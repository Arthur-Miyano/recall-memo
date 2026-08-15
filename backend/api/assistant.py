# -*- coding: utf-8 -*-
"""智能助理对话接口：水墨螃蟹的问答后端（真实调用 LLM），支持多会话管理。

请求：{message} 自由输入，或 {quick: today|recent|all|focus|plan} 快捷指令；
可选 session_id 指定会话（不带则落入最近会话，没有会话时自动建一个）。
响应：{thinking: [...], reply: "...", session_id} —— thinking 为 Agent 调用链的逐步描述（带具体数据）。
持久化：每次问答写入 chat_messages 表（用户消息与助手回复各一条，thinking 存回复那条），
并刷新所属 chat_sessions 的 updated_at（首条用户消息截断为会话标题）。
GET /history?session_id=&limit=50 按时间正序返回该会话历史（不带 session_id 兼容旧行为：全量最近 limit 条）。
会话管理：GET/POST /sessions、DELETE /sessions/{id}。
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session as DBSession, select

from agents.base import SCORE_PASS_THRESHOLD
from api.deps import get_db
from llm import llm_router
from llm.router import LLMProviderUnavailableError
from models import ChatMessage, ChatSession, DailyStat, Question, QuestionFocus, Record, RetryQueueItem
from timeutil import as_local, local_day_start_utc, local_today

router = APIRouter(prefix="/assistant", tags=["assistant"])

# 快捷指令 → 问题文本（与前端 5 个快捷按钮一一对应）
QUICK_PROMPTS = {
    "today": "总结我今天的背诵情况",
    "recent": "总结我最近一周的背诵情况",
    "all": "总结我全部的背诵情况",
    "focus": "我需要重点背诵哪些内容？",
    "plan": "帮我规划一个背诵计划",
}

_SYSTEM_PROMPT = (
    "你是「记忆助手」，一个程序员八股背诵档案的管理员。用户会给你他的背诵档案数据，"
    "请基于数据用简洁的中文回答（可用「1. 2. 3.」式序号列表），不要编造数据里没有的内容，"
    "数据不足时如实说明并给出可执行的建议。回答控制在 200 字以内。"
    "注意：前端按纯文本渲染，不要使用 Markdown 语法（#、**、- 列表等）。"
)


class ChatRequest(BaseModel):
    message: Optional[str] = None
    quick: Optional[str] = None  # today / recent / all / focus / plan
    session_id: Optional[int] = None  # 指定会话；不带则用最近会话或自动新建


def _resolve_session(db: DBSession, session_id: Optional[int]) -> ChatSession:
    """定位本次问答所属会话：指定 id 则校验存在；否则取最近会话，没有则自动新建。"""
    if session_id is not None:
        sess = db.get(ChatSession, session_id)
        if sess is None:
            raise HTTPException(status_code=404, detail=f"会话不存在：{session_id}")
        return sess
    sess = db.exec(select(ChatSession).order_by(ChatSession.updated_at.desc())).first()
    if sess is None:
        sess = ChatSession()
        db.add(sess)
        db.commit()
        db.refresh(sess)
    return sess


def _collect_profile(db: DBSession) -> tuple[str, list[str]]:
    """汇总背诵档案为给 LLM 的上下文文本，同时产出带具体数据的 thinking 步骤描述。"""
    # 档案汇总需逐题/逐条交叉引用（题干文本、队列来源等），全量载入保留；
    # 记录表只取统计所需列，避免整行 ORM 对象载入
    questions = list(db.exec(select(Question)).all())
    records = db.exec(select(Record.question_id, Record.score_total, Record.created_at)).all()

    today = local_today()
    # 近 7 天窗口起点：本地 6 天前 0 点换算成 UTC，与库中 UTC 时间戳比较
    week_start = local_day_start_utc(today - timedelta(days=6))
    q_map = {q.id: q for q in questions}

    covered = {r.question_id for r in records}
    # "今天"按本地日期归属：记录存 UTC，先转本地日期再与 today 比较
    today_records = [r for r in records if as_local(r.created_at).date() >= today]
    week_records = [r for r in records if as_local(r.created_at) >= week_start]
    # 待补答队列与重点题（提前查出，供 thinking 引用具体题名）
    queue_items = list(db.exec(select(RetryQueueItem).order_by(RetryQueueItem.created_at)).all())
    focus_ids = {f.question_id for f in db.exec(select(QuestionFocus)).all()}
    daily = list(db.exec(select(DailyStat).order_by(DailyStat.date.desc()).limit(7)).all())

    queue_names = [q_map[i.question_id].stem[:16] for i in queue_items if i.question_id in q_map]
    thinking: list[str] = [
        f"智能助理 Agent：查询 records —— 累计答题 {len(records)} 条，"
        f"今天 {len(today_records)} 条，近 7 天 {len(week_records)} 条；"
        f"题库 {len(questions)} 题，已覆盖 {len(covered)} 题",
        f"智能助理 Agent：查询待补答队列 —— 共 {len(queue_items)} 题"
        + (f"（{'、'.join(queue_names[:3])}{'…' if len(queue_names) > 3 else ''}）" if queue_names else "（空）"),
    ]

    # 各技术栈正确率
    stack_stat: dict[str, dict] = {}
    for r in records:
        q = q_map.get(r.question_id)
        if q is None or r.score_total is None:
            continue
        e = stack_stat.setdefault(q.tech_stack, {"scored": 0, "passed": 0, "scores": []})
        e["scored"] += 1
        e["scores"].append(r.score_total)
        if r.score_total >= SCORE_PASS_THRESHOLD:
            e["passed"] += 1
    thinking.append(
        f"智能助理 Agent：聚合 {len(stack_stat)} 个技术栈正确率 —— "
        + ("；".join(
            f"{s} {e['passed'] / e['scored']:.0%}（均分 {sum(e['scores']) / e['scored']:.1f}）"
            for s, e in stack_stat.items()
        ) or "暂无已评分记录")
    )
    focus_names = [q_map[qid].stem[:16] for qid in focus_ids if qid in q_map]
    thinking.append(
        f"智能助理 Agent：读取近 7 天 daily_stats 与圈选重点 —— "
        f"重点题 {len(focus_names)} 道"
        + (f"（{'、'.join(focus_names[:3])}{'…' if len(focus_names) > 3 else ''}）" if focus_names else "")
    )

    lines = [
        f"题库总数 {len(questions)} 题，已覆盖 {len(covered)} 题，累计答题 {len(records)} 次。",
        f"今天答题 {len(today_records)} 次；近 7 天答题 {len(week_records)} 次。",
        "各技术栈："
        + ("；".join(
            f"{s} 正确率 {e['passed'] / e['scored']:.0%}（{e['scored']} 次已评分，均分 {sum(e['scores']) / e['scored']:.1f}）"
            for s, e in stack_stat.items()
        ) or "暂无已评分记录"),
        "待补答队列："
        + ("、".join(f"{q_map[i.question_id].stem[:20]}（{i.source} 入队）" for i in queue_items if i.question_id in q_map) or "空"),
        "圈选的重点题："
        + ("、".join(q_map[qid].stem[:20] for qid in focus_ids if qid in q_map) or "无"),
        "近 7 天每日统计："
        + ("；".join(f"{s.date} 答 {s.total_count} 题（成 {s.success_count} / 败 {s.fail_count}）" for s in reversed(daily)) or "无"),
    ]
    return "\n".join(lines), thinking


@router.post("/chat")
async def assistant_chat(req: ChatRequest, db: DBSession = Depends(get_db)):
    if req.quick:
        message = QUICK_PROMPTS.get(req.quick)
        if message is None:
            raise HTTPException(status_code=400, detail=f"未知快捷指令：{req.quick}")
    elif req.message and req.message.strip():
        message = req.message.strip()
    else:
        raise HTTPException(status_code=400, detail="message 与 quick 至少提供一个")

    intent = "背诵情况查询" if req.quick in ("today", "recent", "all") else (
        "重点/规划咨询" if req.quick in ("focus", "plan") else "自由问答"
    )
    thinking = [f"总控 Agent：解析意图 → {intent}"]
    profile, steps = _collect_profile(db)
    thinking += steps

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"【我的背诵档案】\n{profile}\n\n【我的问题】{message}"},
    ]
    try:
        provider, content = await llm_router.chat(messages, temperature=0.5)
    except LLMProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    thinking.append(f"智能助理 Agent：{provider} 模型生成答复，{len(content)} 字")
    sess = _resolve_session(db, req.session_id)
    _save_chat(db, sess, message, content, thinking)
    return {"thinking": thinking, "reply": content, "session_id": sess.id}


def _save_chat(db: DBSession, sess: ChatSession, question: str, reply: str, thinking: list[str]) -> None:
    """一问一答落库：用户消息与助手回复各一条，thinking（JSON 字符串）存回复那条。

    同时刷新会话：首条用户消息截断为标题（仅当会话还没有用户消息时），updated_at 更新为当前时间。
    """
    has_user_msg = db.exec(
        select(ChatMessage.id).where(
            ChatMessage.session_id == sess.id, ChatMessage.role == "user"
        )
    ).first()
    now = datetime.now(timezone.utc)
    db.add(ChatMessage(session_id=sess.id, role="user", content=question, created_at=now))
    db.add(ChatMessage(
        session_id=sess.id, role="assistant", content=reply,
        thinking=json.dumps(thinking, ensure_ascii=False), created_at=now,
    ))
    if not has_user_msg:
        sess.title = question[:24]  # 首条用户消息截断为标题
    sess.updated_at = now
    db.add(sess)
    db.commit()


@router.get("/history")
def assistant_history(
    session_id: Optional[int] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: DBSession = Depends(get_db),
):
    """对话历史：最近 limit 条，按时间正序返回。

    带 session_id 只取该会话；不带则兼容旧行为（全量最近 limit 条，跨会话）。
    """
    stmt = select(ChatMessage)
    if session_id is not None:
        stmt = stmt.where(ChatMessage.session_id == session_id)
    rows = list(db.exec(stmt.order_by(ChatMessage.id.desc()).limit(limit)).all())
    return {
        "messages": [
            {
                "id": m.id,
                "session_id": m.session_id,
                "role": m.role,
                "content": m.content,
                "thinking": json.loads(m.thinking) if m.thinking else None,
                "created_at": m.created_at.isoformat(),
            }
            for m in reversed(rows)
        ]
    }


# ---------- 会话管理 ----------

def _session_payload(db: DBSession, s: ChatSession) -> dict:
    """会话列表项：id、标题、更新时间、消息数。"""
    count = len(db.exec(select(ChatMessage.id).where(ChatMessage.session_id == s.id)).all())
    return {
        "id": s.id,
        "title": s.title,
        "created_at": s.created_at.isoformat(),
        "updated_at": s.updated_at.isoformat(),
        "message_count": count,
    }


@router.get("/sessions")
def list_sessions(db: DBSession = Depends(get_db)):
    """会话列表：按 updated_at 倒序（最近活跃的在前）。"""
    sessions = list(db.exec(select(ChatSession).order_by(ChatSession.updated_at.desc())).all())
    return {"sessions": [_session_payload(db, s) for s in sessions]}


@router.post("/sessions")
def create_session(db: DBSession = Depends(get_db)):
    """新建空会话。"""
    sess = ChatSession()
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return _session_payload(db, sess)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, db: DBSession = Depends(get_db)):
    """删除会话及其全部消息。"""
    sess = db.get(ChatSession, session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail=f"会话不存在：{session_id}")
    for m in db.exec(select(ChatMessage).where(ChatMessage.session_id == session_id)).all():
        db.delete(m)
    db.delete(sess)
    db.commit()
    return {"ok": True, "deleted": session_id}
