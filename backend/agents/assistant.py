# -*- coding: utf-8 -*-
"""智能助理 Agent：中央记忆。答题写库、daily_stats 聚合、历史/统计查询、终局复盘报告。"""
import logging
from datetime import date
from typing import Any, Optional

from sqlmodel import Session as DBSession, select

from models import DailyStat, Question, Record, RetryQueueItem, Session
from timeutil import local_today

from .base import BaseAgent, SCORE_PASS_THRESHOLD, consecutive_success
from .parsing import parse_json_object

logger = logging.getLogger(__name__)

# 复盘报告"学习建议"中额外推荐的历史低分题数量
REVIEW_SUGGEST_HISTORY_COUNT = 3

_REVIEW_SYSTEM_PROMPT = (
    "你是资深技术面试官，正在为候选人做整场面试的终局复盘分析。"
    "只输出一个 JSON 对象，不要输出任何其他文字、解释或 Markdown 代码块。"
)


class AssistantAgent(BaseAgent):
    """智能助理 Agent：答题记录写库 + 每题历史/每日统计查询 + 面试终局复盘报告。"""

    name = "智能助理"

    async def run(self, db: DBSession, session_id: int, question_id: int, user_answer: str) -> int:
        """主入口：写入一条答题记录（不含评分），返回 record id。"""
        return self.log_answer(db, session_id, question_id, user_answer)

    # ------------------------------------------------------------------
    # 写库：拆成两步，便于与评分 Agent 用 asyncio.gather 并行
    # ------------------------------------------------------------------

    def log_answer(self, db: DBSession, session_id: int, question_id: int, user_answer: str) -> int:
        """第一步：写入用户回答原文（不依赖评分结果，可与评分并行）。

        该题在待补答队列中时，本次作答即补答（is_retry=True，每次入队只给一次补答机会）。
        """
        in_queue = db.exec(
            select(RetryQueueItem).where(RetryQueueItem.question_id == question_id)
        ).first() is not None
        record = Record(
            session_id=session_id, question_id=question_id, user_answer=user_answer,
            is_retry=in_queue,
        )
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
        # 标注版标准答案（[[omiss]]/[[logic]] 标记），持久化供复盘报告展示；无标注则为 None
        record.annotated_answer = score.get("annotated_answer")
        # 总分低于阈值标记为需要补答/复习
        record.need_followup = (score.get("total") or 0.0) < SCORE_PASS_THRESHOLD
        db.add(record)
        # 待补答队列（记忆训练/面试共用此出口）：
        # 补答记录的机会已消耗——无论及格与否都不再入队，若仍在队列则出队；
        # 普通记录维持不及格入队、及格出队。
        if record.is_retry:
            self._dequeue_retry(db, record.question_id)
        elif record.need_followup:
            self._enqueue_retry(db, record)
        else:
            self._dequeue_retry(db, record.question_id)
        self._bump_daily_stat(db, passed=(score.get("total") or 0.0) >= SCORE_PASS_THRESHOLD)

    def _enqueue_retry(self, db: DBSession, record: Record) -> None:
        """不及格的题进入待补答队列：已在队列中则只更新来源。"""
        existing = db.exec(
            select(RetryQueueItem).where(RetryQueueItem.question_id == record.question_id)
        ).first()
        session = db.get(Session, record.session_id)
        source = session.mode if session else ""
        if existing is None:
            db.add(RetryQueueItem(question_id=record.question_id, source=source))
        else:
            existing.source = source
            db.add(existing)
        db.commit()

    @staticmethod
    def _dequeue_retry(db: DBSession, question_id: int) -> None:
        """答及格后出队。"""
        existing = db.exec(
            select(RetryQueueItem).where(RetryQueueItem.question_id == question_id)
        ).first()
        if existing is not None:
            db.delete(existing)
            db.commit()

    def log_skip(self, db: DBSession, session_id: int, question_id: int) -> int:
        """面试跳过：记为失败（总分 0），不给补答机会——need_followup=False 且不入待补答队列。"""
        record = Record(
            session_id=session_id,
            question_id=question_id,
            user_answer="",
            score_total=0.0,
            skipped=True,
            need_followup=False,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        self._bump_daily_stat(db, passed=False)
        return record.id

    @staticmethod
    def _bump_daily_stat(db: DBSession, passed: bool) -> None:
        """更新当日聚合统计并提交。「当日」按本地时区口径（与 stats 接口分组口径一致）。"""
        today = local_today()
        stat = db.exec(select(DailyStat).where(DailyStat.date == today)).first()
        if stat is None:
            stat = DailyStat(date=today)
        stat.total_count += 1
        if passed:
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
        return {
            "question_id": question_id,
            "first_seen": records[0].created_at.isoformat(),
            "last_seen": records[-1].created_at.isoformat(),
            "total_count": len(records),
            "consecutive_success": consecutive_success(records),
            "avg_score": round(sum(scored) / len(scored), 1) if scored else None,
        }

    def get_daily_stats(self, db: DBSession, day: Optional[date] = None) -> list[DailyStat]:
        """查询每日统计：指定日期查单日，否则返回全部。"""
        stmt = select(DailyStat)
        if day is not None:
            stmt = stmt.where(DailyStat.date == day)
        return list(db.exec(stmt.order_by(DailyStat.date)).all())

    # ------------------------------------------------------------------
    # 面试终局复盘报告（INTERVIEW_REVIEW）
    # ------------------------------------------------------------------

    async def build_review_report(self, db: DBSession, session: Session) -> dict[str, Any]:
        """生成终局复盘报告：逐题对照 + LLM 薄弱点分析 + 学习建议 + 需补答列表。

        数据源为会话上下文中的 results（作答时已评分存库，此处才汇总展示）。
        报告缓存进 session.context["review_report"]，补答后由总控更新。
        """
        results = session.context.get("results") or []
        followup = session.context.get("followup") or {}
        per_question: list[dict[str, Any]] = []
        retry_list: list[int] = []
        for item in results:
            question = db.get(Question, item["question_id"])
            if question is None:
                continue
            score = item.get("score")  # 跳过的题无评分
            # 标注版标准答案：优先取当场评分输出，旧数据回退 records 表持久化列，均无则 None
            annotated = (score or {}).get("annotated_answer")
            if annotated is None and item.get("record_id"):
                rec = db.get(Record, item["record_id"])
                annotated = rec.annotated_answer if rec else None
            entry: dict[str, Any] = {
                "question_id": question.id,
                "stem": question.stem,
                "tech_stack": question.tech_stack,
                "followup": followup.get(str(question.id)),  # 追问标识，如 "1/2"，独立题为 None
                "skipped": bool(item.get("skipped")),
                "user_answer": item.get("user_answer", ""),
                "standard_answer": question.answer,
                "annotated_answer": annotated,
                "score": score,
                "record_id": item.get("record_id"),
            }
            # 去向标注须与事实一致：答错的题已自动入待补答队列；跳过的题判负但不入队
            if entry["skipped"]:
                entry["disposition"] = "跳过判负，不补答"
            elif score is not None and score.get("total", 0.0) < SCORE_PASS_THRESHOLD:
                entry["disposition"] = "答错，已加入待补答队列"
            else:
                entry["disposition"] = "通过"
            per_question.append(entry)
            # retry_list 是报告展示用的"需重背"清单：答错的题已自动入待补答队列；跳过的题不入队，仅在此列出
            if entry["skipped"] or (score is not None and score.get("total", 0.0) < SCORE_PASS_THRESHOLD):
                retry_list.append(question.id)

        # 「错题去向」说明文案按本场实际情况生成（前端直接渲染，不写死）
        has_failed = any(e["disposition"] == "答错，已加入待补答队列" for e in per_question)
        has_skipped = any(e["skipped"] for e in per_question)
        if has_failed and has_skipped:
            retry_note = "答错的题已自动加入「记忆训练」待补答队列；跳过的题判负不补答，未入队"
        elif has_failed:
            retry_note = "已自动加入「记忆训练」待补答队列，复习巩固在那里完成"
        elif has_skipped:
            retry_note = "跳过的题判负不补答，未加入待补答队列"
        else:
            retry_note = "本场没有答错或跳过的题"

        analysis = await self._analyze_weakness(per_question)
        suggestions = self._build_suggestions(db, per_question)
        totals = [e["score"]["total"] for e in per_question if e.get("score")]
        return {
            "session_id": session.id,
            "mode": session.mode,
            "tech_stack": session.tech_stack,
            "question_count": len(per_question),
            "avg_total": round(sum(totals) / len(totals), 1) if totals else None,
            "per_question": per_question,
            "analysis": analysis,
            "suggestions": suggestions,
            "retry_list": retry_list,
            "retry_note": retry_note,
        }

    async def _analyze_weakness(self, per_question: list[dict[str, Any]]) -> dict[str, Any]:
        """LLM 综合分析本场回答：遗漏考点、理解偏差、背诵痕迹、整体薄弱方向。"""
        items_text = []
        for i, e in enumerate(per_question, 1):
            if e["skipped"]:
                items_text.append(f"{i}. 【题目】{e['stem']}\n   【结果】候选人跳过未作答，记为失败。")
                continue
            score = e["score"]
            missed = "、".join(score.get("missed_points") or []) or "无"
            items_text.append(
                f"{i}. 【题目】{e['stem']}\n"
                f"   【候选人回答】{e['user_answer']}\n"
                f"   【标准答案】{e['standard_answer']}\n"
                f"   【总分】{score.get('total')}（准确性 {score.get('accuracy')} / "
                f"逻辑 {score.get('logic')} / 自然度 {score.get('naturalness')}），"
                f"背诵痕迹：{'有' if score.get('is_reciting') else '无'}，遗漏关键点：{missed}"
            )
        user_prompt = (
            "下面是一场技术面试的逐题作答与评分数据：\n\n"
            + "\n\n".join(items_text)
            + "\n\n请综合整场表现输出复盘分析，JSON 字段如下：\n"
            '- weak_points：薄弱知识点列表（字符串数组，具体到考点，如"GIL 与 GC 的协同关系"）；\n'
            "- misunderstandings：理解偏差分析，指出候选人哪些回答暴露了对概念的错误理解（无则写「未发现明显理解偏差」）；\n"
            "- reciting_notes：背诵痕迹分析，结合重合率与表达自然度点评（无则写「无明显背诵痕迹」）；\n"
            "- overall：整体薄弱方向总结与一句话总评（100 字以内）。\n"
            "只输出 JSON 对象本身。"
        )
        messages = [
            {"role": "system", "content": _REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        try:
            _, content = await self.llm.chat(messages, temperature=0.3)
            parsed = parse_json_object(content)
        except Exception as exc:  # LLM 不可用时给出兜底结构，报告其他部分不受影响
            logger.warning("复盘分析 LLM 调用失败：%s", exc)
            parsed = {}
        weak = parsed.get("weak_points")
        return {
            "weak_points": [str(p) for p in weak] if isinstance(weak, list) else [],
            "misunderstandings": str(parsed.get("misunderstandings", "（分析暂不可用）")),
            "reciting_notes": str(parsed.get("reciting_notes", "（分析暂不可用）")),
            "overall": str(parsed.get("overall", "（分析暂不可用）")),
        }

    def _build_suggestions(self, db: DBSession, per_question: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """学习建议：本场失败/跳过题优先背诵 + 历史平均分低的题补充推荐。"""
        suggestions: list[dict[str, Any]] = []
        listed: set[int] = set()
        for e in per_question:
            if e["skipped"]:
                reason = "本场跳过未作答，建议优先背诵"
            elif e["score"] and e["score"].get("total", 0.0) < SCORE_PASS_THRESHOLD:
                reason = f"本场得分 {e['score']['total']}，低于 {SCORE_PASS_THRESHOLD:.0f} 分"
            else:
                continue
            listed.add(e["question_id"])
            suggestions.append({
                "question_id": e["question_id"],
                "stem": e["stem"],
                "tech_stack": e["tech_stack"],
                "reason": reason,
            })
        # 历史低分题：全场历史平均分 < 阈值，按平均分升序补充
        rows = db.exec(select(Record.question_id, Record.score_total)).all()
        scores_by_qid: dict[int, list[float]] = {}
        for qid, total in rows:
            if total is not None:
                scores_by_qid.setdefault(qid, []).append(total)
        history_low = sorted(
            (
                (qid, sum(ts) / len(ts))
                for qid, ts in scores_by_qid.items()
                if qid not in listed and sum(ts) / len(ts) < SCORE_PASS_THRESHOLD
            ),
            key=lambda item: item[1],
        )[:REVIEW_SUGGEST_HISTORY_COUNT]
        for qid, avg in history_low:
            question = db.get(Question, qid)
            if question is None:
                continue
            suggestions.append({
                "question_id": qid,
                "stem": question.stem,
                "tech_stack": question.tech_stack,
                "reason": f"历史平均分 {avg:.1f}，长期薄弱",
            })
        return suggestions
