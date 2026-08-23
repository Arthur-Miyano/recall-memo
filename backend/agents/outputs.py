# -*- coding: utf-8 -*-
"""LLM 结构化输出的 Pydantic 校验模型（修复方案 §4.3）。

评分结果 / 导入题目 / 助理动作三类输出统一在此约束字段、长度与取值范围；
当前各 Provider 均走文本 JSON（OpenAI 兼容协议），输出必须经过这里的同一套校验。
"""
import logging
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

logger = logging.getLogger(__name__)


def _clamp_score(value: Any) -> float:
    """得分收敛到 [0, 100]：非数字按 0 处理（与 grader 原 _clamp 口径一致）。"""
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _coerce_str_list(value: Any, max_items: int, max_len: int) -> list[str]:
    """字符串数组归一化：非数组按空数组，逐元素截断，限制条数。"""
    if not isinstance(value, list):
        return []
    return [str(p)[:max_len] for p in value if str(p).strip()][:max_items]


class ScoreOutput(BaseModel):
    """评分 Agent 输出：各维度 0~100，遗漏点/点评/标注限长。"""

    accuracy: float = 0.0
    logic: float = 0.0
    naturalness: float = 0.0
    missed_points: list[str] = Field(default_factory=list)
    comment: str = ""
    annotated_answer: Optional[str] = None

    @field_validator("accuracy", "logic", "naturalness", mode="before")
    @classmethod
    def _score_in_range(cls, v: Any) -> float:
        return _clamp_score(v)

    @field_validator("missed_points", mode="before")
    @classmethod
    def _missed_limited(cls, v: Any) -> list[str]:
        return _coerce_str_list(v, max_items=20, max_len=200)

    @field_validator("comment", mode="before")
    @classmethod
    def _comment_limited(cls, v: Any) -> str:
        return str(v or "")[:500]

    @field_validator("annotated_answer", mode="before")
    @classmethod
    def _annotated_limited(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        return str(v)[:20000]


def has_score_fields(parsed: dict[str, Any]) -> bool:
    """解析结果是否包含至少一个得分字段（没有任何得分字段视为"输出无法解析"）。"""
    return any(k in parsed for k in ("accuracy", "logic", "naturalness"))


def _keywords_6(v: Any) -> list[str]:
    return _coerce_str_list(v, max_items=6, max_len=50)


class ImportedQuestion(BaseModel):
    """导入题目（LLM 提取输出）：字段与长度约束。"""

    stem: str = Field(min_length=1, max_length=2000)
    answer: str = Field(default="", max_length=20000)
    tech_stack: str = Field(default="", max_length=50)
    knowledge_point: str = Field(default="", max_length=100)
    keywords: list[str] = Field(default_factory=list)
    difficulty: Optional[str] = None  # basic / medium / hard 之外由调用方忽略

    @field_validator("stem", mode="before")
    @classmethod
    def _stem_stripped(cls, v: Any) -> str:
        # 去首尾空白：纯空白题干由 min_length 拒收（沿用旧逻辑"无题干丢弃"）
        return str(v or "").strip()

    @field_validator("keywords", mode="before")
    @classmethod
    def _keywords_limited(cls, v: Any) -> list[str]:
        return _keywords_6(v)


class EnrichedItem(BaseModel):
    """LLM 补全输出（按 index 对齐原条目）：字段与长度约束。"""

    index: int
    answer: str = Field(default="", max_length=20000)
    tech_stack: str = Field(default="", max_length=50)
    knowledge_point: str = Field(default="", max_length=100)
    keywords: list[str] = Field(default_factory=list)
    difficulty: Optional[str] = None

    @field_validator("keywords", mode="before")
    @classmethod
    def _keywords_limited(cls, v: Any) -> list[str]:
        return _keywords_6(v)


def validate_imported_questions(data: list[Any]) -> list[dict[str, Any]]:
    """逐条校验 LLM 提取的题目数组：非法条目丢弃并记日志，返回清洗后的 dict 列表。

    只保留非空字段（沿用旧逻辑"有值才设置"的语义），stem 必填。
    """
    items: list[dict[str, Any]] = []
    for d in data:
        try:
            q = ImportedQuestion.model_validate(d)
        except ValidationError:
            logger.warning("导入题目未通过输出校验，丢弃：%s", str(d)[:100])
            continue
        items.append({k: v for k, v in q.model_dump().items() if v or k == "stem"})
    return items


# 助理动作允许编辑的字段（与 api/assistant 的协议一致）
ASSISTANT_EDIT_FIELDS = {"stem", "answer", "tech_stack", "difficulty", "keywords", "tags"}


class AssistantAction(BaseModel):
    """助理动作提议（```action 围栏块）：类型、id 列表与编辑字段约束。"""

    type: Literal["delete_questions", "edit_question", "migrate_questions"]
    question_ids: list[int] = Field(min_length=1, max_length=50)
    to_stack: Optional[str] = Field(default=None, max_length=50)
    changes: Optional[dict[str, Any]] = None
    summary: str = Field(default="", max_length=200)

    @field_validator("question_ids", mode="before")
    @classmethod
    def _ids_are_ints(cls, v: Any) -> Any:
        # mode="before"：在 pydantic 强转之前拦下字符串/bool（bool 是 int 的子类，明确拒绝）
        if not isinstance(v, list) or any(not isinstance(i, int) or isinstance(i, bool) for i in v):
            raise ValueError("question_ids 必须为整数列表")
        return v

    @model_validator(mode="after")
    def _check_by_type(self) -> "AssistantAction":
        if self.type == "edit_question":
            if len(self.question_ids) != 1:
                raise ValueError("edit_question 一次只能改一道题")
            if not self.changes or any(k not in ASSISTANT_EDIT_FIELDS for k in self.changes):
                raise ValueError("changes 含非法字段")
        if self.type == "migrate_questions" and not (self.to_stack and self.to_stack.strip()):
            raise ValueError("migrate_questions 必须给 to_stack")
        return self
