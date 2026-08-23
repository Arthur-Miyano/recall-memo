# -*- coding: utf-8 -*-
"""操作日志模型（修复方案 §11）：删除/批量迁移/助理动作等敏感写操作的审计记录。

新表由 init_db 的 create_all 自动创建（新库/存量库都覆盖，无需版本迁移——
版本迁移只用于给既有表改列，见 database.py docstring）。
"""
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OperationLog(SQLModel, table=True):
    """操作日志表：操作类型、目标、明细、发起请求 request_id、时间。"""

    __tablename__ = "operation_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    action: str = Field(
        index=True,
        description="操作类型：delete_question / edit_question / migrate_questions / assistant_action_proposed",
    )
    target: str = Field(default="", description="操作目标摘要（题目 id / 目标栈 / 动作类型）")
    # 明细只放 id 列表、数量、字段名等元信息：不记用户回答、标准答案全文、导入文档内容（§11 脱敏）
    detail: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON), description="操作明细（元信息）")
    request_id: Optional[str] = Field(default=None, index=True, description="发起请求的 request_id（内部/离线操作为空）")
    created_at: datetime = Field(default_factory=_utcnow, description="操作时间（UTC）")
