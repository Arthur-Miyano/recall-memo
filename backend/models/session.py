# -*- coding: utf-8 -*-
"""会话模型：记录一次背诵/面试会话的状态机状态。"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import CheckConstraint, Column, JSON
from sqlmodel import Field, SQLModel

from domain.session_state import VALID_SESSION_MODES, VALID_SESSION_STATES


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _in_check(column: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    """合法值约束（§6.3）：值集合引用 domain.session_state 的集中定义。"""
    literals = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({literals})", name=name)


class Session(SQLModel, table=True):
    """会话表：模式、状态机当前状态、当前题目，随进度持续更新。"""

    __tablename__ = "sessions"
    __table_args__ = (
        _in_check("mode", VALID_SESSION_MODES, "ck_sessions_mode"),
        _in_check("state", VALID_SESSION_STATES, "ck_sessions_state"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    mode: str = Field(index=True, description="模式：memorize（背诵）/ interview（面试）/ review（回忆）")
    # 状态机状态，合法值见 domain/session_state.py（含 EXPIRED 终态标记）
    state: str = Field(default="IDLE", description="状态机当前状态")
    current_question_id: Optional[int] = Field(default=None, foreign_key="questions.id", description="当前题目 id")
    tech_stack: str = Field(default="", description="本次会话选择的技术栈")
    # 当前活跃 Agent 名称（供前端展示与后续 SSE 推送）
    active_agent: str = Field(default="", description="当前活跃 Agent 名称")
    # 本会话抽中的题目 id（原始顺序）
    question_ids: list[int] = Field(default_factory=list, sa_column=Column(JSON), description="抽中的题目 id 列表")
    # 考核时的打乱顺序（元素为 question id）
    quiz_order: list[int] = Field(default_factory=list, sa_column=Column(JSON), description="考核出题顺序（打乱后）")
    current_index: int = Field(default=0, description="当前题在 quiz_order 中的下标")
    # 乐观锁版本号：会话写操作以 WHERE id=? AND version=? AND state=? 条件更新占位，防并发重复推进
    version: int = Field(default=0, description="乐观锁版本号（每次写操作 +1）")
    # 会话上下文：变体题干、各题作答与评分结果等临时数据
    context: dict = Field(default_factory=dict, sa_column=Column(JSON), description="会话上下文（变体/作答结果等）")
    created_at: datetime = Field(default_factory=_utcnow, description="创建时间")
    updated_at: datetime = Field(default_factory=_utcnow, description="更新时间")
