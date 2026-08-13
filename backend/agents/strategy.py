# -*- coding: utf-8 -*-
"""策略 Agent：智能抽题（记忆训练），追问链与排除规则为 Phase 3 预留。"""
import random
from typing import Optional

from sqlalchemy import case, func
from sqlmodel import Session as DBSession, select

from models import Question, Record

from .base import BaseAgent, SCORE_PASS_THRESHOLD


class StrategyAgent(BaseAgent):
    """策略 Agent：基于历史表现抽题。

    优先级：从未在 records 中出现的题 > 历史平均分/成功率低的题。
    """

    name = "策略"

    async def run(
        self,
        db: DBSession,
        tech_stack: Optional[str] = None,
        count: int = 3,
    ) -> list[Question]:
        """主入口：按技术栈抽取 count 道题。"""
        return self.select_questions(db, tech_stack=tech_stack, count=count)

    def select_questions(
        self,
        db: DBSession,
        tech_stack: Optional[str] = None,
        count: int = 3,
    ) -> list[Question]:
        """智能抽题：新题优先，其次历史表现差的题。

        tech_stack 为 None / 空串 / "mixed" 时不限技术栈。
        题量不足时返回全部可用题（MVP 允许）。
        """
        stmt = select(Question)
        if tech_stack and tech_stack != "mixed":
            stmt = stmt.where(Question.tech_stack == tech_stack)
        questions = list(db.exec(stmt).all())
        if not questions:
            return []

        # 汇总每题历史表现：答题次数、平均分、成功次数
        rows = db.exec(
            select(
                Record.question_id,
                func.count(Record.id),
                func.avg(Record.score_total),
                func.sum(case((Record.score_total >= SCORE_PASS_THRESHOLD, 1), else_=0)),
            ).group_by(Record.question_id)
        ).all()
        # stats: question_id -> (次数, 平均分, 成功数)
        stats = {qid: (cnt, avg or 0.0, ok or 0) for qid, cnt, avg, ok in rows}

        fresh = [q for q in questions if q.id not in stats]
        random.shuffle(fresh)
        # 历史表现差的优先：先按平均分升序，同分再按成功率升序
        seen = [q for q in questions if q.id in stats]
        seen.sort(key=lambda q: (stats[q.id][1], stats[q.id][2] / stats[q.id][0]))

        return (fresh + seen)[:count]

    # ------------------------------------------------------------------
    # 以下为面试模式（Phase 3）预留接口，本阶段不实现
    # ------------------------------------------------------------------

    def design_followup_chain(self, db: DBSession, tech_stack: Optional[str] = None) -> None:
        """追问链设计：挑选同一知识点的递进题组成追问链（Phase 3 实现）。"""
        raise NotImplementedError("追问链设计为面试模式功能，Phase 3 实现")

    def apply_exclusion_rule(self, db: DBSession, questions: list[Question]) -> list[Question]:
        """"连续 3 次成功排除"规则：短期内不再抽取已熟练的题（Phase 3 实现）。

        当前为占位：原样返回输入，不做排除。
        """
        # TODO(Phase 3)：读取助理的连续成功次数，排除连续 3 次成功的题
        return questions
