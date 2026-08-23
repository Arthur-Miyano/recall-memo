# -*- coding: utf-8 -*-
"""工作流操作模型：会话写操作的幂等键、执行状态与结果快照。

操作状态（PENDING/RUNNING/SUCCEEDED/FAILED）与会话业务状态（SessionState）分开管理：
会话状态机只描述业务进度，操作层单独追踪一次提交的执行与重试，见修复方案 §3。
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OperationType(str, Enum):
    """操作类型。"""

    ANSWER = "answer"
    SKIP = "skip"
    GENERATE_QUESTION = "generate_question"
    REVIEW = "review"


class OperationStatus(str, Enum):
    """操作执行状态（与会话业务状态分离）。"""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class WorkflowOperation(SQLModel, table=True):
    """工作流操作表：一次会话写操作的幂等占位与执行结果。"""

    __tablename__ = "workflow_operations"

    id: Optional[int] = Field(default=None, primary_key=True)
    # 客户端生成的幂等键：一次提交一个键，失败重试复用同键；唯一索引保证并发下同键只落一条
    idempotency_key: str = Field(unique=True, description="客户端幂等键（重试复用同键）")
    session_id: int = Field(index=True, foreign_key="sessions.id", description="所属会话 id")
    question_id: Optional[int] = Field(default=None, foreign_key="questions.id", description="操作针对的题目 id")
    question_index: Optional[int] = Field(default=None, description="提交时的会话题目序号")
    operation_type: str = Field(description="answer / skip / generate_question / review")
    status: str = Field(default=OperationStatus.PENDING.value, index=True, description="PENDING / RUNNING / SUCCEEDED / FAILED")
    # 成功操作的最小响应快照：同键重放直接返回，不重复执行
    result: Optional[dict] = Field(default=None, sa_column=Column(JSON), description="成功操作的响应快照")
    error_code: Optional[str] = Field(default=None, description="稳定的失败分类（LLM_TIMEOUT / LLM_UNAVAILABLE / INTERRUPTED 等）")
    retry_count: int = Field(default=0, description="已重试次数")
    created_at: datetime = Field(default_factory=_utcnow, description="创建时间（UTC）")
    updated_at: datetime = Field(default_factory=_utcnow, description="更新时间（UTC）")
