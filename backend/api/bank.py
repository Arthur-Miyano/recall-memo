# -*- coding: utf-8 -*-
"""题库总览接口：技术栈 → 知识点两级分组 + 背诵状态格 + 圈选重点背诵。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session as DBSession, select

from agents.base import SCORE_PASS_THRESHOLD
from database import engine
from models import Question, QuestionFocus, Record, RetryQueueItem

router = APIRouter(prefix="/bank", tags=["bank"])

# 技术栈展示名
STACK_DISPLAY = {"python": "Python", "agent": "Agent", "vue3": "Vue 3"}


def get_db():
    with DBSession(engine) as db:
        yield db


def _group_name(question: Question) -> str:
    """知识点分组名：取 tags 第二个（第一个是技术栈大类），兜底"未分类"。"""
    tags = question.tags or []
    if len(tags) > 1:
        return tags[1]
    return tags[0] if tags else "未分类"


def _short_title(question: Question) -> str:
    """格子悬停提示的题目标题：题干截断。"""
    stem = question.stem.strip()
    return stem if len(stem) <= 16 else stem[:15] + "…"


@router.get("/overview")
def bank_overview(db: DBSession = Depends(get_db)):
    """全题列表：按 技术栈 → 知识点 两级分组，每题带背诵状态与重点标记。"""
    questions = list(db.exec(select(Question)).all())
    records = list(db.exec(select(Record)).all())
    focus_ids = {f.question_id for f in db.exec(select(QuestionFocus)).all()}
    retry_ids = {r.question_id for r in db.exec(select(RetryQueueItem)).all()}

    # 每题最新一条已评分记录（按时间升序取最后）
    latest: dict[int, Record] = {}
    for r in sorted(records, key=lambda r: (r.created_at, r.id)):
        latest[r.question_id] = r

    # 分组：stack -> group -> [question]
    stacks: dict[str, dict[str, list[Question]]] = {}
    for q in questions:
        stacks.setdefault(q.tech_stack, {}).setdefault(_group_name(q), []).append(q)

    done_total = 0
    stack_payloads = []
    for stack, groups in stacks.items():
        group_payloads = []
        stack_done = 0
        for group, qs in groups.items():
            cells = []
            for q in qs:
                rec = latest.get(q.id)
                score = rec.score_total if rec and rec.score_total is not None else None
                if score is None:
                    status = "todo"  # 未背
                    tip = f"{_short_title(q)} · 未背"
                elif score >= SCORE_PASS_THRESHOLD:
                    status = "done"  # 已掌握
                    tip = f"{_short_title(q)} · {score:.0f} 分"
                    stack_done += 1
                    done_total += 1
                else:
                    status = "weak"  # 薄弱：答过但最新得分不及格
                    mark = "待补答" if q.id in retry_ids else "薄弱"
                    tip = f"{_short_title(q)} · {score:.0f} 分 · {mark}"
                cells.append({
                    "question_id": q.id,
                    "status": status,
                    "tip": tip,
                    # 短标签：取首个关键词（知识图谱等空间有限处用）
                    "label": (q.keywords or [_short_title(q)])[0],
                    "score": score,
                    "retry": q.id in retry_ids,
                    "focused": q.id in focus_ids,
                })
            group_payloads.append({
                "name": group,
                # 组级"重点背诵"：组内全部题被圈选则视为已圈选
                "starred": bool(qs) and all(q.id in focus_ids for q in qs),
                "cells": cells,
            })
        stack_payloads.append({
            "name": STACK_DISPLAY.get(stack, stack),
            "key": stack,
            "total": sum(len(g["cells"]) for g in group_payloads),
            "done": stack_done,
            "groups": group_payloads,
        })

    return {"done": done_total, "total": len(questions), "stacks": stack_payloads}


class FocusRequest(BaseModel):
    stack: str  # 技术栈 key，如 python / agent / vue3
    group: str  # 知识点分组名
    focused: bool  # True=圈选重点，False=取消


@router.post("/focus")
def bank_focus(req: FocusRequest, db: DBSession = Depends(get_db)):
    """圈选/取消「重点背诵」：按分组整体打标，持久化到 question_focus 表。"""
    questions = [
        q for q in db.exec(select(Question).where(Question.tech_stack == req.stack)).all()
        if _group_name(q) == req.group
    ]
    if not questions:
        return {"ok": False, "detail": "分组不存在或组内无题", "changed": 0}

    existing = {f.question_id: f for f in db.exec(select(QuestionFocus)).all()}
    changed = 0
    for q in questions:
        if req.focused and q.id not in existing:
            db.add(QuestionFocus(question_id=q.id))
            changed += 1
        elif not req.focused and q.id in existing:
            db.delete(existing[q.id])
            changed += 1
    db.commit()
    return {"ok": True, "changed": changed, "starred": req.focused}
