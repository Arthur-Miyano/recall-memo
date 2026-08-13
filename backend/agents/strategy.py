# -*- coding: utf-8 -*-
"""策略 Agent：智能抽题。

- 记忆训练：新题优先，其次历史表现差的题；
- 面试模拟：混合结构抽题（追问链 + 独立单题），带"连续成功短期排除"规则；
- 回忆模式：只抽已出现过的题，按"到期度"（简易艾宾浩斯）排序。
"""
import random
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import case, func
from sqlmodel import Session as DBSession, select

from models import Question, QuestionGroup, Record

from .base import BaseAgent, SCORE_PASS_THRESHOLD, consecutive_success

# "连续成功短期排除"规则：连续 N 次不经补答成功，且最近一次出现在窗口期内，则短期不抽
EXCLUSION_CONSECUTIVE_SUCCESS = 3
EXCLUSION_WINDOW_DAYS = 7

# 回忆模式到期度公式（简易艾宾浩斯，可解释）：
#   到期度 = 距上次出现天数 × (1 - 历史平均得分/100) ÷ (1 + 连续成功降权系数 × 连续成功次数)
# 越久没复习、历史得分越低，到期度越高；连续成功则降权，推迟复习。
REVIEW_CONSECUTIVE_DAMPING = 0.5


def _as_utc(dt: datetime) -> datetime:
    """SQLite 读出的时间可能丢失时区，统一按 UTC 处理。"""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


class StrategyAgent(BaseAgent):
    """策略 Agent：基于历史表现抽题，维护追问链与排除规则。"""

    name = "策略"

    async def run(
        self,
        db: DBSession,
        tech_stack: Optional[str] = None,
        count: int = 3,
    ) -> list[Question]:
        """主入口：记忆训练抽题（面试/回忆走各自的专用方法）。"""
        return self.select_questions(db, tech_stack=tech_stack, count=count)

    # ------------------------------------------------------------------
    # 历史数据汇总
    # ------------------------------------------------------------------

    @staticmethod
    def _histories(db: DBSession) -> dict[int, list[Record]]:
        """每题的答题记录（按时间升序），key 为 question_id。"""
        histories: dict[int, list[Record]] = {}
        for r in db.exec(select(Record).order_by(Record.created_at, Record.id)).all():
            histories.setdefault(r.question_id, []).append(r)
        return histories

    # ------------------------------------------------------------------
    # 记忆训练抽题（Phase 2 已实现）
    # ------------------------------------------------------------------

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
    # 面试模拟抽题：追问链 + 独立单题 + 排除规则
    # ------------------------------------------------------------------

    def apply_exclusion_rule(
        self,
        db: DBSession,
        questions: list[Question],
        histories: Optional[dict[int, list[Record]]] = None,
    ) -> list[Question]:
        """"连续 3 次不经补答成功"规则：最近 7 天内仍在窗口期的熟练题短期排除。"""
        if histories is None:
            histories = self._histories(db)
        now = datetime.now(timezone.utc)
        kept = []
        for q in questions:
            records = histories.get(q.id) or []
            excluded = (
                consecutive_success(records) >= EXCLUSION_CONSECUTIVE_SUCCESS
                and records
                and (now - _as_utc(records[-1].created_at)).days < EXCLUSION_WINDOW_DAYS
            )
            if not excluded:
                kept.append(q)
        return kept

    def select_interview_plan(
        self,
        db: DBSession,
        tech_stack: Optional[str] = None,
        count: int = 4,
    ) -> tuple[list[Question], dict[int, tuple[int, int]]]:
        """面试混合结构抽题：返回 (出题顺序列表, 追问标识 {question_id: (序号, 链长)})。

        - 候选题按技术栈过滤后，先应用排除规则；
        - 尽量安排 1 个追问组（组内题均未被排除且长度不超题量），按预设递进顺序连续出题；
        - 剩余名额用独立单题补齐：新题优先，其次低分/低成功率/久未出现的题；
        - 追问链块插入到独立题序列的随机位置；允许重复（记录照常写库）。
        """
        stmt = select(Question)
        if tech_stack and tech_stack != "mixed":
            stmt = stmt.where(Question.tech_stack == tech_stack)
        all_questions = list(db.exec(stmt).all())
        if not all_questions:
            return [], {}

        histories = self._histories(db)
        available = self.apply_exclusion_rule(db, all_questions, histories)
        # 排除后题量不足时，被排除的题作为兜底池（MVP 允许重复）
        fallback = [q for q in all_questions if q not in available]

        # 追问组：组内题目都在可用池、且整组能放进本场题量
        available_ids = {q.id for q in available}
        groups = [
            g for g in db.exec(select(QuestionGroup)).all()
            if 2 <= len(g.question_ids) <= count and all(qid in available_ids for qid in g.question_ids)
        ]
        # 优先选组员历史表现最差的组（平均分越低越该考），完全没记录时随机
        def _group_avg(g: QuestionGroup) -> float:
            scores = [
                sum(r.score_total for r in histories[qid] if r.score_total is not None)
                / max(len([r for r in histories[qid] if r.score_total is not None]), 1)
                for qid in g.question_ids
                if histories.get(qid)
            ]
            return sum(scores) / len(scores) if scores else random.uniform(0, 100)

        groups.sort(key=_group_avg)
        chain: list[Question] = []
        followup: dict[int, tuple[int, int]] = {}
        if groups:
            group = groups[0]
            by_id = {q.id: q for q in available}
            chain = [by_id[qid] for qid in group.question_ids]
            total = len(chain)
            followup = {q.id: (i + 1, total) for i, q in enumerate(chain)}

        # 独立单题补齐：新题优先，其次平均分低、成功率低、久未出现
        now = datetime.now(timezone.utc)
        chain_ids = {q.id for q in chain}
        pool = [q for q in available if q.id not in chain_ids]
        fresh = [q for q in pool if q.id not in histories]
        random.shuffle(fresh)

        def _seen_key(q: Question) -> tuple[float, float, int]:
            records = histories[q.id]
            scored = [r.score_total for r in records if r.score_total is not None]
            avg = sum(scored) / len(scored) if scored else 0.0
            ok = sum(1 for s in scored if s >= SCORE_PASS_THRESHOLD)
            days = (now - _as_utc(records[-1].created_at)).days
            # 平均分升序、成功率升序、距上次出现天数降序（取负实现）
            return (avg, ok / len(records), -days)

        seen = sorted((q for q in pool if q.id in histories), key=_seen_key)
        independents = (fresh + seen)[: max(count - len(chain), 0)]
        # 可用池不够时用兜底池补齐（保持题量，允许重复）
        if len(chain) + len(independents) < count:
            need = count - len(chain) - len(independents)
            picked_ids = chain_ids | {q.id for q in independents}
            independents += [q for q in fallback if q.id not in picked_ids][:need]

        random.shuffle(independents)
        # 追问链块插入随机位置，单场内顺序固定
        insert_at = random.randint(0, len(independents))
        plan = independents[:insert_at] + chain + independents[insert_at:]
        return plan, followup

    # ------------------------------------------------------------------
    # 回忆模式抽题：只抽已出现过的题，按到期度排序
    # ------------------------------------------------------------------

    def select_review_questions(self, db: DBSession, count: int = 3) -> list[Question]:
        """回忆模式抽题：简易艾宾浩斯调度，到期度高的优先。

        到期度 = 距上次出现天数 × (1 - 历史平均得分/100) ÷ (1 + 降权系数 × 连续成功次数)
        无任何历史记录时返回空列表（由上层转成对用户提示）。
        """
        histories = self._histories(db)
        if not histories:
            return []

        now = datetime.now(timezone.utc)
        ranked: list[tuple[float, int]] = []  # (到期度, question_id)
        for qid, records in histories.items():
            scored = [r.score_total for r in records if not r.skipped and r.score_total is not None]
            avg = sum(scored) / len(scored) if scored else 0.0
            # 距上次出现天数用浮点（不足 1 天也能区分先后），避免同日记录到期度全为 0
            days = max((now - _as_utc(records[-1].created_at)).total_seconds() / 86400, 0.0)
            consec = consecutive_success(records)
            due = days * (1 - avg / 100) / (1 + REVIEW_CONSECUTIVE_DAMPING * consec)
            ranked.append((due, qid))
        # 到期度降序
        ranked.sort(key=lambda item: item[0], reverse=True)

        top_ids = [qid for _, qid in ranked[:count]]
        by_id = {q.id: q for q in db.exec(select(Question).where(Question.id.in_(top_ids))).all()}
        return [by_id[qid] for qid in top_ids if qid in by_id]
