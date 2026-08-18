# -*- coding: utf-8 -*-
"""统计接口：给前端仪表盘/知识图谱直接可用的聚合数据。"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session as DBSession, select

from agents.base import SCORE_PASS_THRESHOLD
from api.deps import get_db
from llm.usage import estimate_cost
from models import DailyStat, LLMUsage, Question, Record, Session
from timeutil import as_local, days_ago_local, local_day_start_utc

# 会话模式 → 中文展示名
MODE_DISPLAY = {"memorize": "记忆训练", "interview": "面试", "review": "回忆"}

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/overview")
def stats_overview(db: DBSession = Depends(get_db)):
    """总览：各技术栈的正确率、已覆盖/总题数，以及全局汇总。"""
    # 只取需要的列，避免整行 ORM 对象载入（per-stack 聚合仍需 Python 侧分组，难以完全下推）
    q_rows = db.exec(select(Question.id, Question.tech_stack)).all()
    r_rows = db.exec(select(Record.question_id, Record.score_total)).all()
    q_stack = {qid: stack for qid, stack in q_rows}

    stacks: dict[str, dict] = {}
    for _, stack in q_rows:
        stacks.setdefault(stack, {"total_questions": 0, "covered": 0, "attempts": 0, "pass": 0, "scores": []})
        stacks[stack]["total_questions"] += 1
    covered_ids: set[int] = set()
    for qid, score_total in r_rows:
        stack = q_stack.get(qid)
        if stack is None:
            continue
        covered_ids.add(qid)
        entry = stacks[stack]
        entry["attempts"] += 1
        if score_total is not None:
            entry["scores"].append(score_total)
            if score_total >= SCORE_PASS_THRESHOLD:
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

    total_scored = [score for _, score in r_rows if score is not None]
    return {
        "per_stack": per_stack,
        "total_questions": len(q_rows),
        "covered": len(covered_ids),
        "total_attempts": len(r_rows),
        "avg_score": round(sum(total_scored) / len(total_scored), 1) if total_scored else None,
    }


@router.get("/daily")
def stats_daily(days: int = Query(default=7, ge=1, le=90), db: DBSession = Depends(get_db)):
    """近 N 天答题趋势：每天题数、成功数、失败数（无数据的日期补零，方便前端画折线）。"""
    since = days_ago_local(days - 1)
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
    since = days_ago_local(days - 1)
    # 日期过滤下推 SQL：记录存 UTC，窗口起点取本地 since 日 0 点对应的 UTC 时间
    # （库中时间戳为 UTC 墙钟，比较参数去 tzinfo 避免 SQLite 绑定带时区后缀）
    since_utc = local_day_start_utc(since).replace(tzinfo=None)
    records = db.exec(
        select(Record).where(Record.created_at >= since_utc).order_by(Record.created_at)
    ).all()
    q_map = {q.id: q for q in db.exec(select(Question)).all()}
    s_map = {s.id: s for s in db.exec(select(Session)).all()}

    by_day: dict[date, list[dict]] = {}
    for r in records:
        day = as_local(r.created_at).date()
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


@router.get("/llm-usage")
def stats_llm_usage(days: int = Query(default=30, ge=1, le=90), db: DBSession = Depends(get_db)):
    """LLM 消耗：全量总计（花费/请求/tokens）+ 近 N 天每日柱状数据 + 按模型分组。

    花费按 llm.usage 的单价表在查询时折算（单价调整后历史自动按新价重估）；
    日期口径与其他统计接口一致（本地日期）。
    """
    rows = db.exec(select(LLMUsage)).all()   # 每 LLM 调用一行，量级小，全量可接受
    since = days_ago_local(days - 1)

    totals = {"cost": 0.0, "requests": 0, "tokens": 0, "unpriced_requests": 0, "errors": 0}
    by_model: dict[str, dict] = {}
    by_day: dict[date, dict] = {}
    for r in rows:
        # 缓存列是后补的：老数据 miss 为 0 时回退为「全部按未命中」（上限口径）
        cache_hit = r.cache_hit_tokens or 0
        cache_miss = r.cache_miss_tokens or max(0, r.prompt_tokens - cache_hit)
        cost = estimate_cost(r.provider, r.model, cache_hit, cache_miss, r.completion_tokens, r.created_at)
        totals["requests"] += 1
        totals["tokens"] += r.total_tokens
        if getattr(r, "status", "ok") == "error":
            totals["errors"] += 1
        if cost is None:
            totals["unpriced_requests"] += 1
        else:
            totals["cost"] += cost
        m = by_model.setdefault(r.model, {"model": r.model, "provider": r.provider,
                                          "priced": cost is not None,
                                          "cost": 0.0, "requests": 0, "tokens": 0})
        m["requests"] += 1
        m["tokens"] += r.total_tokens
        if cost is not None:
            m["cost"] += cost
        day = as_local(r.created_at).date()
        if day >= since:
            d = by_day.setdefault(day, {"cost": 0.0, "requests": 0, "tokens": 0})
            if cost is not None:
                d["cost"] += cost
            d["requests"] += 1
            d["tokens"] += r.total_tokens

    daily = []
    for i in range(days):
        day = since + timedelta(days=i)
        d = by_day.get(day)
        daily.append({
            "date": day.isoformat(),
            "cost": round(d["cost"], 4) if d else 0.0,
            "requests": d["requests"] if d else 0,
            "tokens": d["tokens"] if d else 0,
        })

    return {
        "days": days,
        "totals": {
            "cost": round(totals["cost"], 2),
            "requests": totals["requests"],
            "tokens": totals["tokens"],
            "unpriced_requests": totals["unpriced_requests"],
            "errors": totals["errors"],
        },
        "daily": daily,
        "models": sorted(
            ({**m, "cost": round(m["cost"], 4) if m["priced"] else None} for m in by_model.values()),
            key=lambda m: -(m["cost"] or 0),
        ),
    }


@router.get("/per-question")
def stats_per_question(db: DBSession = Depends(get_db)):
    """逐题明细：每题最近得分、答题次数、状态，附题干/答案与最近 5 次得分记录。

    供仪表盘「各技术栈正确率」放大表格与「知识图谱」节点详情使用。
    """
    questions = list(db.exec(select(Question)).all())
    # 记录只取分组/排序/得分所需列，避免整行 ORM 对象载入
    r_rows = db.exec(select(Record.id, Record.question_id, Record.score_total, Record.created_at)).all()

    by_q: dict[int, list[tuple]] = {}
    for r in sorted(r_rows, key=lambda r: (r.created_at, r.id or 0)):
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
                {"date": as_local(r.created_at).date().isoformat(), "score": r.score_total}
                for r in scored[-5:]
            ],
        })
    return {"total": len(items), "items": items}
