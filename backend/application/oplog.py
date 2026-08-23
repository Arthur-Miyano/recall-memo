# -*- coding: utf-8 -*-
"""操作日志写入（修复方案 §11）：敏感写操作落 operation_logs 表。

与业务操作同一 DBSession 同一事务提交：日志与操作同生共死，不出现"操作成功但无日志"。
request_id 取自 contextvar（infrastructure/requestctx.py），与响应头 X-Request-ID 一致。
"""
from typing import Any, Optional

from sqlmodel import Session as DBSession

from infrastructure.requestctx import current_request_id
from models import OperationLog


def log_operation(
    db: DBSession,
    action: str,
    target: str,
    detail: Optional[dict[str, Any]] = None,
) -> None:
    """落一条操作日志（调用方随业务一起 commit）。

    detail 只放 id 列表/数量/字段名等元信息——不得包含用户回答、答案全文、文档内容（§11）。
    """
    db.add(OperationLog(
        action=action,
        target=target,
        detail=detail,
        request_id=current_request_id(),
    ))
