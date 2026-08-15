# -*- coding: utf-8 -*-
"""strategy 覆盖：

- select_questions（记忆训练抽题）：待补答队列优先且按入队时间排序、count 限制、
  技术栈筛选（mixed/None 不限）、新题优先于有记录的题、低分题优先于高分题
  （注意：本方法不排除已掌握题，只降权排序——此为现状行为快照，待确认）；
- apply_exclusion_rule：连续 3 次不经补答成功且最近一次在 7 天窗口内才排除；
- select_review_questions：无记录返回空、按到期度排序、count 截断；
- select_interview_plan：空题库、追问链连续且带标识、题量补齐。
"""
import random
from datetime import datetime, timedelta, timezone

import pytest

from agents.base import SCORE_PASS_THRESHOLD
from agents.strategy import StrategyAgent
from models import Question, QuestionGroup, Record, RetryQueueItem


@pytest.fixture()
def strategy(fake_router):
    return StrategyAgent(fake_router)


def _add_record(db, question_id: int, score: float | None, session_id: int = 1,
                skipped: bool = False, is_retry: bool = False,
                created_at: datetime | None = None) -> Record:
    r = Record(
        session_id=session_id, question_id=question_id,
        user_answer="", score_total=score, skipped=skipped, is_retry=is_retry,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    if created_at is not None:
        r.created_at = created_at
        db.add(r)
        db.commit()
    return r


# ---------------------------------------------------------------------------
# select_questions
# ---------------------------------------------------------------------------

class TestSelectQuestions:
    def test_empty_bank_returns_empty(self, strategy, db):
        assert strategy.select_questions(db, count=3) == []

    def test_count_limit(self, strategy, db, seed_questions):
        seed_questions(6)
        assert len(strategy.select_questions(db, count=3)) == 3

    def test_count_exceeds_bank_returns_all(self, strategy, db, seed_questions):
        """题量不足时返回全部可用题（MVP 允许）。"""
        seed_questions(2)
        assert len(strategy.select_questions(db, count=5)) == 2

    def test_tech_stack_filter(self, strategy, db, seed_questions):
        seed_questions(2, stack="python")
        seed_questions(3, stack="vue3")
        picked = strategy.select_questions(db, tech_stack="vue3", count=10)
        assert len(picked) == 3
        assert all(q.tech_stack == "vue3" for q in picked)

    def test_mixed_means_no_filter(self, strategy, db, seed_questions):
        seed_questions(2, stack="python")
        seed_questions(2, stack="agent")
        assert len(strategy.select_questions(db, tech_stack="mixed", count=10)) == 4
        assert len(strategy.select_questions(db, tech_stack=None, count=10)) == 4
        assert len(strategy.select_questions(db, tech_stack="", count=10)) == 4

    def test_retry_queue_first_and_ordered_by_enqueue_time(self, strategy, db, seed_questions):
        """待补答队列优先，且队列内部按入队时间先后排序。"""
        questions = seed_questions(4)
        # 故意逆序入队：q3 先入，q1 后入
        db.add(RetryQueueItem(question_id=questions[3].id, source="interview"))
        db.commit()
        db.add(RetryQueueItem(question_id=questions[1].id, source="memorize"))
        db.commit()
        picked = strategy.select_questions(db, count=4)
        assert [q.id for q in picked[:2]] == [questions[3].id, questions[1].id], (
            "队列题应排在最前且按入队时间排序"
        )

    def test_fresh_questions_before_seen(self, strategy, db, seed_questions):
        questions = seed_questions(3)
        _add_record(db, questions[0].id, 90.0)
        picked = strategy.select_questions(db, count=3)
        # 有记录的 q0 应排在两道新题之后
        assert picked[-1].id == questions[0].id

    def test_seen_sorted_by_avg_score_asc(self, strategy, db, seed_questions):
        """历史表现差的优先：平均分升序（已掌握题只是排后，不排除——现状行为快照，待确认）。"""
        questions = seed_questions(3)
        _add_record(db, questions[0].id, 95.0)  # 已掌握
        _add_record(db, questions[1].id, 30.0)  # 薄弱
        _add_record(db, questions[2].id, 70.0)
        picked = strategy.select_questions(db, count=3)
        assert [q.id for q in picked] == [questions[1].id, questions[2].id, questions[0].id]


# ---------------------------------------------------------------------------
# apply_exclusion_rule：连续 3 次不经补答成功 + 7 天窗口
# ---------------------------------------------------------------------------

class TestExclusionRule:
    def test_three_consecutive_success_within_window_excluded(self, strategy, db, seed_questions):
        q = seed_questions(1)[0]
        now = datetime.now(timezone.utc)
        for i in range(3):
            _add_record(db, q.id, 90.0, created_at=now - timedelta(days=2, hours=i))
        assert strategy.apply_exclusion_rule(db, [q]) == []

    def test_fewer_than_three_success_kept(self, strategy, db, seed_questions):
        q = seed_questions(1)[0]
        for _ in range(2):
            _add_record(db, q.id, 90.0)
        assert strategy.apply_exclusion_rule(db, [q]) == [q]

    def test_failure_breaks_consecutive(self, strategy, db, seed_questions):
        q = seed_questions(1)[0]
        _add_record(db, q.id, 90.0)
        _add_record(db, q.id, 90.0)
        _add_record(db, q.id, 30.0)  # 最近一次失败，连续成功归零
        assert strategy.apply_exclusion_rule(db, [q]) == [q]

    def test_retry_success_not_counted(self, strategy, db, seed_questions):
        """补答成功不算"不经补答"，不打断排除的连续性要求是：补答记录直接中断计数。"""
        q = seed_questions(1)[0]
        for _ in range(2):
            _add_record(db, q.id, 90.0)
        _add_record(db, q.id, 90.0, is_retry=True)  # 最近一条是补答成功 -> 连续计数为 0
        assert strategy.apply_exclusion_rule(db, [q]) == [q]

    def test_outside_window_kept(self, strategy, db, seed_questions):
        """连续 3 次成功但最近一次出现在 7 天前：超出窗口期，恢复可抽。"""
        q = seed_questions(1)[0]
        old = datetime.now(timezone.utc) - timedelta(days=8)
        for i in range(3):
            _add_record(db, q.id, 90.0, created_at=old - timedelta(hours=i))
        assert strategy.apply_exclusion_rule(db, [q]) == [q]

    def test_no_history_kept(self, strategy, db, seed_questions):
        q = seed_questions(1)[0]
        assert strategy.apply_exclusion_rule(db, [q]) == [q]


# ---------------------------------------------------------------------------
# select_review_questions
# ---------------------------------------------------------------------------

class TestSelectReviewQuestions:
    def test_no_history_returns_empty(self, strategy, db, seed_questions):
        seed_questions(2)
        assert strategy.select_review_questions(db, count=3) == []

    def test_only_seen_questions_selected(self, strategy, db, seed_questions):
        questions = seed_questions(3)
        _add_record(db, questions[1].id, 50.0)
        picked = strategy.select_review_questions(db, count=10)
        assert [q.id for q in picked] == [questions[1].id], "只抽出现过的题"

    def test_due_ordering_older_first(self, strategy, db, seed_questions):
        """同等得分下，越久没复习的到期度越高、排越前。"""
        questions = seed_questions(2)
        now = datetime.now(timezone.utc)
        _add_record(db, questions[0].id, 50.0, created_at=now - timedelta(days=10))
        _add_record(db, questions[1].id, 50.0, created_at=now - timedelta(days=1))
        picked = strategy.select_review_questions(db, count=2)
        assert [q.id for q in picked] == [questions[0].id, questions[1].id]

    def test_due_ordering_lower_score_first(self, strategy, db, seed_questions):
        """同等时间下，历史得分越低到期度越高。"""
        questions = seed_questions(2)
        at = datetime.now(timezone.utc) - timedelta(days=5)
        _add_record(db, questions[0].id, 90.0, created_at=at)
        _add_record(db, questions[1].id, 20.0, created_at=at)
        picked = strategy.select_review_questions(db, count=2)
        assert picked[0].id == questions[1].id

    def test_count_truncation(self, strategy, db, seed_questions):
        questions = seed_questions(4)
        at = datetime.now(timezone.utc) - timedelta(days=3)
        for q in questions:
            _add_record(db, q.id, 50.0, created_at=at)
        assert len(strategy.select_review_questions(db, count=2)) == 2


# ---------------------------------------------------------------------------
# select_interview_plan
# ---------------------------------------------------------------------------

class TestSelectInterviewPlan:
    def test_empty_bank(self, strategy, db):
        plan, followup = strategy.select_interview_plan(db, count=4)
        assert plan == [] and followup == {}

    def test_plan_length_and_no_followup_without_group(self, strategy, db, seed_questions):
        random.seed(42)
        seed_questions(5)
        plan, followup = strategy.select_interview_plan(db, count=3)
        assert len(plan) == 3
        assert followup == {}, "没有追问组时不应有追问标识"

    def test_followup_chain_contiguous(self, strategy, db, seed_questions):
        """追问链按递进顺序连续出题，标识为 i/n。"""
        random.seed(42)
        questions = seed_questions(5)
        chain_ids = [questions[0].id, questions[1].id, questions[2].id]
        db.add(QuestionGroup(name="GIL 追问链", question_ids=chain_ids))
        db.commit()
        plan, followup = strategy.select_interview_plan(db, count=4)
        assert len(plan) == 4
        plan_ids = [q.id for q in plan]
        # 链在 plan 中连续且保持预设顺序
        start = plan_ids.index(chain_ids[0])
        assert plan_ids[start:start + 3] == chain_ids
        assert followup == {
            chain_ids[0]: (1, 3), chain_ids[1]: (2, 3), chain_ids[2]: (3, 3)
        }

    def test_tech_stack_filter(self, strategy, db, seed_questions):
        seed_questions(2, stack="python")
        seed_questions(3, stack="vue3")
        plan, _ = strategy.select_interview_plan(db, tech_stack="python", count=3)
        # python 只有 2 题，题量不足返回全部可用题
        assert all(q.tech_stack == "python" for q in plan)
