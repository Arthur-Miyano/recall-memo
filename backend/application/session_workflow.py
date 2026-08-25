# -*- coding: utf-8 -*-
"""SessionWorkflow：会话状态规则、合法转换与恢复决策（修复方案 §9.1）。

从 OrchestratorAgent 抽出的纯状态机层：不碰 LLM，只负责
- 模式/题量校验与"展示 → 考核"状态对规则；
- 状态变更落库（transition）、上下文更新、当前题解析；
- 会话状态查询（session_info，前端恢复的入口载荷）。

幂等/并发协调见 operation_coordinator.py；orchestrator.py 保留编排与 LLM 调度。
"""
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session as DBSession

from domain.session_state import SessionState
from models import Question, Session


class StateError(RuntimeError):
    """非法的状态跳转或会话状态不满足操作要求。"""


# 各模式的题量限制：memorize 自由输入（1~20），interview/review 保持小范围
MODE_COUNT_RULES = {
    "memorize": (1, 20, None),
    "interview": (3, 5, None),
    "review": (1, 10, None),
}

# 记忆训练与回忆模式共用的"展示 → 考核"状态对
SHOW_STATES = {"memorize": SessionState.MEMORIZE_SHOW, "review": SessionState.REVIEW_SHOW}
QUIZ_STATES = {"memorize": SessionState.MEMORIZE_QUIZ, "review": SessionState.REVIEW_QUIZ}


class SessionWorkflow:
    """会话状态机：状态规则、合法转换、恢复决策（无 LLM 依赖）。"""

    # ------------------------------------------------------------------
    # 状态规则
    # ------------------------------------------------------------------

    @staticmethod
    def validate_create(mode: str, count: int) -> None:
        """创建会话前的模式/题量校验，非法即 StateError。"""
        if mode not in MODE_COUNT_RULES:
            raise StateError(f"未知模式：{mode}（支持 memorize / interview / review）")
        low, high, allowed = MODE_COUNT_RULES[mode]
        if allowed is not None and count not in allowed:
            raise StateError(f"记忆训练模式题量仅支持 {sorted(allowed)}")
        if not low <= count <= high:
            raise StateError(f"该模式题量范围为 {low}~{high}")

    # ------------------------------------------------------------------
    # 状态转换与上下文
    # ------------------------------------------------------------------

    def transition(self, db: DBSession, session: Session, state: SessionState, active_agent: str) -> None:
        """状态变更：写入 sessions 表，并记录当前活跃 Agent 名称（供后续 SSE）。"""
        session.state = state.value
        session.active_agent = active_agent
        session.updated_at = datetime.now(timezone.utc)
        db.add(session)
        db.commit()
        db.refresh(session)

    def get_session(self, db: DBSession, session_id: int) -> Session:
        session = db.get(Session, session_id)
        if session is None:
            raise StateError(f"会话不存在：{session_id}")
        return session

    @staticmethod
    def save_context(db: DBSession, session: Session, **updates: Any) -> None:
        """更新会话上下文字段（整体重新赋值触发 JSON 列更新）。"""
        session.context = {**session.context, **updates}
        db.add(session)
        db.commit()
        db.refresh(session)

    # ------------------------------------------------------------------
    # 当前题与变体题干
    # ------------------------------------------------------------------

    def current_question(self, db: DBSession, session: Session) -> Question:
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

    def store_variant(self, db: DBSession, session: Session, question_id: int, variant: str) -> None:
        """把变体题干存入会话上下文，供 /current 接口返回。"""
        variants = dict(session.context.get("variants") or {})
        variants[str(question_id)] = variant
        self.save_context(db, session, variants=variants)

    # ------------------------------------------------------------------
    # 载荷与恢复决策
    # ------------------------------------------------------------------

    @staticmethod
    def question_payload(question: Question, with_answer: bool) -> dict[str, Any]:
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
            # 记忆树缓存（无树则为 None，前端据此决定单栏/双栏展示）
            payload["memory_tree"] = question.memory_tree
        return payload

    @staticmethod
    def build_summary(session: Session) -> dict[str, Any]:
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

    @staticmethod
    def session_info(db: DBSession, session_id: int) -> dict[str, Any]:
        """查询会话状态（含当前活跃 Agent 名）：前端刷新/切页恢复的入口载荷。"""
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
