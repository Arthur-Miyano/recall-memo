# -*- coding: utf-8 -*-
"""orchestrator 状态机覆盖：

- 记忆训练全流程：create -> MEMORIZE_SHOW -> start_quiz -> MEMORIZE_QUIZ -> answer×N -> IDLE + summary；
- 非法跳转抛 StateError：未 start_quiz 就 answer / SHOW 阶段重复 start_quiz 边界 /
  review 后再 answer / EXPIRED 会话任何操作；
- 面试模式：answer 只回执不出分、skip 记 0 分且入待补答队列、终局 INTERVIEW_REVIEW + 报告；
- 待补答队列语义：答错入队、补答（记忆训练重背）及格出队；
- 创建参数校验：未知模式 / 题量范围 / memorize 只允许 3/5/7。
"""
import pytest
from sqlmodel import select

from agents import StateError, orchestrator
from models import Record, RetryQueueItem, Session


@pytest.fixture()
def orch(fake_llm):
    """全局 orchestrator 单例（fake_llm fixture 已接管其共享 router 的 chat）。"""
    return orchestrator


def _set_score(fake_llm, total: float):
    """按加权公式反推：三维度同分则总分即该分。"""
    fake_llm.score = {
        "accuracy": total, "logic": total, "naturalness": total,
        "missed_points": [], "comment": "", "annotated_answer": None,
    }


def _retry_ids(db) -> set[int]:
    return {i.question_id for i in db.exec(select(RetryQueueItem)).all()}


# ---------------------------------------------------------------------------
# 创建会话参数校验
# ---------------------------------------------------------------------------

class TestCreateValidation:
    async def test_unknown_mode(self, orch, db, seed_questions):
        seed_questions(3)
        with pytest.raises(StateError, match="未知模式"):
            await orch.run("create_session", db=db, mode="xxx")

    async def test_memorize_count_whitelist(self, orch, db, seed_questions):
        seed_questions(7)
        with pytest.raises(StateError, match="题量仅支持"):
            await orch.run("create_session", db=db, mode="memorize", count=4)

    async def test_interview_count_range(self, orch, db, seed_questions):
        seed_questions(6)
        with pytest.raises(StateError, match="题量范围"):
            await orch.run("create_session", db=db, mode="interview", count=6)

    async def test_empty_bank_rolls_back_session(self, orch, db):
        """空题库抽题失败：已建的会话行被删除，不留孤儿。"""
        with pytest.raises(StateError, match="题库为空"):
            await orch.run("create_session", db=db, mode="memorize", count=3)
        assert db.exec(select(Session)).all() == []

    async def test_review_without_history(self, orch, db, seed_questions):
        seed_questions(3)
        with pytest.raises(StateError, match="暂无历史记录"):
            await orch.run("create_session", db=db, mode="review", count=3)

    async def test_unknown_action(self, orch, db):
        with pytest.raises(StateError, match="未知动作"):
            await orch.run("fly_to_moon", db=db)


# ---------------------------------------------------------------------------
# 记忆训练全流程
# ---------------------------------------------------------------------------

class TestMemorizeFlow:
    async def test_full_flow(self, orch, db, seed_questions, fake_llm):
        questions = seed_questions(3)
        _set_score(fake_llm, 88)

        created = await orch.run("create_session", db=db, mode="memorize", count=3)
        sid = created["session_id"]
        assert created["state"] == "MEMORIZE_SHOW"
        assert len(created["questions"]) == 3
        assert all("answer" in q for q in created["questions"]), "展示阶段应带答案"
        assert all(q["retry"] is False for q in created["questions"])

        # 未 start_quiz 就 answer -> StateError
        with pytest.raises(StateError):
            await orch.run("answer", db=db, session_id=sid, answer="抢答")

        started = await orch.run("start_quiz", db=db, session_id=sid)
        assert started["state"] == "MEMORIZE_QUIZ"
        assert started["progress"] == "1/3"
        assert started["variant_stem"].startswith("（变体提问）")

        # 重复 start_quiz -> StateError
        with pytest.raises(StateError):
            await orch.run("start_quiz", db=db, session_id=sid)

        current = await orch.run("current", db=db, session_id=sid)
        assert current["progress"] == "1/3"
        assert "answer" not in current, "考核阶段不得泄露答案"
        assert "keywords" in current, "考核模式应返回关键词半开卷提示"

        # 答前两题：finished=False 且有 next_question
        for expected_progress in ("2/3", "3/3"):
            resp = await orch.run("answer", db=db, session_id=sid, answer="我的回答。")
            assert resp["score"]["total"] == 88.0
            assert resp["finished"] is False
            assert resp["next_question"]["progress"] == expected_progress

        # 最后一题：finished=True，状态回 IDLE，summary 正确
        resp = await orch.run("answer", db=db, session_id=sid, answer="我的回答。")
        assert resp["finished"] is True
        assert resp["state"] == "IDLE"
        summary = resp["summary"]
        assert summary["question_count"] == 3
        assert summary["avg_total"] == 88.0
        assert summary["reciting_count"] == 0

        # 结束后继续 answer -> StateError
        with pytest.raises(StateError):
            await orch.run("answer", db=db, session_id=sid, answer="结束后作答")

        # 三题全部及格，无人入待补答队列
        assert _retry_ids(db) == set()
        # 每条答题都落库且回填分数
        records = db.exec(select(Record).where(Record.session_id == sid)).all()
        assert len(records) == 3
        assert all(r.score_total == 88.0 for r in records)

    async def test_variant_cached_on_question(self, orch, db, seed_questions, fake_llm):
        from models import Question

        questions = seed_questions(3)
        await orch.run("create_session", db=db, mode="memorize", count=3)
        sid = db.exec(select(Session)).first().id
        await orch.run("start_quiz", db=db, session_id=sid)
        q = db.get(Question, questions[0].id)
        # 至少有一道题为 start_quiz 的当前题生成了变体并缓存入库
        variants_count = sum(len(db.get(Question, x.id).variants) for x in questions)
        assert variants_count >= 1


# ---------------------------------------------------------------------------
# 待补答队列：答错入队、补答及格出队
# ---------------------------------------------------------------------------

class TestRetryQueueSemantics:
    async def test_fail_enqueues_and_pass_dequeues(self, orch, db, seed_questions, fake_llm):
        seed_questions(3)
        _set_score(fake_llm, 30)  # 不及格

        created = await orch.run("create_session", db=db, mode="memorize", count=3)
        sid = created["session_id"]
        await orch.run("start_quiz", db=db, session_id=sid)
        failed_qids = []
        for _ in range(3):
            resp = await orch.run("answer", db=db, session_id=sid, answer="不会。")
            failed_qids.append(resp["question_id"])

        assert _retry_ids(db) == set(failed_qids), "三题全错应全部入队"

        # 新一轮记忆训练：队列题应优先被抽中且带 retry 红标
        _set_score(fake_llm, 90)  # 这次补答及格
        created2 = await orch.run("create_session", db=db, mode="memorize", count=3)
        assert all(q["retry"] for q in created2["questions"]), "队列题应带待补答红标"
        sid2 = created2["session_id"]
        await orch.run("start_quiz", db=db, session_id=sid2)
        for _ in range(3):
            await orch.run("answer", db=db, session_id=sid2, answer="这次会了。")
        assert _retry_ids(db) == set(), "补答及格后应全部出队"


# ---------------------------------------------------------------------------
# 面试模式
# ---------------------------------------------------------------------------

class TestInterviewFlow:
    async def _start_interview(self, orch, db, seed_questions, count=3):
        seed_questions(count)
        created = await orch.run("create_session", db=db, mode="interview", count=count)
        return created["session_id"], created

    async def test_create_returns_first_question(self, orch, db, seed_questions):
        sid, created = await self._start_interview(orch, db, seed_questions)
        assert created["state"] == "INTERVIEW_ANSWER"
        first = created["first_question"]
        assert first["progress"] == "1/3"
        assert "answer" not in first
        assert "score" not in first
        assert first["asked_at"], "应记录出题时间戳"

        current = await orch.run("current", db=db, session_id=sid)
        assert current["question_id"] == first["question_id"]

    async def test_answer_receipt_only_no_score(self, orch, db, seed_questions, fake_llm):
        """面试全程无反馈：answer 响应只回执已记录，不透露分数。"""
        _set_score(fake_llm, 42)
        sid, _ = await self._start_interview(orch, db, seed_questions)

        resp = await orch.run("answer", db=db, session_id=sid, answer="面试作答一。")
        assert resp["recorded"] is True
        assert "score" not in resp, "面试 answer 不得回传分数"
        assert resp["finished"] is False
        assert resp["next_question"]["progress"] == "2/3"

        # 分数其实已异步算好落库（终局复盘用）
        record = db.get(Record, resp["record_id"])
        assert record.score_total == 42.0
        # 低于 60：已悄悄入待补答队列
        assert record.question_id in _retry_ids(db)

    async def test_skip_marks_zero_and_enqueues(self, orch, db, seed_questions):
        sid, _ = await self._start_interview(orch, db, seed_questions)
        current = await orch.run("current", db=db, session_id=sid)
        qid = current["question_id"]

        resp = await orch.run("skip", db=db, session_id=sid)
        assert resp["recorded"] is True
        record = db.get(Record, resp["record_id"])
        assert record.skipped is True
        assert record.score_total == 0.0
        assert record.need_followup is False, "跳过不消耗补答机会（字段语义快照，待确认）"
        assert qid in _retry_ids(db), "跳过的题同样入待补答队列"

    async def test_skip_only_allowed_in_interview_answer(self, orch, db, seed_questions):
        """记忆训练 QUIZ 状态不允许 skip。"""
        seed_questions(3)
        created = await orch.run("create_session", db=db, mode="memorize", count=3)
        sid = created["session_id"]
        await orch.run("start_quiz", db=db, session_id=sid)
        with pytest.raises(StateError, match="不能跳过"):
            await orch.run("skip", db=db, session_id=sid)

    async def test_full_interview_to_review(self, orch, db, seed_questions, fake_llm):
        _set_score(fake_llm, 75)
        sid, _ = await self._start_interview(orch, db, seed_questions, count=3)

        resp = await orch.run("answer", db=db, session_id=sid, answer="答一。")
        assert resp["finished"] is False
        resp = await orch.run("skip", db=db, session_id=sid)
        assert resp["finished"] is False
        resp = await orch.run("answer", db=db, session_id=sid, answer="答三。")
        assert resp["finished"] is True
        assert resp["state"] == "INTERVIEW_REVIEW"

        review = await orch.run("review", db=db, session_id=sid)
        assert review["question_count"] == 3
        assert review["avg_total"] == 75.0  # 跳过的题无评分，不计入均分
        assert len(review["per_question"]) == 3
        skipped_entry = [e for e in review["per_question"] if e["skipped"]]
        assert len(skipped_entry) == 1
        assert skipped_entry[0]["score"] is None
        # 每题都带 annotated_answer 字段（fake 默认 None）
        assert all("annotated_answer" in e for e in review["per_question"])
        # 薄弱点分析来自 FakeLLM
        assert review["analysis"]["weak_points"] == ["假薄弱点"]
        # retry_list 只含跳过的那题（另两题 75 分及格）
        assert review["retry_list"] == [skipped_entry[0]["question_id"]]

        # review 后再 answer -> StateError
        with pytest.raises(StateError):
            await orch.run("answer", db=db, session_id=sid, answer="复盘后再答")
        # 幂等：再次 review 返回缓存报告
        assert (await orch.run("review", db=db, session_id=sid))["session_id"] == sid

    async def test_review_requires_finished_interview(self, orch, db, seed_questions):
        sid, _ = await self._start_interview(orch, db, seed_questions)
        with pytest.raises(StateError, match="无复盘报告"):
            await orch.run("review", db=db, session_id=sid)


# ---------------------------------------------------------------------------
# EXPIRED 会话
# ---------------------------------------------------------------------------

class TestExpiredSession:
    async def test_all_operations_rejected(self, orch, db, seed_questions, fake_llm):
        seed_questions(3)
        created = await orch.run("create_session", db=db, mode="memorize", count=3)
        sid = created["session_id"]
        await orch.run("start_quiz", db=db, session_id=sid)

        session = db.get(Session, sid)
        session.state = "EXPIRED"
        db.add(session)
        db.commit()

        with pytest.raises(StateError):
            await orch.run("answer", db=db, session_id=sid, answer="过期作答")
        with pytest.raises(StateError):
            await orch.run("current", db=db, session_id=sid)
        with pytest.raises(StateError):
            await orch.run("start_quiz", db=db, session_id=sid)
        with pytest.raises(StateError):
            await orch.run("skip", db=db, session_id=sid)
        with pytest.raises(StateError):
            await orch.run("review", db=db, session_id=sid)

    async def test_missing_session_raises(self, orch, db):
        with pytest.raises(StateError, match="会话不存在"):
            await orch.run("answer", db=db, session_id=9999, answer="x")
