# -*- coding: utf-8 -*-
"""首页汇总接口：三个模式抽屉的统计数据（形状对齐前端 mock/home.js）。"""
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlmodel import Session as DBSession, select

from database import engine
from models import Question, Record, RetryQueueItem, Session

router = APIRouter(prefix="/home", tags=["home"])

_WEEKDAYS_EN = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def get_db():
    with DBSession(engine) as db:
        yield db


def _as_utc(dt: datetime) -> datetime:
    """SQLite 读出的时间可能丢失时区，统一按 UTC 处理。"""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


@router.get("/summary")
def home_summary(db: DBSession = Depends(get_db)):
    today = date.today()
    now = datetime.now(timezone.utc)
    week_start = datetime.combine(today - timedelta(days=6), time.min, tzinfo=timezone.utc)

    questions = list(db.exec(select(Question)).all())
    records = list(db.exec(select(Record)).all())
    total = len(questions)
    covered_ids = {r.question_id for r in records}
    covered = len(covered_ids)
    week_attempts = sum(1 for r in records if _as_utc(r.created_at) >= week_start)

    # 待补答队列
    retry_count = len(list(db.exec(select(RetryQueueItem)).all()))

    # 记忆训练：上次训练距今天数（取最近一次 memorize 会话）
    last_memorize = db.exec(
        select(Session).where(Session.mode == "memorize").order_by(Session.created_at.desc())
    ).first()
    if last_memorize is not None:
        days_since = (now - _as_utc(last_memorize.created_at)).days
        last_memorize_v, last_memorize_small = str(days_since), " 天前"
    else:
        last_memorize_v, last_memorize_small = "—", " 从未"

    # 面试：历史场次 + 平均分（面试会话下所有已评分记录）
    interview_sessions = list(db.exec(select(Session).where(Session.mode == "interview")).all())
    interview_ids = {s.id for s in interview_sessions}
    interview_scores = [
        r.score_total for r in records
        if r.session_id in interview_ids and r.score_total is not None
    ]
    interview_avg = round(sum(interview_scores) / len(interview_scores), 1) if interview_scores else None

    # 回忆模式：今日到期（有记录且最近一次记录早于今天）+ 最久未复习天数
    last_seen: dict[int, datetime] = {}
    for r in records:
        ts = _as_utc(r.created_at)
        if r.question_id not in last_seen or ts > last_seen[r.question_id]:
            last_seen[r.question_id] = ts
    due_today = sum(1 for ts in last_seen.values() if ts.date() < today)
    stale_days = max(((now - ts).days for ts in last_seen.values()), default=0)
    all_scores = [r.score_total for r in records if r.score_total is not None]
    overall_avg = round(sum(all_scores) / len(all_scores), 1) if all_scores else None

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
                    {"label": "题量", "options": ["3 题", "5 题", "7 题"], "on": 0, "seal": False},
                ],
                "cta": "开始记忆 →",
                "note": "面试答错的题会进入待补答队列，在这里优先重背",
            },
            {
                "idx": "NO.02", "name": "面试模拟", "hint": "INTERVIEW",
                "stats": [
                    {"k": "限时", "v": "2:00"},
                    {"k": "历史场次", "v": str(len(interview_sessions)), "small": " 场"},
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
                    {"k": "今日到期", "v": str(due_today), "small": " 题"},
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
