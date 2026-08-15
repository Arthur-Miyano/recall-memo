# -*- coding: utf-8 -*-
"""记忆助手对话持久化：水墨螃蟹面板的多会话 + 一问一答消息。

- ChatSession：一个对话（标题取首条用户消息截断，updated_at 随新消息刷新，列表按它倒序）。
- ChatMessage：用户提问与助手回复各一条，思考过程（JSON 数组字符串）存在回复那条上；
  session_id 指向所属会话（旧库轻量迁移补列，历史消息归入自动创建的"默认对话"）。
"""
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChatSession(SQLModel, table=True):
    """对话会话表：标题默认"新对话"，首条用户消息落库时截断为标题。"""

    __tablename__ = "chat_sessions"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(default="新对话", description="会话标题（首条用户消息截断）")
    created_at: datetime = Field(default_factory=_utcnow, description="创建时间戳")
    updated_at: datetime = Field(default_factory=_utcnow, description="最近一条消息时间戳（列表排序键）")


class ChatMessage(SQLModel, table=True):
    """对话消息表：用户提问与助手回复各一条，思考过程（JSON 数组字符串）存在回复那条上。"""

    __tablename__ = "chat_messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: Optional[int] = Field(
        default=None, foreign_key="chat_sessions.id", index=True,
        description="所属会话 id（旧数据迁移归入默认对话）",
    )
    role: str = Field(index=True, description="消息角色：user / assistant")
    content: str = Field(default="", description="消息原文")
    thinking: Optional[str] = Field(default=None, description="思考过程（JSON 数组字符串，仅 assistant 消息有）")
    created_at: datetime = Field(default_factory=_utcnow, description="发送时间戳")
