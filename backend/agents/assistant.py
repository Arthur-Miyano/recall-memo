# -*- coding: utf-8 -*-
"""智能助理 Agent：中央记忆。本阶段只做答题写库、daily_stats 聚合与基础查询。"""
from datetime import date
from typing import Any, Optional

from sqlmodel import Session as DBSession, select

from models import DailyStat, Record

from .base import BaseAgent, SCORE_PASS_THRESHOLD


class AssistantAgent(BaseAgent):
    """智能助理 Agent：答题记录写库 + 每题历史/每日统计查询。"""

    name = "智能助理"

    async def run(self, db: DBSession, session_id: int, question_id: int, user_answer: str) -> int:
        """主入口：写入一条答题记录（不含评分），返回 record id。"""
        return self.log_answer(db, session_id, question_id, user_answer)

    # ------------------------------------------------------------------
    # 写库：拆成两步，便于与评分 Agent 用 asyncio.gather 并行
    # ------------------------------------------------------------------

    def log_answer(self, db: DBSession, session_id: int, question_id: int, user_answer: str) -> int:
        """第一步：写入用户回答原文（不依赖评分结果，可与评分并行）。"""
        record = Record(session_id=session_id, question_id=question_id, user_answer=user_answer)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record.id

    def fill_scores(self, db: DBSession, record_id: int, score: dict[str, Any]) -> None:
        """第二步：评分完成后回填分数，并更新 daily_stats 日聚合。"""
        record = db.get(Record, record_id)
        if record is None:
            return
        record.score_accuracy = score.get("accuracy")
        record.score_logic = score.get("logic")
        record.score_naturalness = score.get("naturalness")
        record.score_total = score.get("total")
        record.is_reciting = score.get("is_reciting")
        # 总分低于阈值标记为需要补答/复习
        record.need_followup = (score.get("total") or 0.0) < SCORE_PASS_THRESHOLD
        db.add(record)

        today = date.today()
        stat = db.exec(select(DailyStat).where(DailyStat.date == today)).first()
        if stat is None:
            stat = DailyStat(date=today)
        stat.total_count += 1
        if (score.get("total") or 0.0) >= SCORE_PASS_THRESHOLD:
            stat.success_count += 1
        else:
            stat.fail_count += 1
        db.add(stat)
        db.commit()

    # ------------------------------------------------------------------
    # 基础查询
    # ------------------------------------------------------------------

    def get_question_history(self, db: DBSession, question_id: int) -> dict[str, Any]:
        """每题历史：首次/最近出现日期、累计次数、连续成功次数、平均分。"""
        records = list(
            db.exec(
                select(Record)
                .where(Record.question_id == question_id)
                .order_by(Record.created_at)
            ).all()
        )
        if not records:
            return {
                "question_id": question_id,
                "first_seen": None,
                "last_seen": None,
                "total_count": 0,
                "consecutive_success": 0,
                "avg_score": None,
            }
        scored = [r.score_total for r in records if r.score_total is not None]
        # 从最近一条往前数连续成功（总分 >= 阈值）的次数
        consecutive = 0
        for r in reversed(records):
            if r.score_total is not None and r.score_total >= SCORE_PASS_THRESHOLD:
                consecutive += 1
            else:
                break
        return {
            "question_id": question_id,
            "first_seen": records[0].created_at.isoformat(),
            "last_seen": records[-1].created_at.isoformat(),
            "total_count": len(records),
            "consecutive_success": consecutive,
            "avg_score": round(sum(scored) / len(scored), 1) if scored else None,
        }

    def get_daily_stats(self, db: DBSession, day: Optional[date] = None) -> list[DailyStat]:
        """查询每日统计：指定日期查单日，否则返回全部。"""
        stmt = select(DailyStat)
        if day is not None:
            stmt = stmt.where(DailyStat.date == day)
        return list(db.exec(stmt.order_by(DailyStat.date)).all())
