# -*- coding: utf-8 -*-
"""数据库引擎与初始化。"""
from sqlalchemy import text
from sqlmodel import SQLModel, create_engine

from config import settings

# check_same_thread=False：允许 FastAPI 多线程共用 SQLite 连接（单 worker 部署）
engine = create_engine(settings.database_url, echo=False, connect_args={"check_same_thread": False})


def init_db() -> None:
    """建表（若不存在）。需先导入 models 以注册表定义。"""
    import models  # noqa: F401  确保所有表已注册到 metadata

    SQLModel.metadata.create_all(engine)
    ensure_indexes()
    migrate_records_annotated_answer()
    migrate_chat_messages_session_id()
    migrate_llm_usage_cache_columns()
    backfill_retry_queue()
    expire_stale_sessions()


def ensure_indexes() -> None:
    """给旧库补高频过滤字段索引（SQLite create_all 不会给已有表补索引）。"""
    stmts = [
        "CREATE INDEX IF NOT EXISTS ix_records_question_id ON records (question_id)",
        "CREATE INDEX IF NOT EXISTS ix_records_session_id ON records (session_id)",
        "CREATE INDEX IF NOT EXISTS ix_records_created_at ON records (created_at)",
    ]
    with engine.begin() as conn:
        for stmt in stmts:
            conn.execute(text(stmt))


# 会话终态：处于这些状态的会话不算"进行中"（与 agents/orchestrator.py 的状态机对应；
# 不 import 是为避免 database ↔ agents 循环依赖）
_TERMINAL_SESSION_STATES = {"IDLE", "INTERVIEW_REVIEW", "EXPIRED"}


def expire_stale_sessions() -> None:
    """启动时把「昨天及更早的进行中会话」标记为 EXPIRED（页面刷新/中断留下的孤儿会话）。

    - 进行中 = state 不在终态集合（IDLE / INTERVIEW_REVIEW / EXPIRED）；
    - 归属日期按本地时区口径（updated_at 转本地日期 < 本地今天才清理）；
      今天的进行中会话保留——用户可能只是刷新页面；
    - EXPIRED 是状态机不认识的终态标记：之后任何操作都会自然抛 StateError，
      统计口径（records / daily_stats）不涉及 state，不受影响。
    """
    from sqlmodel import Session as DBSession, select

    from models import Session
    from timeutil import as_local, local_today

    today = local_today()
    with DBSession(engine) as db:
        stale = [
            s for s in db.exec(select(Session)).all()
            if s.state not in _TERMINAL_SESSION_STATES and as_local(s.updated_at).date() < today
        ]
        for s in stale:
            s.state = "EXPIRED"
            s.active_agent = ""
            db.add(s)
        if stale:
            db.commit()


def migrate_records_annotated_answer() -> None:
    """轻量迁移：旧库的 records 表补 annotated_answer 列（create_all 不会给已有表加列）。"""
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(records)"))}
        if "annotated_answer" not in cols:
            conn.execute(text("ALTER TABLE records ADD COLUMN annotated_answer TEXT"))


def migrate_chat_messages_session_id() -> None:
    """轻量迁移：旧库的 chat_messages 表补 session_id 列，历史消息归入"默认对话"。

    与 migrate_records_annotated_answer 同一模式：PRAGMA 查列 + ALTER TABLE 补列；
    补列后若存在 session_id 为 NULL 的旧消息，则建一个"默认对话"把它们全部归入。
    """
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(chat_messages)"))}
        if "session_id" not in cols:
            conn.execute(text("ALTER TABLE chat_messages ADD COLUMN session_id INTEGER REFERENCES chat_sessions(id)"))
        orphan = conn.execute(text("SELECT COUNT(*) FROM chat_messages WHERE session_id IS NULL")).scalar()
        if orphan:
            # 旧消息时间范围作为默认对话的创建/更新时间，保证列表排序合理
            first_ts, last_ts = conn.execute(
                text("SELECT MIN(created_at), MAX(created_at) FROM chat_messages WHERE session_id IS NULL")
            ).one()
            cur = conn.execute(
                text('INSERT INTO chat_sessions (title, created_at, updated_at) VALUES (:t, :c, :u)'),
                {"t": "默认对话", "c": first_ts, "u": last_ts},
            )
            conn.execute(
                text("UPDATE chat_messages SET session_id = :sid WHERE session_id IS NULL"),
                {"sid": cur.lastrowid},
            )


def migrate_llm_usage_cache_columns() -> None:
    """轻量迁移：llm_usage 表补缓存命中/未命中列（DeepSeek 缓存命中价不同，分开计价）。"""
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(llm_usage)"))}
        if not cols:
            return  # 全新库：create_all 已含新列
        if "cache_hit_tokens" not in cols:
            conn.execute(text("ALTER TABLE llm_usage ADD COLUMN cache_hit_tokens INTEGER DEFAULT 0"))
        if "cache_miss_tokens" not in cols:
            conn.execute(text("ALTER TABLE llm_usage ADD COLUMN cache_miss_tokens INTEGER DEFAULT 0"))


def backfill_retry_queue() -> None:
    """按每题最新一条记录重建待补答队列（兼容建表前的老数据）。

    规则与运行时一致：最新记录不及格或被跳过 → 在队列；最新记录及格 → 不在队列。
    """
    from sqlmodel import Session as DBSession, select

    from agents.base import SCORE_PASS_THRESHOLD
    from models import Record, RetryQueueItem

    with DBSession(engine) as db:
        records = db.exec(select(Record).order_by(Record.created_at, Record.id)).all()
        latest: dict[int, Record] = {}
        for r in records:
            latest[r.question_id] = r
        existing = {i.question_id: i for i in db.exec(select(RetryQueueItem)).all()}
        for qid, r in latest.items():
            failed = r.skipped or (r.score_total is not None and r.score_total < SCORE_PASS_THRESHOLD)
            if failed and qid not in existing:
                db.add(RetryQueueItem(question_id=qid, source="backfill"))
            elif not failed and qid in existing:
                db.delete(existing[qid])
        db.commit()
