# -*- coding: utf-8 -*-
"""P0 会话幂等与操作恢复（修复方案 §3.4 验收测试）：

- 相同幂等键重复/并发提交：只产生一条记录、一次推进，重放返回已保存结果；
- 不同幂等键同时提交同一题：只有一个成功，另一个返回稳定错误码；
- LLM 超时后重试不重复计入统计；LLM 成功但最终写库失败后可安全重试；
- RUNNING 操作在服务"重启"（启动清理）后恢复为可重试状态；
- 跳过和回答并发只有一个生效。
"""
import asyncio

import pytest
from sqlmodel import Session as DBSession, select

import database
from agents import orchestrator
from agents.assistant import AssistantAgent
from agents.orchestrator import OperationConflictError
from models import DailyStat, Record, Session, WorkflowOperation


def _set_score(fake_llm, total: float):
    """按加权公式反推：三维度同分则总分即该分。"""
    fake_llm.score = {
        "accuracy": total, "logic": total, "naturalness": total,
        "missed_points": [], "comment": "", "annotated_answer": None,
    }


def _start_memorize_quiz(client) -> int:
    """经 API 创建记忆训练会话并进入考核状态，返回 session_id。"""
    sid = client.post("/api/sessions", json={"mode": "memorize", "count": 3}).json()["session_id"]
    resp = client.post(f"/api/sessions/{sid}/start_quiz")
    assert resp.status_code == 200
    return sid


def _records(db, sid: int) -> list[Record]:
    return db.exec(select(Record).where(Record.session_id == sid)).all()


def _op_by_key(db, key: str) -> WorkflowOperation:
    return db.exec(select(WorkflowOperation).where(WorkflowOperation.idempotency_key == key)).one()


@pytest.fixture()
def slow_llm(monkeypatch, fake_llm):
    """在 FakeLLM 前加人为 await 点，让并发用例的两个协程确定性地交错。"""
    from llm import llm_router

    orig = fake_llm.chat

    async def chat(messages, **kwargs):
        await asyncio.sleep(0.05)
        return await orig(messages, **kwargs)

    monkeypatch.setattr(llm_router, "chat", chat)
    return fake_llm


# ---------------------------------------------------------------------------
# 相同幂等键：重复提交重放结果，并发提交只生效一次
# ---------------------------------------------------------------------------

class TestSameIdempotencyKey:
    def test_replay_returns_saved_result_without_duplicate(self, client, db, seed_questions, fake_llm):
        """同键重复提交：返回已保存结果，只产生一条记录、一次推进、一次统计。"""
        _set_score(fake_llm, 80)
        seed_questions(3)
        sid = _start_memorize_quiz(client)

        body = {"answer": "我的作答。", "idempotency_key": "k-1"}
        r1 = client.post(f"/api/sessions/{sid}/answer", json=body)
        assert r1.status_code == 200
        r2 = client.post(f"/api/sessions/{sid}/answer", json=body)
        assert r2.status_code == 200
        assert r2.json() == r1.json(), "同键重放应原样返回已保存结果"

        records = _records(db, sid)
        assert len(records) == 1, "重复提交不得产生第二条记录"
        session = db.get(Session, sid)
        assert session.current_index == 1, "进度只推进一次"
        assert session.version == 1, "版本号只在操作占位时 +1"
        stat = db.exec(select(DailyStat)).one()
        assert stat.total_count == 1, "统计只计入一次"

        op = _op_by_key(db, "k-1")
        assert op.status == "SUCCEEDED"
        assert op.result["record_id"] == r1.json()["record_id"], "操作表保存响应快照"
        assert records[0].operation_id == op.id, "记录与操作一一对应"

    async def test_concurrent_same_key_single_record(self, db, test_engine, seed_questions, slow_llm):
        """同键并发提交：一个成功、一个 OPERATION_IN_PROGRESS；事后重放仍返回已保存结果。"""
        _set_score(slow_llm, 80)
        seed_questions(3)
        created = await orchestrator.run("create_session", db=db, mode="memorize", count=3)
        sid = created["session_id"]
        await orchestrator.run("start_quiz", db=db, session_id=sid)

        with DBSession(test_engine) as db2:
            results = await asyncio.gather(
                orchestrator.run("answer", db=db, session_id=sid, answer="作答。", idempotency_key="k-c"),
                orchestrator.run("answer", db=db2, session_id=sid, answer="作答。", idempotency_key="k-c"),
                return_exceptions=True,
            )
        success = [r for r in results if isinstance(r, dict)]
        conflicts = [r for r in results if isinstance(r, OperationConflictError)]
        assert len(success) == 1, "同键并发只允许一个执行"
        assert len(conflicts) == 1 and conflicts[0].code == "OPERATION_IN_PROGRESS"

        db.expire_all()
        assert len(_records(db, sid)) == 1
        assert db.get(Session, sid).current_index == 1

        # 进行中的请求结束后，同键重试直接拿到已保存结果，不重复执行
        replay = await orchestrator.run("answer", db=db, session_id=sid, answer="作答。", idempotency_key="k-c")
        assert replay == success[0]
        db.expire_all()
        assert len(_records(db, sid)) == 1
        assert db.get(Session, sid).current_index == 1


# ---------------------------------------------------------------------------
# 不同幂等键同时提交同一题：只有一个成功
# ---------------------------------------------------------------------------

class TestDifferentKeysRace:
    async def test_one_wins_other_gets_stable_error(self, db, test_engine, seed_questions, slow_llm):
        _set_score(slow_llm, 80)
        seed_questions(3)
        created = await orchestrator.run("create_session", db=db, mode="memorize", count=3)
        sid = created["session_id"]
        await orchestrator.run("start_quiz", db=db, session_id=sid)

        with DBSession(test_engine) as db2:
            results = await asyncio.gather(
                orchestrator.run("answer", db=db, session_id=sid, answer="作答 A。", idempotency_key="k-a"),
                orchestrator.run("answer", db=db2, session_id=sid, answer="作答 B。", idempotency_key="k-b"),
                return_exceptions=True,
            )
        success = [r for r in results if isinstance(r, dict)]
        conflicts = [r for r in results if isinstance(r, OperationConflictError)]
        assert len(success) == 1, "同一题只承认一个提交"
        assert len(conflicts) == 1
        assert conflicts[0].code in ("OPERATION_IN_PROGRESS", "ANSWER_ALREADY_SUBMITTED")

        db.expire_all()
        assert len(_records(db, sid)) == 1, "只产生一条答题记录"
        assert db.get(Session, sid).current_index == 1, "进度只推进一次"
        stat = db.exec(select(DailyStat)).one()
        assert stat.total_count == 1

    def test_retry_after_session_advanced_returns_already_submitted(self, client, db, seed_questions, fake_llm):
        """FAILED 操作重试时会话已推进：返回稳定错误码 ANSWER_ALREADY_SUBMITTED。"""
        _set_score(fake_llm, 80)
        seed_questions(3)
        sid = _start_memorize_quiz(client)

        body = {"answer": "我的作答。", "idempotency_key": "k-adv"}
        assert client.post(f"/api/sessions/{sid}/answer", json=body).status_code == 200

        # 模拟"操作实际已成功但客户端未收到结果、且操作行被恢复流程标记为 FAILED"的边界
        op = _op_by_key(db, "k-adv")
        op.status = "FAILED"
        db.add(op)
        db.commit()

        r = client.post(f"/api/sessions/{sid}/answer", json=body)
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "ANSWER_ALREADY_SUBMITTED"
        db.expire_all()
        assert len(_records(db, sid)) == 1, "不得重复作答"


# ---------------------------------------------------------------------------
# 失败路径：LLM 超时重试不重复计数；最终写库失败可安全重试
# ---------------------------------------------------------------------------

class TestFailureRetry:
    def test_interview_next_question_failure_can_retry_same_submission(
        self, client, db, seed_questions, fake_llm, monkeypatch
    ):
        """回答已评分但下一题生成失败：会话仍停在原题，同键重试只记录一次。"""
        _set_score(fake_llm, 82)
        seed_questions(3)
        created = client.post("/api/sessions", json={"mode": "interview", "count": 3}).json()
        sid = created["session_id"]
        first_question_id = created["first_question"]["question_id"]

        from llm import llm_router

        original_chat = fake_llm.chat
        failed = False

        async def fail_next_question_once(messages, **kwargs):
            nonlocal failed
            system = messages[0]["content"] if messages else ""
            if "改写成自然的面试官口吻" in system and not failed:
                failed = True
                raise TimeoutError("模拟下一题生成超时")
            return await original_chat(messages, **kwargs)

        monkeypatch.setattr(llm_router, "chat", fail_next_question_once)
        body = {"answer": "面试作答。", "idempotency_key": "k-interview-next"}

        with pytest.raises(TimeoutError, match="模拟下一题生成超时"):
            client.post(f"/api/sessions/{sid}/answer", json=body)

        info = client.get(f"/api/sessions/{sid}").json()
        assert info["state"] == "INTERVIEW_ANSWER"
        assert info["current_question_id"] == first_question_id
        assert client.get(f"/api/sessions/{sid}/current").json()["question_id"] == first_question_id

        retried = client.post(f"/api/sessions/{sid}/answer", json=body)
        assert retried.status_code == 200
        replayed = client.post(f"/api/sessions/{sid}/answer", json=body)
        assert replayed.status_code == 200
        assert replayed.json() == retried.json()
        db.expire_all()
        assert len(_records(db, sid)) == 1

    def test_interview_next_question_failure_can_retry_same_skip(
        self, client, db, seed_questions, fake_llm, monkeypatch
    ):
        """跳过时下一题生成失败：不提前记失败记录，同键重试只推进一次。"""
        seed_questions(3)
        created = client.post("/api/sessions", json={"mode": "interview", "count": 3}).json()
        sid = created["session_id"]
        first_question_id = created["first_question"]["question_id"]

        from llm import llm_router

        original_chat = fake_llm.chat
        failed = False

        async def fail_next_question_once(messages, **kwargs):
            nonlocal failed
            system = messages[0]["content"] if messages else ""
            if "改写成自然的面试官口吻" in system and not failed:
                failed = True
                raise TimeoutError("模拟跳过后的下一题生成超时")
            return await original_chat(messages, **kwargs)

        monkeypatch.setattr(llm_router, "chat", fail_next_question_once)
        body = {"idempotency_key": "k-interview-skip-next"}

        with pytest.raises(TimeoutError, match="模拟跳过后的下一题生成超时"):
            client.post(f"/api/sessions/{sid}/skip", json=body)

        assert client.get(f"/api/sessions/{sid}/current").json()["question_id"] == first_question_id
        retried = client.post(f"/api/sessions/{sid}/skip", json=body)
        assert retried.status_code == 200
        replayed = client.post(f"/api/sessions/{sid}/skip", json=body)
        assert replayed.json() == retried.json()
        db.expire_all()
        assert len(_records(db, sid)) == 1

    def test_llm_timeout_retry_not_double_counted(self, client, db, seed_questions, fake_llm, monkeypatch):
        """LLM 超时：操作标记 FAILED（LLM_TIMEOUT），同键重试成功且统计只计一次。"""
        _set_score(fake_llm, 80)
        seed_questions(3)
        sid = _start_memorize_quiz(client)

        from llm import llm_router

        orig = fake_llm.chat
        state = {"failed": False}

        async def flaky(messages, **kwargs):
            system = messages[0]["content"] if messages else ""
            if "评分专家" in system and not state["failed"]:
                state["failed"] = True
                raise TimeoutError("模拟评分超时")
            return await orig(messages, **kwargs)

        monkeypatch.setattr(llm_router, "chat", flaky)

        body = {"answer": "我的作答。", "idempotency_key": "k-t"}
        # TestClient 默认重抛服务端异常；错误对外结构（4xx/5xx 分类）属 §4 范围，此处关注操作状态
        with pytest.raises(TimeoutError):
            client.post(f"/api/sessions/{sid}/answer", json=body)
        assert _records(db, sid) == [], "超时不得留下答题记录"
        assert db.exec(select(DailyStat)).all() == [], "超时不得计入统计"
        op = _op_by_key(db, "k-t")
        assert op.status == "FAILED"
        assert op.error_code == "LLM_TIMEOUT"

        r2 = client.post(f"/api/sessions/{sid}/answer", json=body)
        assert r2.status_code == 200, "FAILED 操作可同键安全重试"
        db.expire_all()
        assert len(_records(db, sid)) == 1
        assert db.get(Session, sid).current_index == 1
        stat = db.exec(select(DailyStat)).one()
        assert stat.total_count == 1, "重试不得重复计入统计"
        db.refresh(op)
        assert op.status == "SUCCEEDED"
        assert op.retry_count == 1

    def test_write_failure_retry_succeeds(self, client, db, seed_questions, fake_llm, monkeypatch):
        """LLM 成功、最终事务失败：原子回滚不留半截记录，同键重试安全完成。"""
        _set_score(fake_llm, 85)
        seed_questions(3)
        sid = _start_memorize_quiz(client)

        orig_fill = AssistantAgent.fill_scores
        calls = {"n": 0}

        def flaky_fill(self, db_, record_id, score, commit=True):
            calls["n"] += 1
            if calls["n"] == 1:
                # 此时答题记录已 flush 但未提交：抛错验证原子回滚
                raise RuntimeError("模拟最终写库失败")
            return orig_fill(self, db_, record_id, score, commit=commit)

        monkeypatch.setattr(AssistantAgent, "fill_scores", flaky_fill)

        body = {"answer": "我的作答。", "idempotency_key": "k-w"}
        with pytest.raises(RuntimeError, match="模拟最终写库失败"):
            client.post(f"/api/sessions/{sid}/answer", json=body)
        db.expire_all()
        assert _records(db, sid) == [], "最终事务失败必须整体回滚，不留半截记录"
        session = db.get(Session, sid)
        assert session.current_index == 0, "写库失败不得推进会话"
        assert session.state == "MEMORIZE_QUIZ"
        assert db.exec(select(DailyStat)).all() == [], "写库失败不得计入统计"
        op = _op_by_key(db, "k-w")
        assert op.status == "FAILED"
        assert op.error_code == "INTERNAL_ERROR"

        r2 = client.post(f"/api/sessions/{sid}/answer", json=body)
        assert r2.status_code == 200
        assert r2.json()["score"]["total"] == 85.0
        db.expire_all()
        assert len(_records(db, sid)) == 1, "重试只补一条记录"
        assert db.get(Session, sid).current_index == 1
        stat = db.exec(select(DailyStat)).one()
        assert stat.total_count == 1


# ---------------------------------------------------------------------------
# 服务重启恢复：RUNNING 操作由启动清理恢复为可重试状态
# ---------------------------------------------------------------------------

class TestRestartRecovery:
    def test_interview_scoring_state_is_restored_before_retry(self, client, db, seed_questions, fake_llm):
        """评分期间进程中断：启动恢复把会话放回等待回答态，同键可以继续。"""
        _set_score(fake_llm, 80)
        seed_questions(3)
        created = client.post("/api/sessions", json={"mode": "interview", "count": 3}).json()
        sid = created["session_id"]

        session = db.get(Session, sid)
        session.state = "INTERVIEW_SCORE"
        db.add(session)
        db.add(WorkflowOperation(
            idempotency_key="k-recover-interview",
            session_id=sid,
            question_id=session.current_question_id,
            question_index=session.current_index,
            operation_type="answer",
            status="RUNNING",
        ))
        db.commit()

        database.recover_interrupted_operations()
        info = client.get(f"/api/sessions/{sid}").json()
        assert info["state"] == "INTERVIEW_ANSWER"

        response = client.post(
            f"/api/sessions/{sid}/answer",
            json={"answer": "恢复后的作答。", "idempotency_key": "k-recover-interview"},
        )
        assert response.status_code == 200

    def test_running_operation_recovered_on_startup(self, client, db, seed_questions, fake_llm):
        """RUNNING 残留：提交返回 409 OPERATION_IN_PROGRESS；启动清理标记 FAILED 后可同键重试。"""
        _set_score(fake_llm, 80)
        seed_questions(3)
        sid = _start_memorize_quiz(client)

        # 模拟上次进程中断残留的 RUNNING 操作
        session = db.get(Session, sid)
        db.add(WorkflowOperation(
            idempotency_key="k-r",
            session_id=sid,
            question_id=session.quiz_order[session.current_index],
            question_index=session.current_index,
            operation_type="answer",
            status="RUNNING",
        ))
        db.commit()

        # 中断期间客户端重试：同键进行中 → 409
        body = {"answer": "我的作答。", "idempotency_key": "k-r"}
        r1 = client.post(f"/api/sessions/{sid}/answer", json=body)
        assert r1.status_code == 409
        assert r1.json()["detail"]["code"] == "OPERATION_IN_PROGRESS"

        # "重启"：启动清理把 PENDING/RUNNING 残留恢复为 FAILED（INTERRUPTED）
        database.recover_interrupted_operations()
        db.expire_all()
        op = _op_by_key(db, "k-r")
        assert op.status == "FAILED"
        assert op.error_code == "INTERRUPTED"

        # 恢复后同键重试安全完成
        r2 = client.post(f"/api/sessions/{sid}/answer", json=body)
        assert r2.status_code == 200
        db.expire_all()
        assert len(_records(db, sid)) == 1
        assert db.get(Session, sid).current_index == 1


# ---------------------------------------------------------------------------
# 跳过与回答并发：只有一个生效
# ---------------------------------------------------------------------------

class TestSkipAnswerRace:
    async def test_skip_and_answer_concurrent_one_wins(self, db, test_engine, seed_questions, slow_llm):
        _set_score(slow_llm, 70)
        seed_questions(3)
        created = await orchestrator.run("create_session", db=db, mode="interview", count=3)
        sid = created["session_id"]

        with DBSession(test_engine) as db2:
            results = await asyncio.gather(
                orchestrator.run("answer", db=db, session_id=sid, answer="面试作答。", idempotency_key="k-ans"),
                orchestrator.run("skip", db=db2, session_id=sid, idempotency_key="k-skp"),
                return_exceptions=True,
            )
        success = [r for r in results if isinstance(r, dict)]
        conflicts = [r for r in results if isinstance(r, OperationConflictError)]
        assert len(success) == 1, "回答与跳过只有一个生效"
        assert len(conflicts) == 1 and conflicts[0].code == "OPERATION_IN_PROGRESS"

        db.expire_all()
        records = _records(db, sid)
        assert len(records) == 1, "只产生一条记录"
        assert db.get(Session, sid).current_index == 1, "进度只推进一次"
        stat = db.exec(select(DailyStat)).one()
        assert stat.total_count == 1

    def test_skip_same_key_replay(self, client, db, seed_questions, fake_llm):
        """跳过同键重复提交：重放已保存结果，不重复记 0 分。"""
        _set_score(fake_llm, 70)
        seed_questions(3)
        sid = client.post("/api/sessions", json={"mode": "interview", "count": 3}).json()["session_id"]

        r1 = client.post(f"/api/sessions/{sid}/skip", json={"idempotency_key": "k-s"})
        assert r1.status_code == 200
        r2 = client.post(f"/api/sessions/{sid}/skip", json={"idempotency_key": "k-s"})
        assert r2.status_code == 200
        assert r2.json() == r1.json()

        records = _records(db, sid)
        assert len(records) == 1
        assert records[0].skipped is True
        assert db.get(Session, sid).current_index == 1
