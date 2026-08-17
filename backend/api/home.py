# -*- coding: utf-8 -*-
"""首页汇总接口：三个模式抽屉的统计数据（形状对齐前端 mock/home.js）。"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlmodel import Session as DBSession, select

from api.deps import get_db
from models import Question, Record, RetryQueueItem, Session
from timeutil import as_local, local_day_start_utc, local_now, local_today

router = APIRouter(prefix="/home", tags=["home"])

_WEEKDAYS_EN = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def _as_utc(dt: datetime) -> datetime:
    """SQLite 读出的时间可能丢失时区，统一按 UTC 处理。"""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


@router.get("/summary")
def home_summary(db: DBSession = Depends(get_db)):
    today = local_today()
    now = local_now()
    # 近 7 天窗口起点：本地 6 天前的 0 点换算成 UTC，再与库中 UTC 时间戳比较
    week_start = local_day_start_utc(today - timedelta(days=6))

    # 题目总数直接 COUNT 下推；记录仍需逐条聚合（每题最近出现/全局均分），但只取需要的列
    total = db.exec(select(func.count(Question.id))).one()
    records = db.exec(select(Record.question_id, Record.score_total, Record.created_at)).all()
    covered = len({r.question_id for r in records})
    week_attempts = sum(1 for r in records if _as_utc(r.created_at) >= week_start)

    # 待补答队列（COUNT 下推）
    retry_count = db.exec(select(func.count(RetryQueueItem.id))).one()

    # 记忆训练：上次训练距今天数（取最近一次 memorize 会话）
    last_memorize = db.exec(
        select(Session).where(Session.mode == "memorize").order_by(Session.created_at.desc())
    ).first()
    if last_memorize is not None:
        days_since = (now - as_local(last_memorize.created_at)).days
        last_memorize_v, last_memorize_small = str(days_since), " 天前"
    else:
        last_memorize_v, last_memorize_small = "—", " 从未"

    # 面试：历史场次 + 平均分（面试会话下所有已评分记录，场次与得分均下推 SQL）
    interview_count = db.exec(
        select(func.count(Session.id)).where(Session.mode == "interview")
    ).one()
    interview_scores = list(db.exec(
        select(Record.score_total).where(
            Record.score_total.is_not(None),
            Record.session_id.in_(select(Session.id).where(Session.mode == "interview")),
        )
    ).all())
    interview_avg = round(sum(interview_scores) / len(interview_scores), 1) if interview_scores else None

    # 回忆模式：逾期未复习（有记录且最近一次出现的本地日期早于今天）+ 最久未复习天数
    last_seen: dict[int, datetime] = {}
    for r in records:
        ts = _as_utc(r.created_at)
        if r.question_id not in last_seen or ts > last_seen[r.question_id]:
            last_seen[r.question_id] = ts
    overdue = sum(1 for ts in last_seen.values() if as_local(ts).date() < today)
    stale_days = max(((now - as_local(ts)).days for ts in last_seen.values()), default=0)
    all_scores = [r.score_total for r in records if r.score_total is not None]
    overall_avg = round(sum(all_scores) / len(all_scores), 1) if all_scores else None

    # 记忆训练可选技术栈：从题库实际存在的 stack 动态生成（混合不限栈，默认选中）
    stacks = sorted(db.exec(select(Question.tech_stack).distinct()).all())
    stack_keys = stacks + ["mixed"]
    stack_labels = [{"vue3": "VUE 3"}.get(k, k.upper()) for k in stacks] + ["混合"]

    return {
        "date": f"{today:%Y.%m.%d} — {_WEEKDAYS_EN[today.weekday()]}",
        "sub": f"// 题库 {total} 题 · 已覆盖 {covered} 题 · 近 7 天答题 {week_attempts} 次",
        "drawers": [
            {
                "idx": "NO.01", "name": "记忆训练", "hint": "MEMORIZE",
                "stats": [
                    {"k": "未背题数", "v": str(total - covered), "small": f" / {total}"},
                    {"k": "待补答", "v": str(retry_count), "small": " 题", "seal": retry_count > 0},
                    {"k": "上次训练", "v": last_memorize_v, "small": last_memorize_small},
                    {"k": "新题优先", "v": "ON"},
                ],
                "optGroups": [
                    # keys 与 options 一一对应，前端按选中下标取 key 传给 POST /api/sessions
                    {"label": "技术栈", "options": stack_labels, "keys": stack_keys, "on": len(stack_keys) - 1, "seal": True},
                    {"label": "题量", "options": ["3 题", "5 题", "7 题"], "on": 0, "seal": False},
                ],
                "cta": "开始记忆 →",
                "note": "面试答错的题会进入待补答队列，在这里优先重背",
            },
            {
                "idx": "NO.02", "name": "面试模拟", "hint": "INTERVIEW",
                "stats": [
                    {"k": "限时", "v": "2:00"},
                    {"k": "历史场次", "v": str(interview_count), "small": " 场"},
                    {"k": "平均得分", "v": str(interview_avg) if interview_avg is not None else "—"},
                ],
                "optGroups": [
                    {"label": "技术栈", "options": ["PYTHON", "AGENT", "VUE 3", "混合"], "on": 3, "seal": True},
                    {"label": "题量", "options": ["3 题", "4 题", "5 题"], "on": 1, "seal": False},
                ],
                "cta": "进入面试 →",
                "note": "全程无反馈，终局统一复盘",
            },
            {
                "idx": "NO.03", "name": "回忆模式", "hint": "RECALL",
                "stats": [
                    {"k": "逾期未复习", "v": str(overdue), "small": " 题"},
                    {"k": "最久未复习", "v": str(stale_days), "small": " 天"},
                    {"k": "平均得分", "v": str(overall_avg) if overall_avg is not None else "—"},
                    {"k": "调度", "v": "EBH", "small": " 曲线"},
                ],
                "optGroups": [],
                "cta": "开始复习 →",
                "note": "只抽背过的题，按遗忘程度排序",
            },
        ],
    }
