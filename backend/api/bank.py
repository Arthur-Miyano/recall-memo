# -*- coding: utf-8 -*-
"""题库总览接口：技术栈 → 知识点两级分组 + 背诵状态格 + 圈选重点背诵 + 录入题库。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session as DBSession, select

from agents import importer
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


# ---------- 录入题库（含清洗去重） ----------

class ImportRequest(BaseModel):
    text: str  # 原始文本或 JSON 数组字符串
    dedupe: bool = True  # 是否按题干相似度去重（阈值见 importer.SIMILARITY_THRESHOLD）


def _title_of(stem: str) -> str:
    """结果清单里的题目标题：题干截断。"""
    stem = stem.strip().replace("\n", " ")
    return stem if len(stem) <= 20 else stem[:19] + "…"


@router.post("/import")
async def bank_import(req: ImportRequest, db: DBSession = Depends(get_db)):
    """录入题库：解析 → LLM 提取/补全 → 相似度去重 → 入库。

    流程：
    1. 解析 text（JSON 数组直接解析；纯文本按 空行/--- 切分，识别"答案：""技术栈：""知识点："行）；
    2. 规则解析不出的片段，一次 LLM 调用做结构化提取；
    3. 缺答案/缺技术栈的题，一次 LLM 调用批量补全（tech_stack 限定 python/agent/vue3）；
    4. dedupe=true 时，与库内题目 + 本批次已接受题逐一算题干相似度，≥ 阈值跳过；
    5. 通过的题插入 Question 表（tags=[技术栈, 知识点]，与种子脚本约定一致）。

    LLM 不可用时降级：能解析完整的题照常入库，缺答案的进 errors。
    """
    result: dict = {"imported": [], "skipped": [], "enriched": [], "errors": []}
    if not req.text.strip():
        result["errors"].append({"title": "（空输入）", "reason": "没有可解析的内容"})
        return result

    # 1. 规则解析
    items, leftovers = importer.parse_text(req.text)

    # 2. LLM 结构化提取兜底（解析不出的片段）
    if leftovers:
        try:
            items += await importer.llm_extract(leftovers)
        except importer.LLMProviderUnavailableError as exc:
            for chunk in leftovers:
                result["errors"].append({
                    "title": _title_of(chunk),
                    "reason": f"规则解析失败，且 LLM 不可用：{exc}",
                })
        except ValueError as exc:
            for chunk in leftovers:
                result["errors"].append({"title": _title_of(chunk), "reason": f"LLM 提取失败：{exc}"})

    # 3. 规整字段（技术栈归一化），丢掉连题干都没有的
    valid: list[dict] = []
    for it in items:
        stem = str(it.get("stem") or "").strip()
        if not stem:
            continue
        it["stem"] = stem
        stack = importer.normalize_stack(it.get("tech_stack"))
        it["tech_stack"] = stack or ""  # 无法识别的留空，交给补全
        valid.append(it)

    # 4. LLM 批量补全缺 answer / tech_stack 的题
    try:
        enrich_marks = await importer.llm_enrich(valid)
    except importer.LLMProviderUnavailableError:
        enrich_marks = [{"fields": []} for _ in valid]  # 降级：不补全，后面按缺字段进 errors
    except ValueError:
        enrich_marks = [{"fields": []} for _ in valid]

    # 5. 去重 + 入库
    existing_stems = [q.stem for q in db.exec(select(Question)).all()]
    accepted_stems: list[str] = []
    for it, mark in zip(valid, enrich_marks):
        title = _title_of(it["stem"])
        stack = importer.normalize_stack(it.get("tech_stack")) or "python"
        answer = str(it.get("answer") or "").strip()
        if not answer:
            result["errors"].append({"title": title, "reason": "缺少标准答案，且 LLM 未能补全"})
            continue
        if not it.get("tech_stack"):
            it["tech_stack"] = stack  # LLM 也没给出分类时兜底 python
        if req.dedupe:
            best_stem, best_sim = None, 0.0
            for other in existing_stems + accepted_stems:
                sim = importer.stem_similarity(it["stem"], other)
                if sim > best_sim:
                    best_stem, best_sim = other, sim
            if best_sim >= importer.SIMILARITY_THRESHOLD:
                result["skipped"].append({
                    "title": title,
                    "similar_to": _title_of(best_stem or ""),
                    "similarity": round(best_sim * 100),
                })
                continue
        question = Question(
            stem=it["stem"],
            answer=answer,
            tech_stack=stack,
            difficulty=it.get("difficulty") or "medium",
            keywords=it.get("keywords") or [],
            # tags 约定：第 1 个是技术栈大类，第 2 个是知识点分组（总览/图谱按它分组）
            tags=[stack, str(it.get("knowledge_point") or "未分类").strip() or "未分类"],
        )
        db.add(question)
        db.flush()  # 拿到自增 id 供响应回显
        accepted_stems.append(it["stem"])
        result["imported"].append({"id": question.id, "title": title, "tech_stack": stack})
        if mark["fields"]:
            result["enriched"].append({"title": title, "fields": mark["fields"]})
    db.commit()
    return result
