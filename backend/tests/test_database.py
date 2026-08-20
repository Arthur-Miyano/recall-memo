# -*- coding: utf-8 -*-
"""database 维护函数覆盖：

- expire_stale_sessions：昨天及更早的进行中会话 -> EXPIRED；今天的保留；终态（IDLE/INTERVIEW_REVIEW/EXPIRED）不动；
- ensure_indexes：幂等，重复调用不报错，索引真实存在；
- backfill_retry_queue：按每题最新记录重建队列（不及格入队，及格/跳过出队——跳过判负不给补答）。
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlmodel import Session as DBSession, select

import database
from database import ensure_indexes, expire_stale_sessions
from models import Record, RetryQueueItem, Session


def _make_session(db, state: str, updated_at: datetime | None = None) -> Session:
    s = Session(mode="memorize", state=state, active_agent="总控")
    db.add(s)
    db.commit()
    db.refresh(s)
    if updated_at is not None:
        s.updated_at = updated_at
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def _states(db):
    return {s.id: s.state for s in db.exec(select(Session)).all()}


class TestExpireStaleSessions:
    def test_old_in_progress_expired(self, test_engine):
        yesterday_utc = datetime.now(timezone.utc) - timedelta(days=1, hours=1)
        with DBSession(test_engine) as db:
            old_quiz = _make_session(db, "MEMORIZE_QUIZ", updated_at=yesterday_utc)
            old_interview = _make_session(db, "INTERVIEW_ANSWER", updated_at=yesterday_utc)
            ids = (old_quiz.id, old_interview.id)

        expire_stale_sessions()

        with DBSession(test_engine) as db:
            states = _states(db)
            assert states[ids[0]] == "EXPIRED"
            assert states[ids[1]] == "EXPIRED"
            # active_agent 被清空
            assert db.get(Session, ids[0]).active_agent == ""

    def test_today_in_progress_kept(self, test_engine):
        with DBSession(test_engine) as db:
            fresh = _make_session(db, "MEMORIZE_QUIZ")  # updated_at = 现在
            fid = fresh.id
        expire_stale_sessions()
        with DBSession(test_engine) as db:
            assert _states(db)[fid] == "MEMORIZE_QUIZ", "今天的进行中会话必须保留"

    def test_terminal_states_untouched(self, test_engine):
        old = datetime.now(timezone.utc) - timedelta(days=3)
        with DBSession(test_engine) as db:
            idle = _make_session(db, "IDLE", updated_at=old)
            review = _make_session(db, "INTERVIEW_REVIEW", updated_at=old)
            expired = _make_session(db, "EXPIRED", updated_at=old)
            ids = (idle.id, review.id, expired.id)
        expire_stale_sessions()
        with DBSession(test_engine) as db:
            states = _states(db)
            assert states[ids[0]] == "IDLE"
            assert states[ids[1]] == "INTERVIEW_REVIEW"
            assert states[ids[2]] == "EXPIRED"

    def test_idempotent(self, test_engine):
        old = datetime.now(timezone.utc) - timedelta(days=2)
        with DBSession(test_engine) as db:
            _make_session(db, "REVIEW_QUIZ", updated_at=old)
        expire_stale_sessions()
        expire_stale_sessions()  # 第二次调用不应报错也不应再改动
        with DBSession(test_engine) as db:
            assert list(_states(db).values()) == ["EXPIRED"]


class TestEnsureIndexes:
    def test_indexes_created_and_idempotent(self, test_engine):
        ensure_indexes()
        ensure_indexes()  # 幂等：重复调用不报错
        with test_engine.connect() as conn:
            indexes = {row[1] for row in conn.execute(text("PRAGMA index_list(records)"))}
        assert {"ix_records_question_id", "ix_records_session_id", "ix_records_created_at"} <= indexes


class TestBackfillRetryQueue:
    def test_rebuild_from_latest_records(self, test_engine):
        """按每题最新一条记录重建队列：最新不及格入队，最新及格/跳过出队。"""
        from models import Question

        with DBSession(test_engine) as db:
            q1 = Question(stem="题一？", answer="答案一", tech_stack="python")
            q2 = Question(stem="题二？", answer="答案二", tech_stack="python")
            q3 = Question(stem="题三？", answer="答案三", tech_stack="python")
            db.add(q1)
            db.add(q2)
            db.add(q3)
            db.commit()
            db.refresh(q1)
            db.refresh(q2)
            db.refresh(q3)

            # q1：最新记录不及格 -> 应在队列
            db.add(Record(session_id=1, question_id=q1.id, score_total=90.0))
            db.add(Record(session_id=1, question_id=q1.id, score_total=20.0))
            # q2：最新记录及格 -> 不在队列
            db.add(Record(session_id=1, question_id=q2.id, score_total=30.0))
            db.add(Record(session_id=1, question_id=q2.id, score_total=85.0))
            # q3：最新记录被跳过 -> 跳过判负不给补答，不应在队列
            db.add(Record(session_id=1, question_id=q3.id, score_total=0.0, skipped=True))
            # 队列里已有一条 q2 的旧记录（历史遗留），backfill 应把它删掉
            db.add(RetryQueueItem(question_id=q2.id, source="old"))
            db.commit()

            database.backfill_retry_queue()

            queue_ids = {i.question_id for i in db.exec(select(RetryQueueItem)).all()}
            assert queue_ids == {q1.id}

    def test_skipped_not_requeued_after_restart(self, test_engine):
        """回归：跳过题在重启回填后不得重新入队（需求：跳过判负，不给补答）。

        跳过记录的 score_total=0.0，回填必须先排除 skipped 再比较分数，
        否则 0 分会被误判为不及格而重新入队。
        """
        from models import Question

        with DBSession(test_engine) as db:
            q = Question(stem="被跳过的题？", answer="答案", tech_stack="python")
            db.add(q)
            db.commit()
            db.refresh(q)
            db.add(Record(session_id=1, question_id=q.id, score_total=0.0, skipped=True))
            db.commit()

            database.backfill_retry_queue()  # 模拟重启

            queue_ids = {i.question_id for i in db.exec(select(RetryQueueItem)).all()}
            assert queue_ids == set(), "跳过题重启后不得重新进入待补答队列"
