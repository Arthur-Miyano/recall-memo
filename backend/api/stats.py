# -*- coding: utf-8 -*-
"""统计接口：给前端仪表盘/知识图谱直接可用的聚合数据。"""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session as DBSession, select

from agents.base import SCORE_PASS_THRESHOLD
from database import engine
from models import DailyStat, Question, Record, Session

# 会话模式 → 中文展示名
MODE_DISPLAY = {"memorize": "记忆训练", "interview": "面试", "review": "回忆"}


def _local_date(dt: datetime) -> date:
    """记录时间戳按 UTC 存储，转成当地日期再分组（与 DailyStat.date 口径一致）。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().date()

router = APIRouter(prefix="/stats", tags=["stats"])


def get_db():
    """每个请求一个 SQLModel Session（单 worker + SQLite，随请求关闭）。"""
    with DBSession(engine) as db:
        yield db


@router.get("/overview")
def stats_overview(db: DBSession = Depends(get_db)):
    """总览：各技术栈的正确率、已覆盖/总题数，以及全局汇总。"""
    questions = list(db.exec(select(Question)).all())
    records = list(db.exec(select(Record)).all())
    q_stack = {q.id: q.tech_stack for q in questions}

    stacks: dict[str, dict] = {}
    for q in questions:
        stacks.setdefault(q.tech_stack, {"total_questions": 0, "covered": 0, "attempts": 0, "pass": 0, "scores": []})
        stacks[q.tech_stack]["total_questions"] += 1
    covered_ids: set[int] = set()
    for r in records:
        stack = q_stack.get(r.question_id)
        if stack is None:
            continue
        covered_ids.add(r.question_id)
        entry = stacks[stack]
        entry["attempts"] += 1
        if r.score_total is not None:
            entry["scores"].append(r.score_total)
            if r.score_total >= SCORE_PASS_THRESHOLD:
                entry["pass"] += 1

    per_stack = {}
    for stack, e in stacks.items():
        scored = len(e["scores"])
        per_stack[stack] = {
            "total_questions": e["total_questions"],
            "covered": len({qid for qid in covered_ids if q_stack[qid] == stack}),
            "attempts": e["attempts"],
            # 正确率 = 及格（>= 60）记录数 / 已评分记录数
            "pass_rate": round(e["pass"] / scored, 4) if scored else None,
            "avg_score": round(sum(e["scores"]) / scored, 1) if scored else None,
        }

    total_scored = [r.score_total for r in records if r.score_total is not None]
    return {
        "per_stack": per_stack,
        "total_questions": len(questions),
        "covered": len(covered_ids),
        "total_attempts": len(records),
        "avg_score": round(sum(total_scored) / len(total_scored), 1) if total_scored else None,
    }


@router.get("/daily")
def stats_daily(days: int = Query(default=7, ge=1, le=90), db: DBSession = Depends(get_db)):
    """近 N 天答题趋势：每天题数、成功数、失败数（无数据的日期补零，方便前端画折线）。"""
    since = date.today() - timedelta(days=days - 1)
    rows = db.exec(select(DailyStat).where(DailyStat.date >= since).order_by(DailyStat.date)).all()
    by_date = {s.date: s for s in rows}
    result = []
    for i in range(days):
        day = since + timedelta(days=i)
        stat = by_date.get(day)
        result.append({
            "date": day.isoformat(),
            "total_count": stat.total_count if stat else 0,
            "success_count": stat.success_count if stat else 0,
            "fail_count": stat.fail_count if stat else 0,
        })
    return {"days": days, "items": result}


@router.get("/daily-detail")
def stats_daily_detail(days: int = Query(default=30, ge=1, le=90), db: DBSession = Depends(get_db)):
    """近 N 天逐日答题明细：只返回有答题的日期，每天列出答了哪些题、得分与模式。

    供仪表盘「每日背诵记录」放大视图使用；日期口径与 /stats/daily 一致（本地日期）。
    """
    since = date.today() - timedelta(days=days - 1)
    records = db.exec(select(Record).order_by(Record.created_at)).all()
    q_map = {q.id: q for q in db.exec(select(Question)).all()}
    s_map = {s.id: s for s in db.exec(select(Session)).all()}

    by_day: dict[date, list[dict]] = {}
    for r in records:
        day = _local_date(r.created_at)
        if day < since:
            continue
        q = q_map.get(r.question_id)
        session = s_map.get(r.session_id)
        by_day.setdefault(day, []).append({
            "question_id": r.question_id,
            "title": (q.stem if q else f"题目 #{r.question_id}"),
            "score": r.score_total,
            "mode": MODE_DISPLAY.get(session.mode if session else "", "背诵"),
            "skipped": r.skipped,
            "is_retry": r.is_retry,
        })

    items = [
        {"date": day.isoformat(), "records": recs}
        for day, recs in sorted(by_day.items(), reverse=True)  # 最近的日期在前
    ]
    return {"days": days, "items": items}


@router.get("/per-question")
def stats_per_question(db: DBSession = Depends(get_db)):
    """逐题明细：每题最近得分、答题次数、状态，附题干/答案与最近 5 次得分记录。

    供仪表盘「各技术栈正确率」放大表格与「知识图谱」节点详情使用。
    """
    questions = list(db.exec(select(Question)).all())
    records = list(db.exec(select(Record)).all())

    by_q: dict[int, list[Record]] = {}
    for r in sorted(records, key=lambda r: (r.created_at, r.id or 0)):
        by_q.setdefault(r.question_id, []).append(r)

    items = []
    for q in sorted(questions, key=lambda q: q.id or 0):
        recs = by_q.get(q.id, [])
        scored = [r for r in recs if r.score_total is not None]
        latest = scored[-1] if scored else None
        score = latest.score_total if latest else None
        if score is None:
            status = "todo"
        elif score >= SCORE_PASS_THRESHOLD:
            status = "done"
        else:
            status = "weak"
        tags = q.tags or []
        items.append({
            "question_id": q.id,
            "stem": q.stem,
            "answer": q.answer,
            "tech_stack": q.tech_stack,
            "group": tags[1] if len(tags) > 1 else (tags[0] if tags else "未分类"),
            "attempts": len(recs),
            "latest_score": score,
            "status": status,
            "last_at": recs[-1].created_at.isoformat() if recs else None,
            # 最近 5 次得分记录（时间升序），图谱节点详情展示用
            "recent_scores": [
                {"date": _local_date(r.created_at).isoformat(), "score": r.score_total}
                for r in scored[-5:]
            ],
        })
    return {"total": len(items), "items": items}

# reload probe
# probe2
