# -*- coding: utf-8 -*-
"""统计接口：给前端仪表盘/知识图谱直接可用的聚合数据。"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session as DBSession, select

from agents.base import SCORE_PASS_THRESHOLD
from database import engine
from models import DailyStat, Question, Record

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
