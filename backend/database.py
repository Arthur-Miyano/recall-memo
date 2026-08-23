# -*- coding: utf-8 -*-
"""数据库引擎、schema 版本迁移与启动清理。

- create_app_engine：统一创建引擎并挂 SQLite PRAGMA（§6.3）；
- run_migrations：最小 schema_version 机制（PRAGMA user_version），每个迁移具备唯一版本号
  与事务边界（§6.2）；存量库 user_version=0 时全部迁移幂等重放，重复启动不出错；
- expire_stale_sessions / recover_interrupted_operations 是每次启动都要跑的清理/恢复，
  不属于版本迁移（崩溃残留每次崩溃都会重新产生，见 §3.3）。
"""
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import event, text
from sqlmodel import SQLModel, create_engine

from config import settings
from domain.session_state import SessionState, TERMINAL_SESSION_STATES

logger = logging.getLogger(__name__)


def _apply_sqlite_pragmas(dbapi_conn: Any) -> None:
    """连接建立时执行（§6.3）：外键强制 + WAL + busy_timeout + synchronous=NORMAL。"""
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")
    cur.execute("PRAGMA journal_mode = WAL")
    cur.execute("PRAGMA busy_timeout = 5000")
    cur.execute("PRAGMA synchronous = NORMAL")
    cur.close()


def create_app_engine(url: str):
    """创建带统一 SQLite PRAGMA 的引擎（应用与测试共用，保证约束行为一致）。"""
    # check_same_thread=False：允许 FastAPI 多线程共用 SQLite 连接（单 worker 部署）
    engine = create_engine(url, echo=False, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", lambda dbapi_conn, _: _apply_sqlite_pragmas(dbapi_conn))
    return engine


engine = create_app_engine(settings.database_url)


def init_db() -> None:
    """建表（若不存在）→ 补索引 → 版本迁移 → 启动清理/恢复。需先导入 models 注册表定义。"""
    import models  # noqa: F401  确保所有表已注册到 metadata

    SQLModel.metadata.create_all(engine)
    ensure_indexes()
    run_migrations()
    expire_stale_sessions()
    recover_interrupted_operations()


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


# ----------------------------------------------------------------------
# schema 版本迁移（§6.2）：PRAGMA user_version 记录当前版本，逐个迁移幂等应用
# ----------------------------------------------------------------------

# 当前 schema 版本：新增迁移时在 MIGRATIONS 末尾追加并 +1
SCHEMA_VERSION = 7


def _migrate_1_records_annotated_answer(conn) -> None:
    """v1：records 补 annotated_answer 列（评分标注版答案）。"""
    cols = {row[1] for row in conn.execute(text("PRAGMA table_info(records)"))}
    if "annotated_answer" not in cols:
        conn.execute(text("ALTER TABLE records ADD COLUMN annotated_answer TEXT"))


def _migrate_2_chat_messages_session_id(conn) -> None:
    """v2：chat_messages 补 session_id 列，历史消息归入"默认对话"。"""
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


def _migrate_3_llm_usage_cache_columns(conn) -> None:
    """v3：llm_usage 补缓存命中/未命中列（DeepSeek 缓存命中价不同，分开计价）。"""
    cols = {row[1] for row in conn.execute(text("PRAGMA table_info(llm_usage)"))}
    if not cols:
        return  # 全新库：create_all 已含新列
    if "cache_hit_tokens" not in cols:
        conn.execute(text("ALTER TABLE llm_usage ADD COLUMN cache_hit_tokens INTEGER DEFAULT 0"))
    if "cache_miss_tokens" not in cols:
        conn.execute(text("ALTER TABLE llm_usage ADD COLUMN cache_miss_tokens INTEGER DEFAULT 0"))


def _migrate_4_llm_usage_status_columns(conn) -> None:
    """v4：llm_usage 补 status/estimated 列（失败调用也落库，token 为输入估算）。"""
    cols = {row[1] for row in conn.execute(text("PRAGMA table_info(llm_usage)"))}
    if not cols:
        return  # 全新库：create_all 已含新列
    if "status" not in cols:
        conn.execute(text("ALTER TABLE llm_usage ADD COLUMN status TEXT DEFAULT 'ok'"))
    if "estimated" not in cols:
        conn.execute(text("ALTER TABLE llm_usage ADD COLUMN estimated INTEGER DEFAULT 0"))


def _migrate_5_sessions_version(conn) -> None:
    """v5：sessions 补 version 列（乐观锁，create_all 不会给已有表加列）。"""
    cols = {row[1] for row in conn.execute(text("PRAGMA table_info(sessions)"))}
    if "version" not in cols:
        conn.execute(text("ALTER TABLE sessions ADD COLUMN version INTEGER DEFAULT 0"))


def _migrate_6_records_operation_id(conn) -> None:
    """v6：records 补 operation_id 列并建唯一索引（幂等：一操作一记录）。

    SQLite 的 ALTER TABLE 不能补唯一约束，唯一性用唯一索引兜底（NULL 不冲突，老记录不受影响）。
    """
    cols = {row[1] for row in conn.execute(text("PRAGMA table_info(records)"))}
    if "operation_id" not in cols:
        conn.execute(text("ALTER TABLE records ADD COLUMN operation_id INTEGER REFERENCES workflow_operations(id)"))
    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_records_operation_id ON records (operation_id)"))


# 每题最新一条记录（按 created_at、id 取大者）：SQL 完成，不做全表 Python 内存聚合（§6.2）
_LATEST_RECORDS_SQL = """
SELECT r.question_id, r.score_total, r.skipped FROM records r
WHERE r.id = (
    SELECT r2.id FROM records r2
    WHERE r2.question_id = r.question_id
    ORDER BY r2.created_at DESC, r2.id DESC LIMIT 1
)
"""


def _migrate_7_backfill_retry_queue(conn) -> None:
    """v7：按每题最新记录一次性重建待补答队列（兼容建表前的老数据）。

    规则与运行时一致：最新记录不及格 → 在队列；最新记录及格或被跳过 → 不在队列。
    注意跳过的记录 score_total=0.0，必须先看 skipped 再看分数，否则 0 分会被误判为不及格。
    """
    from agents.base import SCORE_PASS_THRESHOLD

    now = datetime.now(timezone.utc).isoformat()
    # 入队：最新记录不及格（未跳过且有分数且低于阈值）且不在队列
    conn.execute(
        text(
            f"INSERT INTO retry_queue (question_id, source, created_at) "
            f"SELECT question_id, 'backfill', :now FROM ({_LATEST_RECORDS_SQL}) "
            f"WHERE skipped = 0 AND score_total IS NOT NULL AND score_total < :threshold "
            f"AND question_id NOT IN (SELECT question_id FROM retry_queue)"
        ),
        {"now": now, "threshold": SCORE_PASS_THRESHOLD},
    )
    # 出队：最新记录及格/无分/跳过，但仍在队列
    conn.execute(
        text(
            f"DELETE FROM retry_queue WHERE question_id IN ("
            f"SELECT question_id FROM ({_LATEST_RECORDS_SQL}) "
            f"WHERE skipped <> 0 OR score_total IS NULL OR score_total >= :threshold)"
        ),
        {"threshold": SCORE_PASS_THRESHOLD},
    )


# (版本号, 名称, 迁移函数)：函数接收一个事务内 Connection，只写 DDL/DML，不自行提交
MIGRATIONS: list[tuple[int, str, Callable[[Any], None]]] = [
    (1, "records_annotated_answer", _migrate_1_records_annotated_answer),
    (2, "chat_messages_session_id", _migrate_2_chat_messages_session_id),
    (3, "llm_usage_cache_columns", _migrate_3_llm_usage_cache_columns),
    (4, "llm_usage_status_columns", _migrate_4_llm_usage_status_columns),
    (5, "sessions_version", _migrate_5_sessions_version),
    (6, "records_operation_id", _migrate_6_records_operation_id),
    (7, "backfill_retry_queue", _migrate_7_backfill_retry_queue),
]


def schema_version() -> int:
    """当前库的 schema 版本（PRAGMA user_version；从未迁移过的库为 0）。"""
    with engine.connect() as conn:
        return conn.execute(text("PRAGMA user_version")).scalar() or 0


def run_migrations() -> None:
    """按版本顺序应用未执行的迁移：每个迁移一个事务，成功后推进 user_version。

    存量库 user_version=0：全部迁移幂等重放（列存在即跳过），不会重复执行出错（§6.2）。
    """
    applied = schema_version()
    for version, name, fn in MIGRATIONS:
        if version <= applied:
            continue
        with engine.begin() as conn:  # 事务边界：迁移失败整体回滚，版本号不推进
            fn(conn)
            conn.execute(text(f"PRAGMA user_version = {version}"))
        logger.info("schema 迁移 v%s（%s）已应用", version, name)


def backfill_retry_queue() -> None:
    """v7 迁移的公开入口（测试/手工调用）：语义幂等，随时可安全重跑。"""
    with engine.begin() as conn:
        _migrate_7_backfill_retry_queue(conn)


# ----------------------------------------------------------------------
# 启动清理与恢复（每次启动都跑，不属于版本迁移）
# ----------------------------------------------------------------------

def expire_stale_sessions() -> None:
    """启动时把「昨天及更早的进行中会话」标记为 EXPIRED（页面刷新/中断留下的孤儿会话）。

    - 进行中 = state 不在终态集合（domain.session_state.TERMINAL_SESSION_STATES）；
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
            if s.state not in TERMINAL_SESSION_STATES and as_local(s.updated_at).date() < today
        ]
        for s in stale:
            s.state = "EXPIRED"
            s.active_agent = ""
            db.add(s)
        if stale:
            db.commit()


def recover_interrupted_operations() -> None:
    """启动恢复：把上次进程中断残留的 PENDING/RUNNING 操作标记为 FAILED（INTERRUPTED）。

    单进程部署：服务启动时不存在真正"进行中"的操作，RUNNING/PENDING 一定是崩溃残留；
    标记 FAILED 后客户端可用同一幂等键安全重试（见修复方案 §3.3）。
    """
    from sqlmodel import Session as DBSession, select

    from models import Session, WorkflowOperation

    with DBSession(engine) as db:
        stale = db.exec(
            select(WorkflowOperation).where(WorkflowOperation.status.in_(["PENDING", "RUNNING"]))
        ).all()
        for op in stale:
            session = db.get(Session, op.session_id)
            if (
                session is not None
                and op.operation_type in ("answer", "skip")
                and session.current_index == op.question_index
                and session.state == SessionState.INTERVIEW_SCORE.value
            ):
                # 评分阶段没有业务提交；进程中断后应回到原题等待回答，允许同键重试。
                session.state = SessionState.INTERVIEW_ANSWER.value
                session.current_question_id = op.question_id
                session.active_agent = "面试官"
                session.updated_at = datetime.now(timezone.utc)
                db.add(session)
            op.status = "FAILED"
            op.error_code = "INTERRUPTED"
            op.updated_at = datetime.now(timezone.utc)
            db.add(op)
        if stale:
            db.commit()
