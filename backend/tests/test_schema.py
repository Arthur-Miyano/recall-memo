# -*- coding: utf-8 -*-
"""schema 版本迁移、SQLite 参数与约束（修复方案 §6）覆盖：

- 从旧 schema 升级：构造旧版库 → init_db → 新列/默认对话/回填齐备、数据完整、版本号推进；
- 迁移幂等：重复 init_db / run_migrations 不出错、backfill 只执行一次；
- PRAGMA 生效：foreign_keys=ON、journal_mode=WAL、busy_timeout=5000、synchronous=NORMAL；
- 外键与 CheckConstraint 真实生效：孤儿记录/越界分数/非法 mode/state 被拒；
- 存量数据检查脚本：干净库通过、污染库报错停止。
"""
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session as DBSession, select

import database
import models  # noqa: F401  注册全部表定义
from database import SCHEMA_VERSION
from models import Question, Record, RetryQueueItem, Session


# ---------------------------------------------------------------------------
# 旧 schema 库：缺 annotated_answer/operation_id/version/session_id 等后补列
# ---------------------------------------------------------------------------

_OLD_SCHEMA_DDL = [
    """CREATE TABLE questions (
        id INTEGER PRIMARY KEY, stem TEXT NOT NULL, answer TEXT NOT NULL,
        tech_stack TEXT NOT NULL, difficulty TEXT, keywords TEXT, tags TEXT,
        variants TEXT, created_at TEXT)""",
    """CREATE TABLE sessions (
        id INTEGER PRIMARY KEY, mode TEXT NOT NULL, state TEXT, current_question_id INTEGER,
        tech_stack TEXT, active_agent TEXT, question_ids TEXT, quiz_order TEXT,
        current_index INTEGER, context TEXT, created_at TEXT, updated_at TEXT)""",
    # 无 annotated_answer / operation_id
    """CREATE TABLE records (
        id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, question_id INTEGER NOT NULL,
        user_answer TEXT, score_accuracy REAL, score_logic REAL, score_naturalness REAL,
        score_total REAL, is_reciting INTEGER, need_followup INTEGER, skipped INTEGER,
        is_retry INTEGER, retry_of INTEGER, created_at TEXT)""",
    "CREATE TABLE chat_sessions (id INTEGER PRIMARY KEY, title TEXT, created_at TEXT, updated_at TEXT)",
    # 无 session_id
    """CREATE TABLE chat_messages (
        id INTEGER PRIMARY KEY, role TEXT, content TEXT, thinking TEXT, created_at TEXT)""",
    # 无 cache_hit/cache_miss/status/estimated
    """CREATE TABLE llm_usage (
        id INTEGER PRIMARY KEY, provider TEXT, model TEXT, prompt_tokens INTEGER,
        completion_tokens INTEGER, total_tokens INTEGER, created_at TEXT)""",
    """CREATE TABLE daily_stats (
        id INTEGER PRIMARY KEY, date TEXT, total_count INTEGER, success_count INTEGER, fail_count INTEGER)""",
    "CREATE TABLE notes (id INTEGER PRIMARY KEY, title TEXT, content TEXT, created_at TEXT, updated_at TEXT)",
    "CREATE TABLE question_focus (id INTEGER PRIMARY KEY, question_id INTEGER, created_at TEXT)",
    "CREATE TABLE retry_queue (id INTEGER PRIMARY KEY, question_id INTEGER, source TEXT, created_at TEXT)",
    "CREATE TABLE question_groups (id INTEGER PRIMARY KEY, name TEXT, question_ids TEXT, created_at TEXT)",
]


def _make_old_schema_db(path: Path) -> Path:
    """造一个 user_version=0 的旧版库：缺后补列，带少量数据（含待回填的补答场景）。"""
    conn = sqlite3.connect(path)
    for ddl in _OLD_SCHEMA_DDL:
        conn.execute(ddl)
    ts = "2026-01-03 09:00:00.000000"
    conn.execute(
        "INSERT INTO questions (id, stem, answer, tech_stack, difficulty, keywords, tags, variants, created_at) "
        "VALUES (1, '什么是 GIL？', '全局解释器锁。', 'python', 'medium', '[]', '[]', '[]', ?)", (ts,))
    conn.execute(
        "INSERT INTO questions (id, stem, answer, tech_stack, difficulty, keywords, tags, variants, created_at) "
        "VALUES (2, 'TCP 四次挥手？', '……', 'network', 'medium', '[]', '[]', '[]', ?)", (ts,))
    conn.execute(
        "INSERT INTO sessions (id, mode, state, tech_stack, active_agent, question_ids, quiz_order, "
        "current_index, context, created_at, updated_at) "
        "VALUES (1, 'memorize', 'IDLE', 'python', '', '[1, 2]', '[1, 2]', 0, '{}', ?, ?)", (ts, ts))
    # q1 最新记录不及格（应回填入队）；q2 最新记录及格（不入队）
    conn.execute(
        "INSERT INTO records (session_id, question_id, user_answer, score_total, skipped, is_retry, created_at) "
        "VALUES (1, 1, '答错了', 20.0, 0, 0, ?)", (ts,))
    conn.execute(
        "INSERT INTO records (session_id, question_id, user_answer, score_total, skipped, is_retry, created_at) "
        "VALUES (1, 2, '答对了', 90.0, 0, 0, ?)", (ts,))
    # 无 session_id 的历史消息 → v2 迁移应建"默认对话"归入
    conn.execute(
        "INSERT INTO chat_messages (role, content, thinking, created_at) VALUES ('user', '旧消息', NULL, ?)", (ts,))
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def old_db(tmp_path, monkeypatch):
    """旧版库 + 临时引擎接管 database.engine，返回 (engine, db_path)；teardown 释放连接池。"""
    db_path = _make_old_schema_db(tmp_path / "old.db")
    engine = database.create_app_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(database, "engine", engine)
    yield engine, db_path
    engine.dispose()


def _columns(engine, table: str) -> set[str]:
    with engine.connect() as conn:
        return {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}


class TestMigrateFromOldSchema:
    def test_upgrade_from_version_zero(self, old_db):
        """旧版库 → init_db：新列补齐、数据完整、默认对话归入、补答队列回填、版本号推进。"""
        engine, _ = old_db
        database.init_db()

        # 新列齐备
        assert {"annotated_answer", "operation_id"} <= _columns(engine, "records")
        assert "version" in _columns(engine, "sessions")
        assert "session_id" in _columns(engine, "chat_messages")
        assert {"cache_hit_tokens", "cache_miss_tokens", "status", "estimated"} <= _columns(engine, "llm_usage")
        # 版本号推进到当前版本
        assert database.schema_version() == SCHEMA_VERSION

        with DBSession(engine) as db:
            # 数据完整：题目/会话/记录原样保留
            assert len(db.exec(select(Question)).all()) == 2
            assert db.get(Session, 1).mode == "memorize"
            assert len(db.exec(select(Record)).all()) == 2
            # v2：历史消息归入"默认对话"
            msg = db.exec(select(models.ChatMessage)).one()
            assert msg.session_id is not None
            assert db.get(models.ChatSession, msg.session_id).title == "默认对话"
            # v7：q1 最新不及格入队，q2 及格不入队
            queue = {i.question_id: i.source for i in db.exec(select(RetryQueueItem)).all()}
            assert queue == {1: "backfill"}

    def test_migration_idempotent_on_repeat_start(self, old_db):
        """重复启动（init_db 跑两次）不出错，结果一致（存量库兼容硬要求）。"""
        engine, _ = old_db
        database.init_db()
        database.init_db()  # 第二次启动：全部迁移已应用，幂等跳过
        assert database.schema_version() == SCHEMA_VERSION
        with DBSession(engine) as db:
            assert len(db.exec(select(Record)).all()) == 2
            assert len(db.exec(select(models.ChatSession)).all()) == 1, "默认对话不得重复创建"
            assert len(db.exec(select(RetryQueueItem)).all()) == 1

    def test_backfill_runs_only_once(self, old_db):
        """v7 是一次性版本迁移：版本已推进后重跑 run_migrations 不得再次回填。"""
        engine, _ = old_db
        database.init_db()
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM retry_queue"))  # 用户清空队列
        database.run_migrations()  # 版本已是当前：v7 不得重跑
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM retry_queue")).scalar()
        assert count == 0, "backfill 迁移只能执行一次，不得覆盖用户后续操作"

    def test_backfill_public_entry_remains_rerunnable(self, old_db):
        """公开入口 backfill_retry_queue() 语义幂等：手工/测试调用随时可重跑。"""
        engine, _ = old_db
        database.init_db()
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM retry_queue"))
        database.backfill_retry_queue()
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM retry_queue")).scalar()
        assert count == 1


# ---------------------------------------------------------------------------
# PRAGMA 参数（§6.3）
# ---------------------------------------------------------------------------

class TestSqlitePragmas:
    def test_pragmas_applied_on_connect(self, test_engine):
        with test_engine.connect() as conn:
            assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
            assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
            assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 5000
            assert conn.execute(text("PRAGMA synchronous")).scalar() == 1  # NORMAL


# ---------------------------------------------------------------------------
# 外键与 CheckConstraint 真实生效
# ---------------------------------------------------------------------------

class TestConstraintsEnforced:
    def test_orphan_record_rejected(self, db):
        """records 引用不存在的会话/题目 → 外键拒绝。"""
        db.add(Record(session_id=999, question_id=999, user_answer="孤儿"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_orphan_retry_queue_rejected(self, db):
        db.add(RetryQueueItem(question_id=999, source="interview"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_score_out_of_range_rejected(self, db, seed_questions):
        """分数越界 → CheckConstraint 拒绝；合法边界值通过。"""
        (q,) = seed_questions(1)
        sess = Session(mode="memorize", state="IDLE")
        db.add(sess)
        db.commit()
        db.refresh(sess)
        sid = sess.id
        db.add(Record(session_id=sid, question_id=q.id, score_total=150.0))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(Record(session_id=sid, question_id=q.id, score_total=-1.0))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(Record(session_id=sid, question_id=q.id, score_total=100.0))  # 边界值合法
        db.commit()

    def test_invalid_mode_and_state_rejected(self, db):
        db.add(Session(mode="hack", state="IDLE"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(Session(mode="memorize", state="PWNED"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        db.add(Session(mode="interview", state="EXPIRED"))  # EXPIRED 是合法终态标记
        db.commit()

    def test_delete_question_leaves_no_orphans(self, client, db, seed_questions, test_engine):
        """删除题目后：PRAGMA foreign_key_check 无任何违规（无孤儿记录）。"""
        (q,) = seed_questions(1)
        db.add(Session(mode="memorize", state="IDLE", question_ids=[q.id],
                       quiz_order=[q.id], current_question_id=q.id))
        db.commit()
        sid = db.exec(select(Session)).one().id
        db.add(Record(session_id=sid, question_id=q.id, score_total=50.0))
        db.add(RetryQueueItem(question_id=q.id, source="memorize"))
        db.commit()

        resp = client.delete(f"/api/bank/questions/{q.id}")
        assert resp.status_code == 200
        with test_engine.connect() as conn:
            violations = conn.execute(text("PRAGMA foreign_key_check")).fetchall()
        assert violations == [], f"删除后存在孤儿记录：{violations}"


# ---------------------------------------------------------------------------
# 存量数据检查脚本（§6.3）
# ---------------------------------------------------------------------------

class TestCheckDataIntegrityScript:
    def test_clean_database_passes(self, test_engine):
        from scripts.check_data_integrity import check_database

        assert check_database(Path(test_engine.url.database)) == []

    def test_polluted_database_reports_and_stops(self, tmp_path, capsys):
        """污染库：孤儿记录/越界分数/非法 mode/重复唯一键全部列出，main 返回 1。"""
        from scripts.check_data_integrity import check_database

        db_path = tmp_path / "polluted.db"
        conn = sqlite3.connect(db_path)  # 裸连接：FK 默认不强制，可造出脏数据
        conn.execute("CREATE TABLE questions (id INTEGER PRIMARY KEY, stem TEXT)")
        conn.execute("CREATE TABLE sessions (id INTEGER PRIMARY KEY, mode TEXT, state TEXT)")
        conn.execute(
            "CREATE TABLE records (id INTEGER PRIMARY KEY, session_id INTEGER, question_id INTEGER, score_total REAL)"
        )
        conn.execute("CREATE TABLE retry_queue (id INTEGER PRIMARY KEY, question_id INTEGER, source TEXT)")
        conn.execute("INSERT INTO questions (id, stem) VALUES (1, '题')")
        conn.execute("INSERT INTO sessions (id, mode, state) VALUES (1, 'hack', 'IDLE')")
        conn.execute("INSERT INTO records (id, session_id, question_id, score_total) VALUES (1, 999, 1, 150)")
        conn.execute("INSERT INTO retry_queue (question_id, source) VALUES (999, 'interview')")
        conn.commit()
        conn.close()

        violations = check_database(db_path)
        assert any("session_id=999" in v for v in violations), violations
        assert any("超出 0~100" in v for v in violations), violations
        assert any("mode='hack'" in v for v in violations), violations
        assert any("retry_queue" in v and "999" in v for v in violations), violations

        rc = main_with_argv(tmp_path, db_path, capsys)
        assert rc == 1
        out = capsys.readouterr().out
        assert "已停止" in out and "可恢复提示" in out


def main_with_argv(tmp_path, db_path, capsys) -> int:
    """以指定 db_path 调用脚本 main（替换 sys.argv）。"""
    import sys

    from scripts.check_data_integrity import main

    argv = sys.argv
    sys.argv = ["check_data_integrity.py", str(db_path)]
    try:
        return main()
    finally:
        sys.argv = argv
