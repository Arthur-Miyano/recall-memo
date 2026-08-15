# -*- coding: utf-8 -*-
"""记忆助手对话历史表：水墨螃蟹面板的一问一答持久化。"""
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChatMessage(SQLModel, table=True):
    """对话消息表：用户提问与助手回复各一条，思考过程（JSON 数组字符串）存在回复那条上。"""

    __tablename__ = "chat_messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    role: str = Field(index=True, description="消息角色：user / assistant")
    content: str = Field(default="", description="消息原文")
    thinking: Optional[str] = Field(default=None, description="思考过程（JSON 数组字符串，仅 assistant 消息有）")
    created_at: datetime = Field(default_factory=_utcnow, description="发送时间戳")
