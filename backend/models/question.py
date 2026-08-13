# -*- coding: utf-8 -*-
"""题库相关模型：题目表、追问组表。"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Question(SQLModel, table=True):
    """题目表：标准题干 + 标准答案，技术栈/难度/关键词/标签。"""

    __tablename__ = "questions"

    id: Optional[int] = Field(default=None, primary_key=True)
    stem: str = Field(description="标准题干")
    answer: str = Field(description="标准答案")
    tech_stack: str = Field(index=True, description="技术栈：python / agent / vue3")
    difficulty: str = Field(default="medium", index=True, description="难度：basic / medium / hard")
    keywords: list[str] = Field(default_factory=list, sa_column=Column(JSON), description="关键词列表")
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON), description="标签列表")
    created_at: datetime = Field(default_factory=_utcnow, description="创建时间")


class QuestionGroup(SQLModel, table=True):
    """追问组表：同一主线题的递进追问链。"""

    __tablename__ = "question_groups"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(default="", description="追问组名称")
    # 组内题目 id 列表，按递进顺序排列，如 [12, 45, 46]
    question_ids: list[int] = Field(default_factory=list, sa_column=Column(JSON), description="组内题目 id 列表（按递进顺序）")
    created_at: datetime = Field(default_factory=_utcnow, description="创建时间")
