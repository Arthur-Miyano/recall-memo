# -*- coding: utf-8 -*-
"""智能助理对话接口：水墨螃蟹的问答后端（真实调用 LLM）。

请求：{message} 自由输入，或 {quick: today|recent|all|focus|plan} 快捷指令。
响应：{thinking: [...], reply: "..."} —— thinking 为 Agent 调用链的逐步描述。
"""
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session as DBSession, select

from agents.base import SCORE_PASS_THRESHOLD
from database import engine
from llm import llm_router
from llm.router import LLMProviderUnavailableError
from models import DailyStat, Question, QuestionFocus, Record, RetryQueueItem

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


def get_db():
    with DBSession(engine) as db:
        yield db


class ChatRequest(BaseModel):
    message: Optional[str] = None
    quick: Optional[str] = None  # today / recent / all / focus / plan


def _collect_profile(db: DBSession) -> tuple[str, list[str]]:
    """汇总背诵档案为给 LLM 的上下文文本，同时产出 thinking 步骤描述。"""
    thinking: list[str] = []
    questions = list(db.exec(select(Question)).all())
    records = list(db.exec(select(Record)).all())
    thinking.append("智能助理 Agent：查询 records / daily_stats / 待补答队列 …")

    today = date.today()
    week_start = datetime.combine(today - timedelta(days=6), time.min, tzinfo=timezone.utc)
    q_map = {q.id: q for q in questions}

    covered = {r.question_id for r in records}
    today_records = [r for r in records if r.created_at.date() >= today]
    week_records = [
        r for r in records
        if (r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=timezone.utc)) >= week_start
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
    thinking.append(f"智能助理 Agent：聚合 {len(stack_stat)} 个技术栈正确率 …")

    # 待补答队列与重点题
    queue_items = list(db.exec(select(RetryQueueItem).order_by(RetryQueueItem.created_at)).all())
    focus_ids = {f.question_id for f in db.exec(select(QuestionFocus)).all()}
    daily = list(db.exec(select(DailyStat).order_by(DailyStat.date.desc()).limit(7)).all())

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
    thinking.append(f"智能助理 Agent：{provider} 模型生成答复 …")
    return {"thinking": thinking, "reply": content}
