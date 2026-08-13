# -*- coding: utf-8 -*-
"""会话模型：记录一次背诵/面试会话的状态机状态。"""
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Session(SQLModel, table=True):
    """会话表：模式、状态机当前状态、当前题目，随进度持续更新。"""

    __tablename__ = "sessions"

    id: Optional[int] = Field(default=None, primary_key=True)
    mode: str = Field(index=True, description="模式：memorize（背诵）/ interview（面试）/ review（复盘）")
    # 状态机状态，见文档 3.3：IDLE / MEMORIZE_SHOW / MEMORIZE_QUIZ /
    # INTERVIEW_SELECT / INTERVIEW_ASK / INTERVIEW_ANSWER / INTERVIEW_SCORE / INTERVIEW_REVIEW
    state: str = Field(default="IDLE", description="状态机当前状态")
    current_question_id: Optional[int] = Field(default=None, description="当前题目 id")
    tech_stack: str = Field(default="", description="本次会话选择的技术栈")
    created_at: datetime = Field(default_factory=_utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=_utcnow, description="更新时间")
