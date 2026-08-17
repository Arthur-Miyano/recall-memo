# -*- coding: utf-8 -*-
"""笔记表：背诵时划句收藏的片段 + 文档式整理（相关性知识记到一起）。"""
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Note(SQLModel, table=True):
    """笔记文档：一篇笔记聚合若干划句片段与手写内容，纯文本存储（前端负责排版）。"""

    __tablename__ = "notes"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(default="未命名笔记", description="笔记标题")
    content: str = Field(default="", description="笔记正文（纯文本，划句以 > 引用块追加）")
    created_at: datetime = Field(default_factory=_utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=_utcnow, description="最近编辑时间")
