# -*- coding: utf-8 -*-
"""grader 覆盖：

- _validate_annotated：标记配对正确通过、未闭合/交叉/改动原文降级 None、
  嵌套规则、无标记按 None、非字符串输入；
- detect_reciting：重合率与 0.3 阈值；
- score：评分 JSON 解析（正常 / 带 markdown 围栏 / 坏 JSON 容错），
  加权总分、背诵时自然度强制 <=5、_clamp 收敛越界分。
"""
import json

from agents.grader import GraderAgent
from models import Question


def _make_grader(fake_router) -> GraderAgent:
    return GraderAgent(fake_router)


def _question(answer: str = "标准答案原文。") -> Question:
    return Question(stem="测试题干？", answer=answer, tech_stack="python", keywords=[])


# ---------------------------------------------------------------------------
# _validate_annotated
# ---------------------------------------------------------------------------

class TestValidateAnnotated:
    def test_valid_omiss_marker_passes(self):
        standard = "GIL 是全局解释器锁，同一时刻只允许一个线程执行字节码。"
        annotated = "GIL 是[[omiss]]全局解释器锁[[/omiss]]，同一时刻只允许一个线程执行字节码。"
        assert GraderAgent._validate_annotated(annotated, standard) == annotated

    def test_valid_both_marker_types_pass(self):
        standard = "甲乙丙丁"
        annotated = "[[omiss]]甲[[/omiss]]乙[[logic]]丙[[/logic]]丁"
        assert GraderAgent._validate_annotated(annotated, standard) == annotated

    def test_unclosed_marker_returns_none(self):
        standard = "甲乙丙"
        assert GraderAgent._validate_annotated("[[omiss]]甲乙丙", standard) is None
        assert GraderAgent._validate_annotated("甲[[/omiss]]乙丙", standard) is None

    def test_crossing_markers_returns_none(self):
        """交叉标记 [[omiss]]…[[logic]]…[[/omiss]]…[[/logic]] 非法。"""
        standard = "甲乙丙丁"
        annotated = "[[omiss]]甲[[logic]]乙[[/omiss]]丙[[/logic]]丁"
        assert GraderAgent._validate_annotated(annotated, standard) is None

    def test_nested_same_tag_allowed(self):
        """同标签嵌套配对合法（栈式校验允许）。"""
        standard = "甲乙丙丁"
        annotated = "[[omiss]]甲[[omiss]]乙丙[[/omiss]]丁[[/omiss]]"
        assert GraderAgent._validate_annotated(annotated, standard) == annotated

    def test_modified_original_returns_none(self):
        """标记之外改动了原文（哪怕一个标点）：降级 None。"""
        standard = "GIL 是全局解释器锁。"
        annotated = "GIL 是[[omiss]]全局解释器锁[[/omiss]]！"  # 句号被改成叹号
        assert GraderAgent._validate_annotated(annotated, standard) is None

    def test_extra_text_outside_markers_returns_none(self):
        standard = "原文"
        assert GraderAgent._validate_annotated("原文[[omiss]][[/omiss]]多了字", standard) is None

    def test_no_markers_returns_none(self):
        """去掉标记后与原文一致但没有任何标记 = 没标注，按 None。"""
        standard = "纯原文"
        assert GraderAgent._validate_annotated("纯原文", standard) is None

    def test_non_string_and_empty_inputs(self):
        assert GraderAgent._validate_annotated(None, "原文") is None
        assert GraderAgent._validate_annotated(123, "原文") is None
        assert GraderAgent._validate_annotated("   ", "原文") is None


# ---------------------------------------------------------------------------
# detect_reciting
# ---------------------------------------------------------------------------

class TestDetectReciting:
    def test_verbatim_copy_is_reciting(self):
        answer = "GIL 是 CPython 的全局解释器锁，同一时刻只允许一个线程执行 Python 字节码。"
        ratio, is_reciting = GraderAgent.detect_reciting(answer, answer)
        assert ratio == 1.0
        assert is_reciting is True

    def test_unrelated_answer_not_reciting(self):
        ratio, is_reciting = GraderAgent.detect_reciting(
            "我不太确定，可能是跟线程有关的东西吧。",
            "GIL 是 CPython 的全局解释器锁，同一时刻只允许一个线程执行 Python 字节码。",
        )
        assert ratio < 0.3
        assert is_reciting is False


# ---------------------------------------------------------------------------
# score：JSON 解析容错与加权总分
# ---------------------------------------------------------------------------

class TestScore:
    async def test_normal_json(self, fake_router, fake_llm):
        fake_llm.score = {
            "accuracy": 90, "logic": 60, "naturalness": 30,
            "missed_points": ["GC"], "comment": "还行", "annotated_answer": None,
        }
        # 用户回答与标准答案零公共字符，避免误触发反背诵检测
        result = await _make_grader(fake_router).score(_question(), "我觉得大概是一种并发限制机制")
        # 加权：90*0.5 + 60*0.3 + 30*0.2 = 45 + 18 + 6 = 69
        assert result["total"] == 69.0
        assert result["accuracy"] == 90.0
        assert result["missed_points"] == ["GC"]
        assert result["is_reciting"] is False
        assert result["annotated_answer"] is None

    async def test_markdown_fenced_json(self, fake_router, fake_llm):
        """带 ```json 围栏的输出也能解析。"""
        fake_llm.score_raw = '```json\n{"accuracy": 100, "logic": 100, "naturalness": 100, '
        fake_llm.score_raw += '"missed_points": [], "comment": "满分", "annotated_answer": null}\n```'
        result = await _make_grader(fake_router).score(_question(), "完全不一样的回答。")
        assert result["total"] == 100.0

    async def test_json_with_surrounding_text(self, fake_router, fake_llm):
        fake_llm.score_raw = '好的，评分如下：{"accuracy": 50, "logic": 50, "naturalness": 50} 完毕。'
        result = await _make_grader(fake_router).score(_question(), "不重合的回答。")
        assert result["total"] == 50.0

    async def test_broken_json_falls_back_to_zero(self, fake_router, fake_llm):
        """坏 JSON：parse_json_object 返回 {}，各维度收敛为 0。"""
        fake_llm.score_raw = "这根本不是 JSON"
        result = await _make_grader(fake_router).score(_question(), "不重合的回答。")
        assert result["total"] == 0.0
        assert result["accuracy"] == 0.0
        assert result["comment"] == ""
        assert result["missed_points"] == []

    async def test_scores_clamped_to_0_100(self, fake_router, fake_llm):
        fake_llm.score = {"accuracy": 150, "logic": -20, "naturalness": "abc", "missed_points": [], "comment": ""}
        result = await _make_grader(fake_router).score(_question(), "不重合的回答。")
        assert result["accuracy"] == 100.0
        assert result["logic"] == 0.0
        assert result["naturalness"] == 0.0

    async def test_reciting_forces_naturalness_down(self, fake_router, fake_llm):
        """整段照抄标准答案：无论 LLM 给多少分，naturalness 强制 <=5。"""
        standard = "GIL 是 CPython 的全局解释器锁，同一时刻只允许一个线程执行 Python 字节码。"
        fake_llm.score = {
            "accuracy": 100, "logic": 100, "naturalness": 100,
            "missed_points": [], "comment": "", "annotated_answer": None,
        }
        result = await _make_grader(fake_router).score(_question(standard), standard)
        assert result["is_reciting"] is True
        assert result["naturalness"] == 5.0
        # 总分：100*0.5 + 100*0.3 + 5*0.2 = 81
        assert result["total"] == 81.0

    async def test_valid_annotated_answer_kept(self, fake_router, fake_llm):
        standard = "要点一。要点二。"
        annotated = "要点一。[[omiss]]要点二。[[/omiss]]"
        fake_llm.score = {
            "accuracy": 80, "logic": 80, "naturalness": 80,
            "missed_points": ["要点二"], "comment": "", "annotated_answer": annotated,
        }
        result = await _make_grader(fake_router).score(_question(standard), "只答了要点一，文字完全不同。")
        assert result["annotated_answer"] == annotated

    async def test_invalid_annotated_answer_degraded(self, fake_router, fake_llm):
        fake_llm.score = {
            "accuracy": 80, "logic": 80, "naturalness": 80,
            "missed_points": [], "comment": "",
            "annotated_answer": "要点一。[[omiss]]要点二",  # 未闭合
        }
        result = await _make_grader(fake_router).score(_question("要点一。要点二。"), "不重合的回答。")
        assert result["annotated_answer"] is None
