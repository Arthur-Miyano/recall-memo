# -*- coding: utf-8 -*-
"""会话模型：记录一次背诵/面试会话的状态机状态。"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Session(SQLModel, table=True):
    """会话表：模式、状态机当前状态、当前题目，随进度持续更新。"""

    __tablename__ = "sessions"

    id: Optional[int] = Field(default=None, primary_key=True)
    mode: str = Field(index=True, description="模式：memorize（背诵）/ interview（面试）/ review（回忆）")
    # 状态机状态，见文档 3.3：IDLE / MEMORIZE_SHOW / MEMORIZE_QUIZ /
    # INTERVIEW_SELECT / INTERVIEW_ASK / INTERVIEW_ANSWER / INTERVIEW_SCORE / INTERVIEW_REVIEW /
    # REVIEW_SHOW / REVIEW_QUIZ（回忆模式，预留）
    state: str = Field(default="IDLE", description="状态机当前状态")
    current_question_id: Optional[int] = Field(default=None, description="当前题目 id")
    tech_stack: str = Field(default="", description="本次会话选择的技术栈")
    # 当前活跃 Agent 名称（供前端展示与后续 SSE 推送）
    active_agent: str = Field(default="", description="当前活跃 Agent 名称")
    # 本会话抽中的题目 id（原始顺序）
    question_ids: list[int] = Field(default_factory=list, sa_column=Column(JSON), description="抽中的题目 id 列表")
    # 考核时的打乱顺序（元素为 question id）
    quiz_order: list[int] = Field(default_factory=list, sa_column=Column(JSON), description="考核出题顺序（打乱后）")
    current_index: int = Field(default=0, description="当前题在 quiz_order 中的下标")
    # 会话上下文：变体题干、各题作答与评分结果等临时数据
    context: dict = Field(default_factory=dict, sa_column=Column(JSON), description="会话上下文（变体/作答结果等）")
    created_at: datetime = Field(default_factory=_utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=_utcnow, description="更新时间")
