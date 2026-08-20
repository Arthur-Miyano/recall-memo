# -*- coding: utf-8 -*-
"""增量小表：重点背诵标记、待补答队列。

独立建表而非改 Question/Record 结构：bagu.db 已有数据，create_all 不会给旧表加列。
"""
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class QuestionFocus(SQLModel, table=True):
    """重点背诵标记表：存在的 question_id 即为被圈选的重点题。"""

    __tablename__ = "question_focus"

    id: Optional[int] = Field(default=None, primary_key=True)
    question_id: int = Field(unique=True, index=True, description="题目 id")
    created_at: datetime = Field(default_factory=_utcnow, description="标记时间")


class RetryQueueItem(SQLModel, table=True):
    """待补答队列表：面试/考核答错的题入队（跳过不入队），记忆训练中重背后出队（每题仅一次补答机会）。"""

    __tablename__ = "retry_queue"

    id: Optional[int] = Field(default=None, primary_key=True)
    question_id: int = Field(unique=True, index=True, description="题目 id")
    source: str = Field(default="", description="入队来源：interview / memorize / review")
    created_at: datetime = Field(default_factory=_utcnow, description="入队时间")
