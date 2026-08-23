# -*- coding: utf-8 -*-
"""总控 Agent（Orchestrator）：手写状态机，解析 API 意图，编排其余 Agent 的调用链。"""
import random
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session as DBSession, select

import events
from domain.session_state import SessionState  # noqa: F401  re-export：旧导入路径 agents.orchestrator.SessionState 仍可用
from llm import llm_router
from llm.errors import (
    LLMAuthenticationError,
    LLMOutputValidationError,
    LLMRateLimitError,
    LLMRequestError,
    LLMTemporaryError,
    LLMTimeoutError,
)
from llm.router import LLMProviderUnavailableError
from models import OperationStatus, OperationType, Question, RetryQueueItem, Session, WorkflowOperation

from .assistant import AssistantAgent
from .base import BaseAgent
from .grader import GraderAgent
from .interviewer import InterviewerAgent
from .strategy import StrategyAgent


class StateError(RuntimeError):
    """非法的状态跳转或会话状态不满足操作要求。"""


class OperationConflictError(RuntimeError):
    """幂等/并发冲突：携带稳定错误码（API 层映射为 409）。

    code 取值：OPERATION_IN_PROGRESS（同题操作进行中）/ ANSWER_ALREADY_SUBMITTED（会话已推进）。
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# 各模式的题量限制，见文档 2.3
_MODE_COUNT_RULES = {
    "memorize": (3, 7, {3, 5, 7}),
    "interview": (3, 5, None),
    "review": (1, 10, None),
}

# 记忆训练与回忆模式共用的"展示 → 考核"状态对
_SHOW_STATES = {"memorize": SessionState.MEMORIZE_SHOW, "review": SessionState.REVIEW_SHOW}
_QUIZ_STATES = {"memorize": SessionState.MEMORIZE_QUIZ, "review": SessionState.REVIEW_QUIZ}


class OrchestratorAgent(BaseAgent):
    """总控 Agent：用户请求唯一入口，维护状态机并持久化到 sessions 表。"""

    name = "总控"

    def __init__(self, router=llm_router) -> None:
        super().__init__(router)
        # 持有的子 Agent（共享同一个 LLMRouter）
        self.interviewer = InterviewerAgent(router)
        self.strategy = StrategyAgent(router)
        self.grader = GraderAgent(router)
        self.assistant = AssistantAgent(router)

    async def run(self, action: str, **kwargs: Any) -> Any:
        """统一入口：按动作名解析意图并分发到对应处理流程。"""
        handlers = {
            "create_session": self.create_session,
            "start_quiz": self.start_quiz,
            "current": self.get_current,
            "answer": self.submit_answer,
            "skip": self.skip_question,
            "review": self.get_review,
        }
        handler = handlers.get(action)
        if handler is None:
            raise StateError(f"未知动作：{action}")
        return await handler(**kwargs)

    # ------------------------------------------------------------------
    # 状态机工具
    # ------------------------------------------------------------------

    def _transition(self, db: DBSession, session: Session, state: SessionState, active_agent: str) -> None:
        """状态变更：写入 sessions 表，并记录当前活跃 Agent 名称（供后续 SSE）。"""
        session.state = state.value
        session.active_agent = active_agent
        session.updated_at = datetime.now(timezone.utc)
        db.add(session)
        db.commit()
        db.refresh(session)

    def _get_session(self, db: DBSession, session_id: int) -> Session:
        session = db.get(Session, session_id)
        if session is None:
            raise StateError(f"会话不存在：{session_id}")
        return session

    @staticmethod
    def _save_context(db: DBSession, session: Session, **updates: Any) -> None:
        """更新会话上下文字段（整体重新赋值触发 JSON 列更新）。"""
        session.context = {**session.context, **updates}
        db.add(session)
        db.commit()
        db.refresh(session)

    # ------------------------------------------------------------------
    # 幂等操作协调（修复方案 §3.3）：短事务占位 → 不持事务执行 → 原子收尾
    # ------------------------------------------------------------------

    @staticmethod
    def _bump_version(db: DBSession, session: Session) -> bool:
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
    def _running_operation(db: DBSession, session_id: int) -> Optional[WorkflowOperation]:
        """会话内处于 PENDING/RUNNING 的操作（同一会话的写操作必须串行）。"""
        return db.exec(
            select(WorkflowOperation)
            .where(WorkflowOperation.session_id == session_id)
            .where(WorkflowOperation.status.in_([OperationStatus.PENDING.value, OperationStatus.RUNNING.value]))
        ).first()

    def _resolve_conflict(self, db: DBSession, session_id: int) -> OperationConflictError:
        """条件更新失败后重读分类：有进行中操作 → OPERATION_IN_PROGRESS；否则会话已被推进。"""
        if self._running_operation(db, session_id) is not None:
            return OperationConflictError("OPERATION_IN_PROGRESS", "当前题目有操作正在进行中，请勿重复提交")
        return OperationConflictError("ANSWER_ALREADY_SUBMITTED", "本题已提交过，会话已推进")

    @staticmethod
    def _classify_operation_error(exc: Exception) -> str:
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

    async def _run_operation(
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
            if self._running_operation(db, session.id) is not None:
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
        if not self._bump_version(db, session):
            db.rollback()
            raise self._resolve_conflict(db, session.id)
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

        try:
            payload = await executor(session, op)
        except Exception as exc:
            db.rollback()
            op.status = OperationStatus.FAILED.value
            op.error_code = self._classify_operation_error(exc)
            op.updated_at = datetime.now(timezone.utc)
            db.add(op)
            db.commit()
            raise
        op.status = OperationStatus.SUCCEEDED.value
        op.result = payload
        op.updated_at = datetime.now(timezone.utc)
        db.add(op)
        db.commit()
        return payload

    # ------------------------------------------------------------------
    # 创建会话：按模式分发
    # ------------------------------------------------------------------

    async def create_session(
        self,
        db: DBSession,
        mode: str = "memorize",
        tech_stack: Optional[str] = None,
        count: int = 3,
    ) -> dict[str, Any]:
        """开始会话：按模式抽题并进入对应初始状态。"""
        if mode not in _MODE_COUNT_RULES:
            raise StateError(f"未知模式：{mode}（支持 memorize / interview / review）")
        low, high, allowed = _MODE_COUNT_RULES[mode]
        if allowed is not None and count not in allowed:
            raise StateError(f"记忆训练模式题量仅支持 {sorted(allowed)}")
        if not low <= count <= high:
            raise StateError(f"该模式题量范围为 {low}~{high}")

        session = Session(mode=mode, tech_stack=tech_stack or "mixed")
        db.add(session)
        db.commit()
        db.refresh(session)

        try:
            if mode == "interview":
                return await self._create_interview(db, session, tech_stack, count)
            return await self._create_show(db, session, tech_stack, count)
        except StateError:
            # 抽题失败（空题库/无历史记录等）：删除已建的会话行，避免留下孤儿会话
            db.delete(session)
            db.commit()
            raise

    async def _create_show(
        self, db: DBSession, session: Session, tech_stack: Optional[str], count: int
    ) -> dict[str, Any]:
        """记忆训练 / 回忆模式公共入口：抽题 → 进入 *_SHOW，返回题干+答案供记忆。"""
        mode = session.mode
        # 策略 Agent 抽题期间，活跃 Agent 记为"策略"
        self._transition(db, session, SessionState.IDLE, self.strategy.name)
        events.publish(self.strategy.name, "抽题中…")
        if mode == "review":
            # 回忆模式：只抽历史记录中出现过的题，按到期度排序
            questions = self.strategy.select_review_questions(db, count=count)
            if not questions:
                raise StateError("暂无历史记录，请先完成记忆训练")
        else:
            questions = await self.strategy.run(db, tech_stack=tech_stack, count=count)
            if not questions:
                raise StateError("题库为空或该技术栈下没有题目，请先导入题库")

        session.question_ids = [q.id for q in questions]
        db.add(session)
        db.commit()

        # 抽题完成，进入展示阶段（题干+答案可见）；待补答队列中的题打上「待补答」红标
        retry_ids = {r.question_id for r in db.exec(select(RetryQueueItem)).all()}
        self._transition(db, session, _SHOW_STATES[mode], self.name)
        return {
            "session_id": session.id,
            "mode": session.mode,
            "state": session.state,
            "active_agent": session.active_agent,
            "questions": [
                {**self._question_payload(q, with_answer=True), "retry": q.id in retry_ids}
                for q in questions
            ],
        }

    async def _create_interview(
        self, db: DBSession, session: Session, tech_stack: Optional[str], count: int
    ) -> dict[str, Any]:
        """面试模拟入口：混合结构抽题（追问链 + 独立单题）→ 直接出第一题。"""
        self._transition(db, session, SessionState.INTERVIEW_SELECT, self.strategy.name)
        events.publish(self.strategy.name, "抽题中…")
        plan, followup = self.strategy.select_interview_plan(db, tech_stack=tech_stack, count=count)
        if not plan:
            raise StateError("题库为空或该技术栈下没有题目，请先导入题库")

        session.question_ids = [q.id for q in plan]
        session.quiz_order = [q.id for q in plan]  # 面试不打乱，按策略编排的顺序出题
        session.current_index = 0
        db.add(session)
        db.commit()
        # followup: {question_id: "1/2"}；asked_at：各题出题时间戳（时间压力计时基准）
        self._save_context(
            db, session,
            variants={}, results=[], retried=[],
            followup={str(qid): f"{i}/{n}" for qid, (i, n) in followup.items()},
            asked_at={},
        )

        first = await self._ask_interview_question(db, session)
        return {
            "session_id": session.id,
            "mode": session.mode,
            "state": session.state,
            "active_agent": session.active_agent,
            "question_count": len(plan),
            "first_question": first,
        }

    # ------------------------------------------------------------------
    # 记忆训练 / 回忆模式：展示 → 考核 → 即时反馈（共用代码路径）
    # ------------------------------------------------------------------

    async def start_quiz(self, db: DBSession, session_id: int) -> dict[str, Any]:
        """用户确认记好了：打乱顺序，进入 *_QUIZ，返回第一题变体题干。"""
        session = self._get_session(db, session_id)
        quiz_state = _QUIZ_STATES.get(session.mode)
        if quiz_state is None or session.state != _SHOW_STATES[session.mode].value:
            raise StateError(f"当前状态 {session.state} 不能开始考核（需在展示阶段）")

        quiz_order = list(session.question_ids)
        random.shuffle(quiz_order)
        session.quiz_order = quiz_order
        session.current_index = 0
        db.add(session)
        db.commit()
        self._save_context(db, session, variants={}, results=[])

        question = db.get(Question, quiz_order[0])
        # 面试官 Agent 生成第一题变体题干
        self._transition(db, session, quiz_state, self.interviewer.name)
        events.publish(self.interviewer.name, "出题中…")
        variant = await self.interviewer.run(question, db)
        self._store_variant(db, session, question.id, variant)

        return {
            "session_id": session.id,
            "state": session.state,
            "active_agent": session.active_agent,
            "progress": f"1/{len(quiz_order)}",
            "question_id": question.id,
            "variant_stem": variant,
        }

    async def get_current(self, db: DBSession, session_id: int) -> dict[str, Any]:
        """当前题：考核模式返回变体题干+关键词（半开卷提示）；面试模式返回变体题干+追问标识+出题时间。"""
        session = self._get_session(db, session_id)
        if session.state == SessionState.INTERVIEW_ANSWER.value:
            return self._interview_current_payload(db, session)
        if session.state not in (SessionState.MEMORIZE_QUIZ.value, SessionState.REVIEW_QUIZ.value):
            raise StateError(f"当前状态 {session.state} 无进行中的题目")
        question = self._current_question(db, session)
        variant = (session.context.get("variants") or {}).get(str(question.id), question.stem)
        return {
            "session_id": session.id,
            "state": session.state,
            "active_agent": session.active_agent,
            "progress": f"{session.current_index + 1}/{len(session.quiz_order)}",
            "question_id": question.id,
            "variant_stem": variant,
            "keywords": question.keywords,
        }

    async def submit_answer(
        self, db: DBSession, session_id: int, answer: str, started_at: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """提交回答：考核模式即时反馈；面试模式只回执"已记录"并推进。幂等键去重，冲突返回稳定错误码。"""
        session = self._get_session(db, session_id)
        if session.state == SessionState.INTERVIEW_ANSWER.value:
            return await self._run_operation(
                db, session, OperationType.ANSWER.value, idempotency_key,
                {SessionState.INTERVIEW_ANSWER.value},
                lambda s, op: self._interview_answer(db, s, answer, started_at, op),
            )
        if session.state in (SessionState.MEMORIZE_QUIZ.value, SessionState.REVIEW_QUIZ.value):
            return await self._run_operation(
                db, session, OperationType.ANSWER.value, idempotency_key,
                {SessionState.MEMORIZE_QUIZ.value, SessionState.REVIEW_QUIZ.value},
                lambda s, op: self._quiz_answer(db, s, answer, op),
            )
        # 状态不匹配但有进行中操作（如面试评分中 INTERVIEW_SCORE）：按并发冲突处理，返回稳定错误码
        if self._running_operation(db, session.id) is not None:
            db.rollback()
            raise OperationConflictError("OPERATION_IN_PROGRESS", "当前题目有操作正在进行中，请勿重复提交")
        raise StateError(f"当前状态 {session.state} 不能提交回答")

    async def _quiz_answer(self, db: DBSession, session: Session, answer: str, op: WorkflowOperation) -> dict[str, Any]:
        """记忆训练/回忆模式答题：LLM 阶段（不持事务）→ 原子写库（记录+队列+统计+推进），即时返回评分。"""
        quiz_state = SessionState(session.state)
        question = self._current_question(db, session)
        is_last = session.current_index + 1 >= len(session.quiz_order)

        # LLM 阶段（不持有数据库事务）：评分 + 下一题变体预生成
        # with_annotation=False：即时反馈不展示标注版答案，省掉"逐字复制标答"的输出 token
        self._transition(db, session, quiz_state, self.grader.name)
        events.publish(self.grader.name, "判分中…")
        score = await self.grader.run(question, answer, with_annotation=False)
        next_question = None
        next_variant = None
        if not is_last:
            next_question = db.get(Question, session.quiz_order[session.current_index + 1])
            self._transition(db, session, quiz_state, self.interviewer.name)
            events.publish(self.interviewer.name, "出题中…")
            next_variant = await self.interviewer.run(next_question, db)

        # 原子写库：答题记录（绑定 operation_id）+ 评分回填 + 待补答队列 + 日统计 + 会话推进，一次提交
        record_id = self.assistant.log_answer(db, session.id, question.id, answer, operation_id=op.id, commit=False)
        self.assistant.fill_scores(db, record_id, score, commit=False)
        results = list(session.context.get("results") or [])
        results.append({"question_id": question.id, "user_answer": answer, "record_id": record_id, "score": score})
        context = {**session.context, "results": results}
        if next_question is not None:
            variants = dict(session.context.get("variants") or {})
            variants[str(next_question.id)] = next_variant
            context["variants"] = variants
        session.context = context
        session.current_index += 1
        session.updated_at = datetime.now(timezone.utc)
        if is_last:
            # 全部答完：状态回 IDLE
            session.state = SessionState.IDLE.value
            session.active_agent = self.name
        db.add(session)
        db.commit()

        payload: dict[str, Any] = {
            "session_id": session.id,
            "question_id": question.id,
            "score": score,
            "standard_answer": question.answer,
            "record_id": record_id,
        }
        if not is_last:
            payload["finished"] = False
            payload["next_question"] = {
                "question_id": next_question.id,
                "variant_stem": next_variant,
                "progress": f"{session.current_index + 1}/{len(session.quiz_order)}",
            }
        else:
            payload["finished"] = True
            payload["state"] = session.state
            payload["summary"] = self._build_summary(session)
        return payload

    # ------------------------------------------------------------------
    # 面试模拟模式：全程无反馈，终局复盘
    # ------------------------------------------------------------------

    async def _ask_interview_question(self, db: DBSession, session: Session) -> dict[str, Any]:
        """出当前面试题：生成变体题干，记录出题时间戳，进入等待回答状态。"""
        question = db.get(Question, session.quiz_order[session.current_index])
        if question is None:
            raise StateError("当前题目在题库中不存在")

        # 面试官 Agent 生成变体题干（INTERVIEW_ASK）
        self._transition(db, session, SessionState.INTERVIEW_ASK, self.interviewer.name)
        events.publish(self.interviewer.name, "提问中…")
        variant = await self.interviewer.run(question, db)
        self._store_variant(db, session, question.id, variant)

        # 记录出题时间戳（2 分钟时间压力的计时基准），进入等待回答状态
        asked_at = dict(session.context.get("asked_at") or {})
        asked_at[str(question.id)] = datetime.now(timezone.utc).isoformat()
        self._save_context(db, session, asked_at=asked_at)
        session.current_question_id = question.id
        db.add(session)
        self._transition(db, session, SessionState.INTERVIEW_ANSWER, self.interviewer.name)
        return self._interview_current_payload(db, session)

    def _interview_current_payload(self, db: DBSession, session: Session) -> dict[str, Any]:
        """面试当前题载荷：变体题干 + 追问标识 + 出题时间，不含答案与任何评分信息。"""
        question = db.get(Question, session.quiz_order[session.current_index])
        if question is None:
            raise StateError("当前题目在题库中不存在")
        context = session.context
        variant = (context.get("variants") or {}).get(str(question.id), question.stem)
        return {
            "session_id": session.id,
            "state": session.state,
            "active_agent": session.active_agent,
            "progress": f"{session.current_index + 1}/{len(session.quiz_order)}",
            "question_id": question.id,
            "variant_stem": variant,
            "followup": (context.get("followup") or {}).get(str(question.id)),
            "asked_at": (context.get("asked_at") or {}).get(str(question.id)),
        }

    async def _interview_answer(
        self, db: DBSession, session: Session, answer: str, started_at: Optional[str], op: WorkflowOperation
    ) -> dict[str, Any]:
        """面试答题：LLM 评分（不持事务）→ 原子写库（记录+统计+推进），响应只回执"已记录"。"""
        question = db.get(Question, session.quiz_order[session.current_index])
        if question is None:
            raise StateError("当前题目在题库中不存在")

        # LLM 阶段：评分照常异步算好（INTERVIEW_SCORE，结果不透露给用户）
        self._transition(db, session, SessionState.INTERVIEW_SCORE, self.grader.name)
        events.publish(self.grader.name, "判分中…")
        score = await self.grader.run(question, answer)

        # 原子写库：答题记录 + 评分回填 + 待补答队列 + 日统计 + 会话推进，一次提交
        record_id = self.assistant.log_answer(db, session.id, question.id, answer, operation_id=op.id, commit=False)
        self.assistant.fill_scores(db, record_id, score, commit=False)
        results = list(session.context.get("results") or [])
        results.append({
            "question_id": question.id,
            "user_answer": answer,
            "record_id": record_id,
            "score": score,
            "skipped": False,
            "started_at": started_at,  # 调用方标记的开始作答时间（时间压力检测留给前端）
        })
        session.context = {**session.context, "results": results}
        session.current_index += 1
        session.updated_at = datetime.now(timezone.utc)
        db.add(session)
        db.commit()
        return await self._interview_advance(db, session, question.id, record_id)

    async def skip_question(self, db: DBSession, session_id: int, idempotency_key: Optional[str] = None) -> dict[str, Any]:
        """面试跳过：标记为失败（总分 0），不消耗补答机会、不给补答，直接推进。幂等键去重。"""
        session = self._get_session(db, session_id)
        if session.state != SessionState.INTERVIEW_ANSWER.value:
            # 状态不匹配但有进行中操作（如回答正在评分）：按并发冲突处理，返回稳定错误码
            if self._running_operation(db, session.id) is not None:
                db.rollback()
                raise OperationConflictError("OPERATION_IN_PROGRESS", "当前题目有操作正在进行中，请勿重复提交")
            raise StateError(f"当前状态 {session.state} 不能跳过（仅面试作答中可跳过）")
        return await self._run_operation(
            db, session, OperationType.SKIP.value, idempotency_key,
            {SessionState.INTERVIEW_ANSWER.value},
            lambda s, op: self._skip_answer(db, s, op),
        )

    async def _skip_answer(self, db: DBSession, session: Session, op: WorkflowOperation) -> dict[str, Any]:
        """跳过落库：失败记录 + 日统计 + 会话推进，一次原子提交（不消耗补答机会、不入待补答队列）。"""
        question = db.get(Question, session.quiz_order[session.current_index])
        if question is None:
            raise StateError("当前题目在题库中不存在")

        record_id = self.assistant.log_skip(db, session.id, question.id, operation_id=op.id, commit=False)
        results = list(session.context.get("results") or [])
        results.append({
            "question_id": question.id,
            "user_answer": "",
            "record_id": record_id,
            "score": None,
            "skipped": True,
        })
        session.context = {**session.context, "results": results}
        session.current_index += 1
        session.updated_at = datetime.now(timezone.utc)
        db.add(session)
        db.commit()
        return await self._interview_advance(db, session, question.id, record_id)

    async def _interview_advance(
        self, db: DBSession, session: Session, question_id: int, record_id: int
    ) -> dict[str, Any]:
        """面试推进：有下一题则出题，否则进入终局复盘并生成报告。"""
        payload: dict[str, Any] = {
            "session_id": session.id,
            "question_id": question_id,
            "recorded": True,  # 全程无反馈：只回执已记录，不透露分数/对错
            "record_id": record_id,
        }
        if session.current_index < len(session.quiz_order):
            next_payload = await self._ask_interview_question(db, session)
            payload["finished"] = False
            payload["next_question"] = next_payload
        else:
            self._transition(db, session, SessionState.INTERVIEW_REVIEW, self.assistant.name)
            events.publish(self.assistant.name, "生成复盘报告…")
            report = await self.assistant.build_review_report(db, session)
            self._save_context(db, session, review_report=report)
            payload["finished"] = True
            payload["state"] = session.state
        return payload

    # ------------------------------------------------------------------
    # 终局复盘与补答
    # ------------------------------------------------------------------

    async def get_review(self, db: DBSession, session_id: int) -> dict[str, Any]:
        """终局复盘报告：逐题对照 + 薄弱点分析 + 学习建议 + 需补答列表。"""
        session = self._get_session(db, session_id)
        if session.state != SessionState.INTERVIEW_REVIEW.value:
            raise StateError(f"当前状态 {session.state} 无复盘报告（需面试全部结束后）")
        report = session.context.get("review_report")
        if not report:
            raise StateError("复盘报告尚未生成")
        return report

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _current_question(self, db: DBSession, session: Session) -> Question:
        """取当前题（quiz_order[current_index]）。"""
        if not session.quiz_order or session.current_index >= len(session.quiz_order):
            raise StateError("会话没有进行中的题目")
        question = db.get(Question, session.quiz_order[session.current_index])
        if question is None:
            raise StateError("当前题目在题库中不存在")
        session.current_question_id = question.id
        db.add(session)
        db.commit()
        return question

    def _store_variant(self, db: DBSession, session: Session, question_id: int, variant: str) -> None:
        """把变体题干存入会话上下文，供 /current 接口返回。"""
        variants = dict(session.context.get("variants") or {})
        variants[str(question_id)] = variant
        self._save_context(db, session, variants=variants)

    @staticmethod
    def _question_payload(question: Question, with_answer: bool) -> dict[str, Any]:
        payload = {
            "question_id": question.id,
            "stem": question.stem,
            "tech_stack": question.tech_stack,
            "difficulty": question.difficulty,
            "keywords": question.keywords,
            "tags": question.tags,
        }
        if with_answer:
            payload["answer"] = question.answer
        return payload

    @staticmethod
    def _build_summary(session: Session) -> dict[str, Any]:
        """会话总结：各题得分、平均分、背诵次数。"""
        results = session.context.get("results") or []
        totals = [r["score"]["total"] for r in results if r.get("score")]
        return {
            "question_count": len(results),
            "avg_total": round(sum(totals) / len(totals), 1) if totals else None,
            "reciting_count": sum(1 for r in results if r.get("score", {}) and r["score"].get("is_reciting")),
            "per_question": [
                {"question_id": r["question_id"], "total": r["score"]["total"], "is_reciting": r["score"]["is_reciting"]}
                for r in results
                if r.get("score")
            ],
        }


def get_session_info(db: DBSession, session_id: int) -> dict[str, Any]:
    """查询会话状态（含当前活跃 Agent 名）。模块级函数，无需 LLM。"""
    session = db.get(Session, session_id)
    if session is None:
        raise StateError(f"会话不存在：{session_id}")
    return {
        "session_id": session.id,
        "mode": session.mode,
        "state": session.state,
        "active_agent": session.active_agent,
        "tech_stack": session.tech_stack,
        "question_count": len(session.question_ids),
        "progress": f"{min(session.current_index, len(session.quiz_order))}/{len(session.quiz_order)}" if session.quiz_order else None,
        "current_question_id": session.current_question_id,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


# 全局单例：共享同一个 LLMRouter
orchestrator = OrchestratorAgent()
