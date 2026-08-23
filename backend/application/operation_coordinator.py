# -*- coding: utf-8 -*-
"""OperationCoordinator：会话写操作的版本检查、幂等、短事务与结果持久化（修复方案 §9.1）。

从 OrchestratorAgent 抽出的协调层（§3.3 的实现本体）：
- 同键重放：已成功返回已存结果 / 进行中报冲突 / 失败校验原题后安全重试；
- 短事务占位：RUNNING 操作行 + 会话版本条件更新（乐观锁）；
- 执行期不持事务，成功载荷快照进 op.result，失败标记 FAILED（可同键重试）。

状态规则见 session_workflow.py；orchestrator.py 只保留编排与 LLM 调度。
"""
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session as DBSession, select

from application.session_workflow import StateError
from infrastructure.requestctx import current_request_id
from llm.errors import (
    LLMAuthenticationError,
    LLMOutputValidationError,
    LLMRateLimitError,
    LLMRequestError,
    LLMTemporaryError,
    LLMTimeoutError,
)
from llm.router import LLMProviderUnavailableError
from models import OperationStatus, Session, WorkflowOperation

logger = logging.getLogger(__name__)


class OperationConflictError(RuntimeError):
    """幂等/并发冲突：携带稳定错误码（API 层映射为 409）。

    code 取值：OPERATION_IN_PROGRESS（同题操作进行中）/ ANSWER_ALREADY_SUBMITTED（会话已推进）。
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class OperationCoordinator:
    """幂等操作协调器：版本检查、幂等去重、短事务占位、操作结果持久化。"""

    @staticmethod
    def bump_version(db: DBSession, session: Session) -> bool:
        """乐观锁条件更新：仅当版本与状态均未变时 version+1；失败表示已被并发请求推进。"""
        result = db.execute(
            update(Session)
            .where(
                Session.id == session.id,
                Session.version == session.version,
                Session.state == session.state,
            )
            .values(version=Session.version + 1, updated_at=datetime.now(timezone.utc))
        )
        return result.rowcount == 1

    @staticmethod
    def running_operation(db: DBSession, session_id: int) -> Optional[WorkflowOperation]:
        """会话内处于 PENDING/RUNNING 的操作（同一会话的写操作必须串行）。"""
        return db.exec(
            select(WorkflowOperation)
            .where(WorkflowOperation.session_id == session_id)
            .where(WorkflowOperation.status.in_([OperationStatus.PENDING.value, OperationStatus.RUNNING.value]))
        ).first()

    def resolve_conflict(self, db: DBSession, session_id: int) -> OperationConflictError:
        """条件更新失败后重读分类：有进行中操作 → OPERATION_IN_PROGRESS；否则会话已被推进。"""
        if self.running_operation(db, session_id) is not None:
            return OperationConflictError("OPERATION_IN_PROGRESS", "当前题目有操作正在进行中，请勿重复提交")
        return OperationConflictError("ANSWER_ALREADY_SUBMITTED", "本题已提交过，会话已推进")

    @staticmethod
    def classify_operation_error(exc: Exception) -> str:
        """操作失败的稳定分类（写入 op.error_code，供排障与安全重试决策），与 llm/errors 异常体系衔接。"""
        if isinstance(exc, StateError):
            return "STATE_ERROR"
        if isinstance(exc, (LLMTimeoutError, TimeoutError)):
            return "LLM_TIMEOUT"
        if isinstance(exc, LLMRateLimitError):
            return "LLM_RATE_LIMITED"
        if isinstance(exc, LLMAuthenticationError):
            return "LLM_AUTH_FAILED"
        if isinstance(exc, LLMRequestError):
            return "LLM_REQUEST_INVALID"
        if isinstance(exc, LLMOutputValidationError):
            return "LLM_OUTPUT_INVALID"
        if isinstance(exc, (LLMTemporaryError, LLMProviderUnavailableError)):
            return "LLM_UNAVAILABLE"
        return "INTERNAL_ERROR"

    async def run_operation(
        self,
        db: DBSession,
        session: Session,
        operation_type: str,
        idempotency_key: Optional[str],
        expected_states: set[str],
        executor: Any,
    ) -> dict[str, Any]:
        """幂等执行一次会话写操作。

        流程（修复方案 §3.3）：
        1. 同键重放：已成功 → 直接返回已保存结果；进行中 → OPERATION_IN_PROGRESS；
           失败 → 校验会话仍停在原题后安全重试（retry_count+1）；
        2. 短事务占位：建 RUNNING 操作行 + WHERE id/version/state 条件更新会话版本；
        3. 提交后不持事务执行 executor（LLM 调用 + 最终原子写库），返回响应载荷；
        4. 成功载荷快照进 op.result；任何失败回滚并把操作标记 FAILED（可同键重试）。
        """
        # 无键直连（旧客户端/测试）：服务端生成一次性键，等价于不做幂等
        key = idempotency_key or f"srv-{uuid4().hex}"
        now = datetime.now(timezone.utc)
        op = db.exec(
            select(WorkflowOperation).where(WorkflowOperation.idempotency_key == key)
        ).first()
        if op is not None:
            if op.status == OperationStatus.SUCCEEDED.value:
                logger.info("同键重放 type=%s session=%s key=%s request_id=%s",
                            operation_type, session.id, key, current_request_id())
                return op.result
            if op.status in (OperationStatus.PENDING.value, OperationStatus.RUNNING.value):
                db.rollback()  # 释放读事务，避免阻塞进行中的写方
                raise OperationConflictError("OPERATION_IN_PROGRESS", "相同操作正在进行中，请勿重复提交")
            # FAILED 重试：会话必须仍停在原题，否则视为已推进
            if session.state not in expected_states or session.current_index != op.question_index:
                db.rollback()
                raise OperationConflictError("ANSWER_ALREADY_SUBMITTED", "会话已推进，本题已有作答结果")
            op.status = OperationStatus.RUNNING.value
            op.error_code = None
            op.retry_count += 1
            op.updated_at = now
            db.add(op)
        else:
            # 新操作：先挡住明显的进行中冲突，再建行并以条件更新占位
            if self.running_operation(db, session.id) is not None:
                db.rollback()
                raise OperationConflictError("OPERATION_IN_PROGRESS", "当前题目有操作正在进行中，请勿重复提交")
            question_id = None
            if session.quiz_order and session.current_index < len(session.quiz_order):
                question_id = session.quiz_order[session.current_index]
            op = WorkflowOperation(
                idempotency_key=key,
                session_id=session.id,
                question_id=question_id,
                question_index=session.current_index,
                operation_type=operation_type,
                status=OperationStatus.RUNNING.value,
            )
            db.add(op)
        if not self.bump_version(db, session):
            db.rollback()
            raise self.resolve_conflict(db, session.id)
        try:
            db.commit()
        except IntegrityError:
            # 并发下同键插入撞唯一索引：以库中已有的那一条为准
            db.rollback()
            existing = db.exec(
                select(WorkflowOperation).where(WorkflowOperation.idempotency_key == key)
            ).first()
            if existing is not None and existing.status == OperationStatus.SUCCEEDED.value:
                return existing.result
            db.rollback()
            raise OperationConflictError("OPERATION_IN_PROGRESS", "相同操作正在进行中，请勿重复提交")
        db.refresh(session)
        db.refresh(op)
        logger.info("操作开始 type=%s session=%s key=%s request_id=%s",
                    operation_type, session.id, key, current_request_id())

        try:
            payload = await executor(session, op)
        except Exception as exc:
            db.rollback()
            op.status = OperationStatus.FAILED.value
            op.error_code = self.classify_operation_error(exc)
            op.updated_at = datetime.now(timezone.utc)
            db.add(op)
            db.commit()
            logger.warning("操作失败 type=%s session=%s key=%s error=%s request_id=%s",
                           operation_type, session.id, key, op.error_code, current_request_id())
            raise
        op.status = OperationStatus.SUCCEEDED.value
        op.result = payload
        op.updated_at = datetime.now(timezone.utc)
        db.add(op)
        db.commit()
        logger.info("操作成功 type=%s session=%s key=%s request_id=%s",
                    operation_type, session.id, key, current_request_id())
        return payload
