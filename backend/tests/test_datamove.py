# -*- coding: utf-8 -*-
"""API 覆盖（数据迁移）：/settings/export 整库导出 + /settings/import-db 幂等合并导入。

隔离红线：client 夹具已把 database.engine 换成 tmp_path 下的临时库，
datamove 的导入/导出/备份全部从 engine.url 推导路径，因此备份文件也落在 tmp_path，
绝不触碰真实 data/bagu.db。
"""
import sqlite3
from datetime import date, datetime
from pathlib import Path

from sqlmodel import SQLModel, create_engine, select
from sqlmodel import Session as DBSession

import models
from models import (
    ChatMessage, ChatSession, DailyStat, Note, Question, QuestionFocus,
    Record, RetryQueueItem, Session,
)


# ----------------------------------------------------------------------
# 造"旧库"：独立的临时 SQLite，schema 与当前一致，种入各表数据
# ----------------------------------------------------------------------

def _make_old_db(path: Path) -> Path:
    """造一个完整旧库：2 题（1 题与当前库题干相似应判重）+ 会话/记录/重点/统计等各若干。"""
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with DBSession(engine) as db:
        # q1 与当前库已有题题干几乎相同（导入时应判重）；q2 是全新题
        q1 = Question(
            stem="旧库题干：什么是 Python 的 GIL 锁？（表述略有差异）", answer="全局解释器锁。",
            tech_stack="python", difficulty="hard", keywords=["GIL"], tags=["并发"],
            variants=["变体：GIL 是什么？"], created_at=datetime(2026, 1, 1, 10, 0, 0),
        )
        q2 = Question(
            stem="旧库独有题：TCP 四次挥手为什么是四次？", answer="因为被动关闭方的 ACK 和 FIN 分开发送。",
            tech_stack="network", keywords=["TCP"], tags=["网络"],
            created_at=datetime(2026, 1, 2, 10, 0, 0),
        )
        db.add(q1)
        db.add(q2)
        db.flush()
        s1 = Session(
            mode="memorize", state="IDLE", tech_stack="python",
            question_ids=[q1.id, q2.id], quiz_order=[q2.id, q1.id],
            current_question_id=q2.id,
            created_at=datetime(2026, 1, 3, 9, 0, 0), updated_at=datetime(2026, 1, 3, 10, 0, 0),
        )
        db.add(s1)
        db.flush()
        r1 = Record(
            session_id=s1.id, question_id=q1.id, user_answer="GIL 是全局解释器锁，同一时刻只有一个线程执行字节码。",
            score_total=80.0, score_accuracy=85.0, created_at=datetime(2026, 1, 3, 9, 30, 0),
        )
        db.add(r1)
        db.flush()
        r2 = Record(
            session_id=s1.id, question_id=q2.id, user_answer="因为 TIME_WAIT……",
            score_total=40.0, is_retry=True, retry_of=r1.id, created_at=datetime(2026, 1, 3, 9, 40, 0),
        )
        db.add(r2)
        db.add(QuestionFocus(question_id=q2.id, created_at=datetime(2026, 1, 3, 11, 0, 0)))
        db.add(RetryQueueItem(question_id=q2.id, source="interview", created_at=datetime(2026, 1, 3, 11, 0, 0)))
        db.add(models.QuestionGroup(name="并发追问链", question_ids=[q1.id, q2.id],
                                    created_at=datetime(2026, 1, 3, 12, 0, 0)))
        db.add(DailyStat(date=date(2026, 1, 3), total_count=5, success_count=3, fail_count=2))
        cs = ChatSession(title="GIL 相关讨论", created_at=datetime(2026, 1, 4, 8, 0, 0),
                         updated_at=datetime(2026, 1, 4, 8, 5, 0))
        db.add(cs)
        db.flush()
        db.add(ChatMessage(session_id=cs.id, role="user", content="GIL 会影响多线程爬虫吗？",
                           created_at=datetime(2026, 1, 4, 8, 1, 0)))
        db.add(Note(title="并发笔记", content="GIL 要点整理……",
                    created_at=datetime(2026, 1, 5, 8, 0, 0), updated_at=datetime(2026, 1, 5, 8, 0, 0)))
        db.add(models.LLMUsage(provider="deepseek", model="deepseek-v4-flash", prompt_tokens=100,
                               completion_tokens=50, total_tokens=150,
                               created_at=datetime(2026, 1, 3, 9, 30, 1)))
        db.commit()
    engine.dispose()
    return path


def _seed_current(db):
    """当前库已有：1 道与旧库 q1 题干相似的题（应被判重吃掉）。"""
    q = Question(
        stem="什么是 Python 的 GIL 锁？（表述略有差异）", answer="全局解释器锁，CPython 特有。",
        tech_stack="python", created_at=datetime(2026, 1, 1, 8, 0, 0),
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return q


def _upload(client, path: Path):
    return client.post(
        "/api/settings/import-db",
        files={"file": ("old-bagu.db", path.read_bytes(), "application/octet-stream")},
    )


# ----------------------------------------------------------------------
# 导出
# ----------------------------------------------------------------------

class TestExport:
    def test_export_downloads_sqlite_file(self, client, seed_questions):
        seed_questions(2)
        resp = client.get("/api/settings/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/octet-stream"
        assert "recall-backup-" in resp.headers.get("content-disposition", "")
        assert resp.content.startswith(b"SQLite format 3")


# ----------------------------------------------------------------------
# 导入合并
# ----------------------------------------------------------------------

class TestImportMerge:
    def test_merge_counts_and_id_remap(self, client, db, tmp_path):
        existing_q = _seed_current(db)
        old_db = _make_old_db(tmp_path / "old.db")

        resp = _upload(client, old_db)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        tables = data["tables"]

        # 题：q1 与现有题题干相似 → 跳过；q2 新插入
        assert tables["questions"] == {"imported": 1, "skipped": 1}
        assert tables["sessions"] == {"imported": 1, "skipped": 0}
        assert tables["records"] == {"imported": 2, "skipped": 0}
        assert tables["question_focus"] == {"imported": 1, "skipped": 0}
        assert tables["retry_queue"] == {"imported": 1, "skipped": 0}
        assert tables["question_groups"] == {"imported": 1, "skipped": 0}
        assert tables["daily_stats"] == {"imported": 1, "skipped": 0}
        assert tables["chat_sessions"] == {"imported": 1, "skipped": 0}
        assert tables["chat_messages"] == {"imported": 1, "skipped": 0}
        assert tables["notes"] == {"imported": 1, "skipped": 0}
        assert tables["llm_usage"] == {"imported": 1, "skipped": 0}
        assert data["backup"]

        # 总数：1 已有 + 1 新增 = 2（相似题没产生重复）
        db.expire_all()
        assert len(db.exec(select(Question)).all()) == 2

        # id 重映射：records 指向新库里的 question id（旧 q1 → 现有题；旧 q2 → 新插入题）
        records = db.exec(select(Record).order_by(Record.created_at)).all()
        new_q = db.exec(select(Question).where(Question.tech_stack == "network")).one()
        assert {r.question_id for r in records} == {existing_q.id, new_q.id}
        # retry_of 也走映射：r2 的 retry_of 指向重映射后的 r1
        r2 = next(r for r in records if r.is_retry)
        r1 = next(r for r in records if not r.is_retry)
        assert r2.retry_of == r1.id

        # 重点/补答队列指向新题 id
        assert db.exec(select(QuestionFocus)).one().question_id == new_q.id
        assert db.exec(select(RetryQueueItem)).one().question_id == new_q.id

        # 会话内题目引用已重映射
        s = db.exec(select(Session)).one()
        assert sorted(s.question_ids) == sorted([existing_q.id, new_q.id])
        assert s.current_question_id == new_q.id

        # 追问组 question_ids 已重映射
        g = db.exec(select(models.QuestionGroup)).one()
        assert sorted(g.question_ids) == sorted([existing_q.id, new_q.id])

    def test_import_twice_is_idempotent(self, client, db, tmp_path):
        _seed_current(db)
        old_db = _make_old_db(tmp_path / "old.db")

        first = _upload(client, old_db).json()["tables"]
        second = _upload(client, old_db).json()["tables"]

        # 第二次：全部跳过，没有新导入
        for table, counts in second.items():
            assert counts["imported"] == 0, f"{table} 第二次导入仍新增了 {counts['imported']} 条"
        assert sum(c["imported"] for c in first.values()) > 0  # 第一次确实导入了数据

        # 各表总数与第一次导入后一致
        db.expire_all()
        assert len(db.exec(select(Question)).all()) == 2
        assert len(db.exec(select(Record)).all()) == 2
        assert len(db.exec(select(Session)).all()) == 1
        assert len(db.exec(select(DailyStat)).all()) == 1
        assert len(db.exec(select(ChatMessage)).all()) == 1

    def test_backup_file_created(self, client, db, test_engine, tmp_path):
        _seed_current(db)
        old_db = _make_old_db(tmp_path / "old.db")
        resp = _upload(client, old_db)
        assert resp.status_code == 200
        backups = list(Path(test_engine.url.database).parent.glob("test.db.bak-*"))
        assert len(backups) == 1
        assert backups[0].read_bytes().startswith(b"SQLite format 3")

    def test_non_sqlite_file_rejected(self, client):
        resp = client.post(
            "/api/settings/import-db",
            files={"file": ("fake.db", b"this is not a sqlite file at all", "application/octet-stream")},
        )
        assert resp.status_code == 400

    def test_missing_tables_skipped(self, client, db, tmp_path):
        """更老版本的库表不全（只有 questions，且缺 keywords 等后补列）：跳过缺失表不报错。"""
        _seed_current(db)
        old = tmp_path / "ancient.db"
        conn = sqlite3.connect(old)
        conn.execute(
            "CREATE TABLE questions (id INTEGER PRIMARY KEY, stem TEXT, answer TEXT, "
            "tech_stack TEXT, difficulty TEXT, created_at TEXT)"
        )
        conn.execute(
            "INSERT INTO questions (stem, answer, tech_stack, difficulty, created_at) VALUES (?, ?, ?, ?, ?)",
            ("远古独有题：进程和线程的区别是什么？", "进程是资源分配单位，线程是调度单位。",
             "os", "basic", "2025-12-01 10:00:00.000000"),
        )
        conn.commit()
        conn.close()

        resp = _upload(client, old)
        assert resp.status_code == 200, resp.text
        tables = resp.json()["tables"]
        assert tables["questions"] == {"imported": 1, "skipped": 0}
        # 缺失的表：0/0 不报错
        for name in ("records", "sessions", "daily_stats", "chat_messages", "notes", "llm_usage"):
            assert tables[name] == {"imported": 0, "skipped": 0}
        db.expire_all()
        assert db.exec(select(Question).where(Question.tech_stack == "os")).one().keywords == []
