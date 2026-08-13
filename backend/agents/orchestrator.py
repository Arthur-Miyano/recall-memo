# -*- coding: utf-8 -*-
"""总控 Agent（Orchestrator）：手写状态机，解析 API 意图，编排其余 Agent 的调用链。"""
import asyncio
import random
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from sqlmodel import Session as DBSession

from database import engine
from llm import llm_router
from models import Question, Record, Session

from .assistant import AssistantAgent
from .base import BaseAgent
from .grader import GraderAgent
from .interviewer import InterviewerAgent
from .strategy import StrategyAgent


class SessionState(str, Enum):
    """会话状态机，见文档 3.3。"""

    IDLE = "IDLE"
    # 记忆训练模式
    MEMORIZE_SHOW = "MEMORIZE_SHOW"  # 展示题干+答案供记忆
    MEMORIZE_QUIZ = "MEMORIZE_QUIZ"  # 打乱顺序考核中
    # 面试模拟模式
    INTERVIEW_SELECT = "INTERVIEW_SELECT"  # 选技术栈/题量（抽题中）
    INTERVIEW_ASK = "INTERVIEW_ASK"  # 展示变体题干
    INTERVIEW_ANSWER = "INTERVIEW_ANSWER"  # 等待回答（2 分钟计时由前端做）
    INTERVIEW_SCORE = "INTERVIEW_SCORE"  # 评分中（评分+助理并行，不透露给用户）
    INTERVIEW_REVIEW = "INTERVIEW_REVIEW"  # 终局复盘
    # 回忆模式
    REVIEW_SHOW = "REVIEW_SHOW"  # 展示题干+答案供回忆
    REVIEW_QUIZ = "REVIEW_QUIZ"  # 打乱顺序考核中


class StateError(RuntimeError):
    """非法的状态跳转或会话状态不满足操作要求。"""


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
            "retry": self.retry_question,
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

        # 抽题完成，进入展示阶段（题干+答案可见）
        self._transition(db, session, _SHOW_STATES[mode], self.name)
        return {
            "session_id": session.id,
            "mode": session.mode,
            "state": session.state,
            "active_agent": session.active_agent,
            "questions": [self._question_payload(q, with_answer=True) for q in questions],
        }

    async def _create_interview(
        self, db: DBSession, session: Session, tech_stack: Optional[str], count: int
    ) -> dict[str, Any]:
        """面试模拟入口：混合结构抽题（追问链 + 独立单题）→ 直接出第一题。"""
        self._transition(db, session, SessionState.INTERVIEW_SELECT, self.strategy.name)
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
        self, db: DBSession, session_id: int, answer: str, started_at: Optional[str] = None
    ) -> dict[str, Any]:
        """提交回答：考核模式即时反馈；面试模式只回执"已记录"并推进。"""
        session = self._get_session(db, session_id)
        if session.state == SessionState.INTERVIEW_ANSWER.value:
            return await self._interview_answer(db, session, answer, started_at)
        if session.state in (SessionState.MEMORIZE_QUIZ.value, SessionState.REVIEW_QUIZ.value):
            return await self._quiz_answer(db, session, answer)
        raise StateError(f"当前状态 {session.state} 不能提交回答")

    async def _quiz_answer(self, db: DBSession, session: Session, answer: str) -> dict[str, Any]:
        """记忆训练/回忆模式答题：评分+写库并行，即时返回评分并推进到下一题。"""
        quiz_state = SessionState(session.state)
        question = self._current_question(db, session)

        # 评分 Agent 评分 与 智能助理写入回答原文 并行（文档 3.2）
        self._transition(db, session, quiz_state, self.grader.name)
        score, record_id = await asyncio.gather(
            self.grader.run(question, answer),
            self.assistant.run(db, session_id=session.id, question_id=question.id, user_answer=answer),
        )
        # 评分完成后回填分数并聚合 daily_stats
        self.assistant.fill_scores(db, record_id, score)

        # 记录本题结果到会话上下文
        results = list(session.context.get("results") or [])
        results.append({"question_id": question.id, "user_answer": answer, "record_id": record_id, "score": score})
        session.context = {**session.context, "results": results}

        session.current_index += 1
        db.add(session)
        db.commit()

        payload: dict[str, Any] = {
            "session_id": session.id,
            "question_id": question.id,
            "score": score,
            "standard_answer": question.answer,
            "record_id": record_id,
        }

        if session.current_index < len(session.quiz_order):
            # 还有下一题：面试官生成新变体，继续考核
            next_question = db.get(Question, session.quiz_order[session.current_index])
            self._transition(db, session, quiz_state, self.interviewer.name)
            variant = await self.interviewer.run(next_question, db)
            self._store_variant(db, session, next_question.id, variant)
            payload["finished"] = False
            payload["next_question"] = {
                "question_id": next_question.id,
                "variant_stem": variant,
                "progress": f"{session.current_index + 1}/{len(session.quiz_order)}",
            }
        else:
            # 全部答完：输出总结，状态回 IDLE
            self._transition(db, session, SessionState.IDLE, self.name)
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
        self, db: DBSession, session: Session, answer: str, started_at: Optional[str]
    ) -> dict[str, Any]:
        """面试答题：评分照常异步算好存库，但响应只回执"已记录"+ 推进下一题。"""
        question = db.get(Question, session.quiz_order[session.current_index])
        if question is None:
            raise StateError("当前题目在题库中不存在")

        # 评分 Agent 与智能助理写库并行（INTERVIEW_SCORE，结果不透露给用户）
        self._transition(db, session, SessionState.INTERVIEW_SCORE, self.grader.name)
        score, record_id = await asyncio.gather(
            self.grader.run(question, answer),
            self.assistant.run(db, session_id=session.id, question_id=question.id, user_answer=answer),
        )
        self.assistant.fill_scores(db, record_id, score)

        results = list(session.context.get("results") or [])
        results.append({
            "question_id": question.id,
            "user_answer": answer,
            "record_id": record_id,
            "score": score,
            "skipped": False,
            "started_at": started_at,  # 调用方标记的开始作答时间（时间压力检测留给前端）
        })
        self._save_context(db, session, results=results)

        session.current_index += 1
        db.add(session)
        db.commit()
        return await self._interview_advance(db, session, question.id, record_id)

    async def skip_question(self, db: DBSession, session_id: int) -> dict[str, Any]:
        """面试跳过：标记为失败（总分 0），不消耗补答机会、不给补答，直接推进。"""
        session = self._get_session(db, session_id)
        if session.state != SessionState.INTERVIEW_ANSWER.value:
            raise StateError(f"当前状态 {session.state} 不能跳过（仅面试作答中可跳过）")
        question = db.get(Question, session.quiz_order[session.current_index])
        if question is None:
            raise StateError("当前题目在题库中不存在")

        record_id = self.assistant.log_skip(db, session.id, question.id)
        results = list(session.context.get("results") or [])
        results.append({
            "question_id": question.id,
            "user_answer": "",
            "record_id": record_id,
            "score": None,
            "skipped": True,
        })
        self._save_context(db, session, results=results)

        session.current_index += 1
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

    async def retry_question(
        self, db: DBSession, session_id: int, question_id: int, answer: str
    ) -> dict[str, Any]:
        """补答：仅允许复盘报告"需补答"列表中的题，每题仅 1 次。

        原记录保留不覆盖：补答写为新记录（is_retry=True，retry_of 指向原记录）。
        """
        session = self._get_session(db, session_id)
        if session.state != SessionState.INTERVIEW_REVIEW.value:
            raise StateError(f"当前状态 {session.state} 不能补答（需在终局复盘阶段）")
        report = session.context.get("review_report") or {}
        retry_list = list(report.get("retry_list") or [])
        if question_id not in retry_list:
            raise StateError(f"题目 {question_id} 不在需补答列表中（跳过/已及格/已补答过的题不可补答）")

        question = db.get(Question, question_id)
        if question is None:
            raise StateError("题目在题库中不存在")
        original = next(
            (e for e in report.get("per_question") or [] if e["question_id"] == question_id), None
        )

        # 重新评分，写为新记录（原记录保留可查）
        self._transition(db, session, SessionState.INTERVIEW_REVIEW, self.grader.name)
        score, record_id = await asyncio.gather(
            self.grader.run(question, answer),
            self.assistant.run(db, session_id=session.id, question_id=question.id, user_answer=answer),
        )
        record = db.get(Record, record_id)
        record.is_retry = True
        record.retry_of = original.get("record_id") if original else None
        db.add(record)
        db.commit()
        self.assistant.fill_scores(db, record_id, score)

        # 更新报告：移出需补答列表，补答结果挂到该题条目下
        retry_list.remove(question_id)
        if original is not None:
            original["retry"] = {"record_id": record_id, "user_answer": answer, "score": score}
        report["retry_list"] = retry_list
        retried = list(session.context.get("retried") or [])
        retried.append(question_id)
        self._save_context(db, session, review_report=report, retried=retried)
        self._transition(db, session, SessionState.INTERVIEW_REVIEW, self.assistant.name)

        return {
            "session_id": session.id,
            "question_id": question_id,
            "record_id": record_id,
            "is_retry": True,
            "score": score,
            "standard_answer": question.answer,
        }

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
