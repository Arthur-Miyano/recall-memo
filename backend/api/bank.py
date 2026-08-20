# -*- coding: utf-8 -*-
"""题库接口（HTTP 适配层）：总览分组 / 重点圈选 / 增删改迁移 / 录入。

本模块只做请求解析与响应组装：
- 录入流程编排（解析→提取/补全→判重→入库、后台任务）在 application/importer.py；
- 上传文件解析（PDF/文本）在 infrastructure/documents.py。
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session as DBSession, select

from agents import importer
from agents.base import SCORE_PASS_THRESHOLD
from api.deps import get_db
from application.importer import IMPORT_JOBS, job_view, new_job, run_import, run_import_job
from infrastructure.documents import decode_source_text
from models import Question, QuestionFocus, QuestionGroup, Record, RetryQueueItem, Session

router = APIRouter(prefix="/bank", tags=["bank"])

# 技术栈展示名（覆盖 importer.ALLOWED_STACKS 全部 canonical key；
# 白名单外 LLM 自由命名的 key 用 STACK_DISPLAY.get(stack, stack) 兜底原样显示）
STACK_DISPLAY = {
    "python": "Python", "java": "Java", "go": "Go", "c": "C", "cpp": "C++",
    "csharp": "C#", "php": "PHP", "javascript": "JavaScript",
    "vue3": "Vue 3", "react": "React", "database": "Database",
    "network": "计算机网络", "os": "操作系统", "algorithm": "算法",
    "design_pattern": "设计模式", "distributed": "分布式", "linux": "Linux",
    "devops": "DevOps", "agent": "Agent", "hr": "HR", "other": "其他",
}


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
    # 记录只取"每题最新得分"所需列，避免整行 ORM 对象载入
    records = db.exec(select(Record.id, Record.question_id, Record.score_total, Record.created_at)).all()
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


@router.delete("/questions/{question_id}")
def bank_delete_question(question_id: int, db: DBSession = Depends(get_db)):
    """删除一道题及其全部关联数据（同一事务提交）：

    - 答题记录 Record、重点标记 QuestionFocus、待补答 RetryQueueItem 一并删除
      （这些小表无外键约束，需手工级联）；
    - 追问组 QuestionGroup：从 question_ids 中移除该题，组空了连组删除；
    - 历史会话 Session：摘除 question_ids / quiz_order / current_question_id 里的引用，
      会话本身与复盘快照（context.review_report）保留。
    题目不存在返回 404。
    """
    question = db.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="题目不存在")

    removed_records = 0
    for r in db.exec(select(Record).where(Record.question_id == question_id)).all():
        db.delete(r)
        removed_records += 1

    focus = db.exec(select(QuestionFocus).where(QuestionFocus.question_id == question_id)).first()
    if focus:
        db.delete(focus)
    retry = db.exec(select(RetryQueueItem).where(RetryQueueItem.question_id == question_id)).first()
    if retry:
        db.delete(retry)

    removed_groups = 0
    for g in db.exec(select(QuestionGroup)).all():
        if question_id in (g.question_ids or []):
            g.question_ids = [qid for qid in g.question_ids if qid != question_id]
            if g.question_ids:
                db.add(g)
            else:
                db.delete(g)
                removed_groups += 1

    touched_sessions = 0
    for s in db.exec(select(Session)).all():
        changed = False
        if question_id in (s.question_ids or []):
            s.question_ids = [qid for qid in s.question_ids if qid != question_id]
            changed = True
        if question_id in (s.quiz_order or []):
            s.quiz_order = [qid for qid in s.quiz_order if qid != question_id]
            changed = True
        if s.current_question_id == question_id:
            s.current_question_id = None
            changed = True
        if changed:
            db.add(s)
            touched_sessions += 1

    db.delete(question)
    db.commit()
    return {
        "ok": True,
        "deleted": question_id,
        "removed_records": removed_records,
        "removed_focus": bool(focus),
        "removed_retry": bool(retry),
        "removed_groups": removed_groups,
        "touched_sessions": touched_sessions,
    }


def _question_view(question: Question) -> dict:
    """题目完整字段视图（PATCH 响应用）。"""
    return {
        "id": question.id,
        "stem": question.stem,
        "answer": question.answer,
        "tech_stack": question.tech_stack,
        "difficulty": question.difficulty,
        "keywords": question.keywords,
        "tags": question.tags,
        "variants": question.variants,
        "created_at": question.created_at,
    }


class QuestionPatchRequest(BaseModel):
    """改题请求：全部字段可选，至少提供一个；tech_stack 传空字符串表示不改。"""

    stem: Optional[str] = None
    answer: Optional[str] = None
    tech_stack: Optional[str] = None
    difficulty: Optional[str] = None
    keywords: Optional[list[str]] = None
    tags: Optional[list[str]] = None


@router.patch("/questions/{question_id}")
def bank_patch_question(question_id: int, req: QuestionPatchRequest, db: DBSession = Depends(get_db)):
    """改题：改技术栈 + 改内容（题干/答案/难度/关键词/标签），返回更新后的完整题目。

    - tech_stack 过 importer.normalize_stack：空字符串视为"不改"；
      非空但归一化后为空（无法清洗出有效 slug）返回 400；
    - 至少提供一个有效字段，否则 400；题目不存在 404；
    - 注意：stem 是录入去重的相似度基准（importer.stem_similarity），
      改题干会影响后续导入时的判重结果，这里只更新不额外处理。
    """
    question = db.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="题目不存在")

    changed = False
    if req.tech_stack is not None and req.tech_stack.strip():
        stack = importer.normalize_stack(req.tech_stack)
        if not stack:
            raise HTTPException(status_code=400, detail=f"无法识别的技术栈：{req.tech_stack}")
        question.tech_stack = stack
        changed = True
    if req.stem is not None:
        stem = req.stem.strip()
        if not stem:
            raise HTTPException(status_code=400, detail="题干不能为空")
        question.stem = stem
        changed = True
    if req.answer is not None:
        question.answer = req.answer.strip()
        changed = True
    if req.difficulty is not None:
        question.difficulty = req.difficulty.strip()
        changed = True
    if req.keywords is not None:
        question.keywords = [str(k) for k in req.keywords]
        changed = True
    if req.tags is not None:
        question.tags = [str(t) for t in req.tags]
        changed = True
    if not changed:
        raise HTTPException(status_code=400, detail="没有提供任何要修改的字段")

    db.add(question)
    db.commit()
    db.refresh(question)
    return _question_view(question)


class MigrateRequest(BaseModel):
    question_ids: list[int]  # 要迁移的题目 id 列表
    to_stack: str  # 目标技术栈（过 normalize_stack，支持自由命名）


@router.post("/questions/migrate")
def bank_migrate_questions(req: MigrateRequest, db: DBSession = Depends(get_db)):
    """批量迁移：把选中题目改到目标技术栈（单事务提交）。

    不存在的 id 忽略但在响应 missing 里列出；只改 tech_stack，
    tags 第 1 个的技术栈大类约定不联动（分组展示以 tech_stack 为准）。
    """
    if not req.question_ids:
        raise HTTPException(status_code=400, detail="question_ids 不能为空")
    to_stack = importer.normalize_stack(req.to_stack)
    if not to_stack:
        raise HTTPException(status_code=400, detail=f"无法识别的目标技术栈：{req.to_stack}")

    ids = list(dict.fromkeys(req.question_ids))  # 去重保序
    existing = {q.id: q for q in db.exec(select(Question).where(Question.id.in_(ids))).all()}
    missing = [qid for qid in ids if qid not in existing]
    for qid in ids:
        question = existing.get(qid)
        if question is not None:
            question.tech_stack = to_stack
            db.add(question)
    db.commit()
    return {"ok": True, "moved": len(ids) - len(missing), "missing": missing, "to_stack": to_stack}


# ---------- 录入题库（流程编排在 application/importer.py） ----------

class ImportRequest(BaseModel):
    text: str  # 原始文本或 JSON 数组字符串
    dedupe: bool = True  # 是否按题干相似度去重（阈值见 importer.SIMILARITY_THRESHOLD）
    max_questions: Optional[int] = None  # 最多录入题数，None=不限（便于测试与分批导入）
    force_llm_extract: bool = False  # 强制整段走 LLM 结构化提取（跳过规则分段，适合无标签长文）


@router.post("/import")
async def bank_import(req: ImportRequest, db: DBSession = Depends(get_db)):
    """录入题库（粘贴文本/JSON）：走共用清洗管线 run_import（application/importer.py）。

    流程：
    1. 解析 text（JSON 数组直接解析；纯文本按 空行/--- 切分，识别"答案：""技术栈：""知识点："行）；
       force_llm_extract=true 时跳过规则分段，整段切块走 LLM 提取真问题；
    2. 规则解析不出的片段，一次 LLM 调用做结构化提取；
    3. 缺答案/缺技术栈的题，一次 LLM 调用批量补全（tech_stack 分类指引见 importer._STACK_GUIDE）；
    4. dedupe=true 时，与库内题目 + 本批次已接受题逐一算题干相似度，≥ 阈值跳过；
    5. 通过的题插入 Question 表（tags=[技术栈, 知识点]，与种子脚本约定一致）。

    LLM 不可用时降级：能解析完整的题照常入库，缺答案的进 errors。
    """
    return await run_import(req.text, req.dedupe, db, req.max_questions, req.force_llm_extract)


# ---------- 文件上传录入（PDF / md / txt / json） ----------

@router.post("/import-file")
async def bank_import_file(
    file: UploadFile = File(...),  # 上传文件：.pdf 用 pypdf 提取，.md/.txt/.json 读文本
    dedupe: bool = Form(True),
    max_questions: Optional[int] = Form(None),  # 最多录入题数，None=不限
    force_llm_extract: bool = Form(False),  # 强制整段走 LLM 提取；.pdf 自动为 True
    db: DBSession = Depends(get_db),
):
    """文件录入题库：提取文本后走与 /import 完全相同的清洗管线 run_import。

    解析（含 PDF）是 CPU 活，统一放工作线程（infrastructure/documents.py），
    避免大文件阻塞事件循环——与后台任务路径同一入口，不会再出现一处线程化一处遗漏。
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="文件为空")
    text, force_pdf = await asyncio.to_thread(decode_source_text, file.filename or "", raw)
    force = force_llm_extract or force_pdf
    return await run_import(text, dedupe, db, max_questions, force)


# ---------- 后台录入任务（多文件 + 进度可查；任务体在 application/importer.py） ----------

@router.post("/import-jobs", status_code=202)
async def bank_import_job_create(
    files: Optional[list[UploadFile]] = File(None),  # 多文件：.pdf / .md / .txt / .json
    text: Optional[str] = Form(None),               # 粘贴文本（与文件可同时给）
    dedupe: bool = Form(True),
):
    """创建后台录入任务：支持多文件 + 粘贴文本，立即返回 job_id，前端轮询进度。

    任务在后台协程执行，关闭面板/切页面不影响录入；重开面板用 GET latest 重新挂上。
    """
    sources: list[tuple[str, bytes]] = []
    for f in files or []:
        raw = await f.read()
        if raw:
            sources.append((f.filename or "未命名文件", raw))
    if not sources and not (text and text.strip()):
        raise HTTPException(status_code=400, detail="没有可录入的内容（未选择文件也未粘贴文本）")
    label = "、".join(n for n, _ in sources) or "粘贴文本"
    job = new_job(label)
    asyncio.create_task(run_import_job(job, sources, text, dedupe))
    return {"job_id": job["id"], "status": job["status"]}


@router.get("/import-jobs/latest")
def bank_import_job_latest():
    """最近一次录入任务：前端打开录入面板时调用，任务还在跑就重新挂上轮询。"""
    if not IMPORT_JOBS:
        return {"job": None}
    return {"job": job_view(max(IMPORT_JOBS.values(), key=lambda j: j["created_at"]))}


@router.get("/import-jobs/{job_id}")
def bank_import_job_status(job_id: str):
    """录入任务进度：status/stage/进度计数；完成后带 result（逐文件清单 + 总计）。"""
    job = IMPORT_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在或已被清理")
    return job_view(job)
