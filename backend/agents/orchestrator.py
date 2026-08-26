# -*- coding: utf-8 -*-
"""总控 Agent：用户请求唯一入口，编排会话全流程（记忆训练 / 面试模拟 / 回忆）。

结构（修复方案 §9.1）：本文件只保留意图分发、模式编排与 LLM 调度；
- 状态规则 / 合法转换 / 恢复决策 → application/session_workflow.py（SessionWorkflow）
- 版本检查 / 幂等 / 短事务 / 结果持久化 → application/operation_coordinator.py（OperationCoordinator）

StateError / OperationConflictError / SessionState 在此 re-export，
旧导入路径（agents.StateError、agents.orchestrator.StateError 等）不受影响。
"""
import random
from datetime import datetime, timezone
from typing import Any, Optional

from sqlmodel import Session as DBSession, select

import events
from application.operation_coordinator import (  # noqa: F401  re-export：旧导入路径仍可用
    OperationConflictError,
    OperationCoordinator,
)
from application.session_workflow import (  # noqa: F401  re-export：旧导入路径仍可用
    QUIZ_STATES,
    SHOW_STATES,
    SessionWorkflow,
    StateError,
)
from domain.session_state import SessionState  # noqa: F401  re-export：旧导入路径 agents.orchestrator.SessionState 仍可用
from llm import llm_router
from models import OperationType, Question, RetryQueueItem, Session, WorkflowOperation

from .assistant import AssistantAgent
from .base import BaseAgent
from .grader import GraderAgent
from .interviewer import InterviewerAgent
from .strategy import StrategyAgent


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
        # 状态机与幂等协调（§9.1 抽出的独立模块）
        self.workflow = SessionWorkflow()
        self.coordinator = OperationCoordinator()

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
        self.workflow.validate_create(mode, count)

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
        self.workflow.transition(db, session, SessionState.IDLE, self.strategy.name)
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
        self.workflow.transition(db, session, SHOW_STATES[mode], self.name)
        return {
            "session_id": session.id,
            "mode": session.mode,
            "state": session.state,
            "active_agent": session.active_agent,
            "questions": [
                {**self.workflow.question_payload(q, with_answer=True), "retry": q.id in retry_ids}
                for q in questions
            ],
        }

    async def _create_interview(
        self, db: DBSession, session: Session, tech_stack: Optional[str], count: int
    ) -> dict[str, Any]:
        """面试模拟入口：混合结构抽题（追问链 + 独立单题）→ 直接出第一题。"""
        self.workflow.transition(db, session, SessionState.INTERVIEW_SELECT, self.strategy.name)
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
        self.workflow.save_context(
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
        session = self.workflow.get_session(db, session_id)
        quiz_state = QUIZ_STATES.get(session.mode)
        if quiz_state is None or session.state != SHOW_STATES[session.mode].value:
            raise StateError(f"当前状态 {session.state} 不能开始考核（需在展示阶段）")

        quiz_order = list(session.question_ids)
        random.shuffle(quiz_order)
        session.quiz_order = quiz_order
        session.current_index = 0
        db.add(session)
        db.commit()
        self.workflow.save_context(db, session, variants={}, results=[])

        question = db.get(Question, quiz_order[0])
        # 面试官 Agent 生成第一题变体题干
        self.workflow.transition(db, session, quiz_state, self.interviewer.name)
        events.publish(self.interviewer.name, "出题中…")
        variant = await self.interviewer.run(question, db)
        self.workflow.store_variant(db, session, question.id, variant)

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
        session = self.workflow.get_session(db, session_id)
        if session.state == SessionState.INTERVIEW_ANSWER.value:
            return self._interview_current_payload(db, session)
        if session.state not in (SessionState.MEMORIZE_QUIZ.value, SessionState.REVIEW_QUIZ.value):
            raise StateError(f"当前状态 {session.state} 无进行中的题目")
        question = self.workflow.current_question(db, session)
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
        session = self.workflow.get_session(db, session_id)
        if session.state == SessionState.INTERVIEW_ANSWER.value:
            return await self.coordinator.run_operation(
                db, session, OperationType.ANSWER.value, idempotency_key,
                {SessionState.INTERVIEW_ANSWER.value},
                lambda s, op: self._interview_answer(db, s, answer, started_at, op),
            )
        if session.state in (SessionState.MEMORIZE_QUIZ.value, SessionState.REVIEW_QUIZ.value):
            return await self.coordinator.run_operation(
                db, session, OperationType.ANSWER.value, idempotency_key,
                {SessionState.MEMORIZE_QUIZ.value, SessionState.REVIEW_QUIZ.value},
                lambda s, op: self._quiz_answer(db, s, answer, op),
            )
        # 状态不匹配但有进行中操作（如面试评分中 INTERVIEW_SCORE）：按并发冲突处理，返回稳定错误码
        if self.coordinator.running_operation(db, session.id) is not None:
            db.rollback()
            raise OperationConflictError("OPERATION_IN_PROGRESS", "当前题目有操作正在进行中，请勿重复提交")
        raise StateError(f"当前状态 {session.state} 不能提交回答")

    async def _quiz_answer(self, db: DBSession, session: Session, answer: str, op: WorkflowOperation) -> dict[str, Any]:
        """记忆训练/回忆模式答题：LLM 阶段（不持事务）→ 原子写库（记录+队列+统计+推进），即时返回评分。"""
        quiz_state = SessionState(session.state)
        question = self.workflow.current_question(db, session)
        is_last = session.current_index + 1 >= len(session.quiz_order)

        # LLM 阶段（不持有数据库事务）：评分 + 下一题变体预生成
        # with_annotation=False：即时反馈不展示标注版答案，省掉"逐字复制标答"的输出 token
        self.workflow.transition(db, session, quiz_state, self.grader.name)
        events.publish(self.grader.name, "判分中…")
        score = await self.grader.run(question, answer, with_annotation=False)
        next_question = None
        next_variant = None
        if not is_last:
            next_question = db.get(Question, session.quiz_order[session.current_index + 1])
            self.workflow.transition(db, session, quiz_state, self.interviewer.name)
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
            payload["summary"] = self.workflow.build_summary(session)
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
        self.workflow.transition(db, session, SessionState.INTERVIEW_ASK, self.interviewer.name)
        events.publish(self.interviewer.name, "提问中…")
        variant = await self.interviewer.run(question, db)
        self.workflow.store_variant(db, session, question.id, variant)

        # 记录出题时间戳（2 分钟时间压力的计时基准），进入等待回答状态
        asked_at = dict(session.context.get("asked_at") or {})
        asked_at[str(question.id)] = datetime.now(timezone.utc).isoformat()
        self.workflow.save_context(db, session, asked_at=asked_at)
        session.current_question_id = question.id
        db.add(session)
        self.workflow.transition(db, session, SessionState.INTERVIEW_ANSWER, self.interviewer.name)
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
        """面试答题：先完成全部 LLM 工作，再原子写入记录、推进状态和操作结果。"""
        question = db.get(Question, session.quiz_order[session.current_index])
        if question is None:
            raise StateError("当前题目在题库中不存在")

        # LLM 阶段不提交 Session 中间态；失败后数据库仍停在原题，可用同键重试。
        events.publish(self.grader.name, "判分中…")
        score = await self.grader.run(question, answer)
        pending_result = {
            "question_id": question.id,
            "user_answer": answer,
            "score": score,
            "skipped": False,
            "started_at": started_at,
        }
        advance = await self._prepare_interview_advance(db, session, pending_result)

        # 不在此提交；OperationCoordinator 会把业务数据与 SUCCEEDED/result 一次提交。
        record_id = self.assistant.log_answer(db, session.id, question.id, answer, operation_id=op.id, commit=False)
        self.assistant.fill_scores(db, record_id, score, commit=False)
        pending_result["record_id"] = record_id
        return self._apply_interview_advance(db, session, question.id, record_id, pending_result, advance)

    async def skip_question(self, db: DBSession, session_id: int, idempotency_key: Optional[str] = None) -> dict[str, Any]:
        """面试跳过：标记为失败（总分 0），不消耗补答机会、不给补答，直接推进。幂等键去重。"""
        session = self.workflow.get_session(db, session_id)
        if session.state != SessionState.INTERVIEW_ANSWER.value:
            # 状态不匹配但有进行中操作（如回答正在评分）：按并发冲突处理，返回稳定错误码
            if self.coordinator.running_operation(db, session.id) is not None:
                db.rollback()
                raise OperationConflictError("OPERATION_IN_PROGRESS", "当前题目有操作正在进行中，请勿重复提交")
            raise StateError(f"当前状态 {session.state} 不能跳过（仅面试作答中可跳过）")
        return await self.coordinator.run_operation(
            db, session, OperationType.SKIP.value, idempotency_key,
            {SessionState.INTERVIEW_ANSWER.value},
            lambda s, op: self._skip_answer(db, s, op),
        )

    async def _skip_answer(self, db: DBSession, session: Session, op: WorkflowOperation) -> dict[str, Any]:
        """跳过：先准备下一题/复盘，再与失败记录、统计和操作结果原子提交。"""
        question = db.get(Question, session.quiz_order[session.current_index])
        if question is None:
            raise StateError("当前题目在题库中不存在")

        pending_result = {
            "question_id": question.id,
            "user_answer": "",
            "score": None,
            "skipped": True,
        }
        advance = await self._prepare_interview_advance(db, session, pending_result)
        record_id = self.assistant.log_skip(db, session.id, question.id, operation_id=op.id, commit=False)
        pending_result["record_id"] = record_id
        return self._apply_interview_advance(db, session, question.id, record_id, pending_result, advance)

    async def _prepare_interview_advance(
        self, db: DBSession, session: Session, pending_result: dict[str, Any]
    ) -> dict[str, Any]:
        """在写入答题结果前完成下一题或复盘所需的全部 LLM 工作。"""
        results = list(session.context.get("results") or [])
        next_index = session.current_index + 1
        if next_index < len(session.quiz_order):
            next_question = db.get(Question, session.quiz_order[next_index])
            if next_question is None:
                raise StateError("下一题在题库中不存在")
            events.publish(self.interviewer.name, "提问中…")
            variant = await self.interviewer.run(next_question, db, commit=False)
            return {
                "finished": False,
                "results": results,
                "question": next_question,
                "variant": variant,
                "asked_at": datetime.now(timezone.utc).isoformat(),
            }

        # 报告生成只读取预览上下文；失败时 Coordinator rollback，不留下已推进状态。
        session.context = {**session.context, "results": [*results, pending_result]}
        db.add(session)
        events.publish(self.assistant.name, "生成复盘报告…")
        report = await self.assistant.build_review_report(db, session)
        return {"finished": True, "results": results, "report": report}

    def _apply_interview_advance(
        self,
        db: DBSession,
        session: Session,
        question_id: int,
        record_id: int,
        result: dict[str, Any],
        advance: dict[str, Any],
    ) -> dict[str, Any]:
        """把准备好的推进结果写入当前事务；提交权交给 OperationCoordinator。"""
        context = {**session.context, "results": [*advance["results"], result]}
        session.current_index += 1
        payload: dict[str, Any] = {
            "session_id": session.id,
            "question_id": question_id,
            "recorded": True,
            "record_id": record_id,
        }
        if not advance["finished"]:
            next_question = advance["question"]
            variants = dict(context.get("variants") or {})
            variants[str(next_question.id)] = advance["variant"]
            asked_at = dict(context.get("asked_at") or {})
            asked_at[str(next_question.id)] = advance["asked_at"]
            context.update(variants=variants, asked_at=asked_at)
            session.state = SessionState.INTERVIEW_ANSWER.value
            session.active_agent = self.interviewer.name
            session.current_question_id = next_question.id
            next_payload = {
                "session_id": session.id,
                "state": session.state,
                "active_agent": session.active_agent,
                "progress": f"{session.current_index + 1}/{len(session.quiz_order)}",
                "question_id": next_question.id,
                "variant_stem": advance["variant"],
                "followup": (context.get("followup") or {}).get(str(next_question.id)),
                "asked_at": advance["asked_at"],
            }
            payload["finished"] = False
            payload["next_question"] = next_payload
        else:
            report = advance["report"]
            for item in report.get("per_question", []):
                if item.get("question_id") == question_id and item.get("record_id") is None:
                    item["record_id"] = record_id
            context["review_report"] = report
            session.state = SessionState.INTERVIEW_REVIEW.value
            session.active_agent = self.assistant.name
            payload["finished"] = True
            payload["state"] = session.state
        session.context = context
        session.updated_at = datetime.now(timezone.utc)
        db.add(session)
        return payload

    # ------------------------------------------------------------------
    # 终局复盘与补答
    # ------------------------------------------------------------------

    async def get_review(self, db: DBSession, session_id: int) -> dict[str, Any]:
        """终局复盘报告：逐题对照 + 薄弱点分析 + 学习建议 + 需补答列表。"""
        session = self.workflow.get_session(db, session_id)
        if session.state != SessionState.INTERVIEW_REVIEW.value:
            raise StateError(f"当前状态 {session.state} 无复盘报告（需面试全部结束后）")
        report = session.context.get("review_report")
        if not report:
            raise StateError("复盘报告尚未生成")
        attach_memory_trees(db, report)
        return report


def attach_memory_trees(db: DBSession, report: dict[str, Any]) -> None:
    """展示层需要记忆树：按 question_id 现查附加（题已删除则为 None），不写回缓存快照。

    报告是会话上下文里的快照：若题库后来被重新导入导致 id 重排，
    按 id 查到的可能已是另一道题。题干对不上时按题干快照找回原题，找不到就显示无树。
    """
    for item in report.get("per_question", []):
        question = db.get(Question, item.get("question_id"))
        stem = item.get("stem")
        if question is not None and stem and question.stem != stem:
            question = db.exec(select(Question).where(Question.stem == stem)).first()
        item["memory_tree"] = question.memory_tree if question else None


def get_session_info(db: DBSession, session_id: int) -> dict[str, Any]:
    """查询会话状态（含当前活跃 Agent 名）：委托 SessionWorkflow，保留旧模块级入口。"""
    return SessionWorkflow.session_info(db, session_id)


# 全局单例：共享同一个 LLMRouter
orchestrator = OrchestratorAgent()
