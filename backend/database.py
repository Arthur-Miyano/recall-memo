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
    migrate_records_annotated_answer()
    backfill_retry_queue()


def migrate_records_annotated_answer() -> None:
    """轻量迁移：旧库的 records 表补 annotated_answer 列（create_all 不会给已有表加列）。"""
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(records)"))}
        if "annotated_answer" not in cols:
            conn.execute(text("ALTER TABLE records ADD COLUMN annotated_answer TEXT"))


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
