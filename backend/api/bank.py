# -*- coding: utf-8 -*-
"""题库总览接口：技术栈 → 知识点两级分组 + 背诵状态格 + 圈选重点背诵 + 录入题库。"""
import asyncio
import io
import time
import uuid
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session as DBSession, select

from agents import importer
from agents.base import SCORE_PASS_THRESHOLD
from api.deps import get_db
import database
from models import Question, QuestionFocus, Record, RetryQueueItem

router = APIRouter(prefix="/bank", tags=["bank"])

# 技术栈展示名
STACK_DISPLAY = {"python": "Python", "agent": "Agent", "vue3": "Vue 3", "database": "Database"}


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


# ---------- 录入题库（含清洗去重） ----------

class ImportRequest(BaseModel):
    text: str  # 原始文本或 JSON 数组字符串
    dedupe: bool = True  # 是否按题干相似度去重（阈值见 importer.SIMILARITY_THRESHOLD）
    max_questions: Optional[int] = None  # 最多录入题数，None=不限（便于测试与分批导入）
    force_llm_extract: bool = False  # 强制整段走 LLM 结构化提取（跳过规则分段，适合无标签长文）


def _title_of(stem: str) -> str:
    """结果清单里的题目标题：题干截断。"""
    stem = stem.strip().replace("\n", " ")
    return stem if len(stem) <= 20 else stem[:19] + "…"


async def _run_import(text: str, dedupe: bool, db: DBSession,
                      max_questions: Optional[int] = None,
                      force_llm_extract: bool = False,
                      progress: Optional[Callable[[str, int, int], None]] = None) -> dict:
    """录入清洗共用管线（/import 与 /import-file 共用）：

    解析 → LLM 提取/补全 → 相似度去重 → 入库。
    max_questions 在规整字段后截断条目数（同时限制 LLM 补全的规模），方便测试与分批导入。
    force_llm_extract=True 时跳过规则分段，整段按块走 LLM 提取真问题
    （PDF 提取的文本没有「答案：」标签行，规则分段会把正文段落当成题干）。
    progress 为可选回调 progress(阶段名, 已完成, 总数)，供后台录入任务汇报进度。
    """

    def _report(stage: str, done: int, total: int) -> None:
        if progress:
            progress(stage, done, total)

    result: dict = {"imported": [], "skipped": [], "enriched": [], "errors": []}
    if not text.strip():
        result["errors"].append({"title": "（空输入）", "reason": "没有可解析的内容"})
        return result

    # 1. 解析 + 2. LLM 结构化提取
    if force_llm_extract:
        # 强制路径：整段切块走 LLM，不经过规则分段
        try:
            extracted, extract_errors = await importer.extract_questions_with_llm(
                text, progress=lambda i, n: _report("LLM 提取真问题", i, n),
            )
            items = extracted
            for err in extract_errors:
                result["errors"].append({"title": "（LLM 提取）", "reason": err})
        except importer.LLMProviderUnavailableError as exc:
            result["errors"].append({"title": "（LLM 提取）", "reason": f"LLM 不可用：{exc}"})
            return result
    else:
        items, leftovers = importer.parse_text(text)
        if leftovers:
            _report("LLM 结构化提取", 0, 1)
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
            _report("LLM 结构化提取", 1, 1)

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

    # max_questions：只处理前 N 题（截断在 LLM 补全之前，避免不必要的调用）
    if max_questions is not None and max_questions >= 0:
        valid = valid[:max_questions]

    # 4. LLM 批量补全缺 answer / tech_stack 的题
    _report("AI 补全缺字段", 0, 1)
    try:
        enrich_marks = await importer.llm_enrich(valid)
    except importer.LLMProviderUnavailableError:
        enrich_marks = [{"fields": []} for _ in valid]  # 降级：不补全，后面按缺字段进 errors
    except ValueError:
        enrich_marks = [{"fields": []} for _ in valid]
    _report("AI 补全缺字段", 1, 1)

    # 5. 去重 + 入库
    existing_stems = [q.stem for q in db.exec(select(Question)).all()]
    accepted_stems: list[str] = []
    for idx, (it, mark) in enumerate(zip(valid, enrich_marks), start=1):
        _report("去重入库", idx, len(valid))
        title = _title_of(it["stem"])
        stack = importer.normalize_stack(it.get("tech_stack")) or "python"
        answer = str(it.get("answer") or "").strip()
        if not answer:
            result["errors"].append({"title": title, "reason": "缺少标准答案，且 LLM 未能补全"})
            continue
        if not it.get("tech_stack"):
            it["tech_stack"] = stack  # LLM 也没给出分类时兜底 python
        if dedupe:
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


@router.post("/import")
async def bank_import(req: ImportRequest, db: DBSession = Depends(get_db)):
    """录入题库（粘贴文本/JSON）：走共用清洗管线 _run_import。

    流程：
    1. 解析 text（JSON 数组直接解析；纯文本按 空行/--- 切分，识别"答案：""技术栈：""知识点："行）；
       force_llm_extract=true 时跳过规则分段，整段切块走 LLM 提取真问题；
    2. 规则解析不出的片段，一次 LLM 调用做结构化提取；
    3. 缺答案/缺技术栈的题，一次 LLM 调用批量补全（tech_stack 限定 python/agent/vue3/database）；
    4. dedupe=true 时，与库内题目 + 本批次已接受题逐一算题干相似度，≥ 阈值跳过；
    5. 通过的题插入 Question 表（tags=[技术栈, 知识点]，与种子脚本约定一致）。

    LLM 不可用时降级：能解析完整的题照常入库，缺答案的进 errors。
    """
    return await _run_import(req.text, req.dedupe, db, req.max_questions, req.force_llm_extract)


# ---------- 文件上传录入（PDF / md / txt / json） ----------

# 按文本读取的扩展名；.pdf 走 pypdf 提取
_TEXT_EXTS = {".md", ".txt", ".json"}


def _extract_pdf_text(raw: bytes) -> str:
    """pypdf 提取 PDF 全文（逐页拼接）。失败/无文本抛 HTTPException 400。"""
    from pypdf import PdfReader  # 延迟导入：PDF 是可选路径，不影响文本导入
    try:
        reader = PdfReader(io.BytesIO(raw))
        pages = [(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:  # 损坏/加密/非 PDF 内容等统一归为无法解析
        raise HTTPException(status_code=400, detail=f"PDF 解析失败：{exc}")
    text = "\n\n".join(p for p in pages if p.strip())
    if not text.strip():
        raise HTTPException(status_code=400, detail="PDF 中未提取到文本（可能是扫描件或图片型 PDF）")
    return text


@router.post("/import-file")
async def bank_import_file(
    file: UploadFile = File(...),  # 上传文件：.pdf 用 pypdf 提取，.md/.txt/.json 读文本
    dedupe: bool = Form(True),
    max_questions: Optional[int] = Form(None),  # 最多录入题数，None=不限
    force_llm_extract: bool = Form(False),  # 强制整段走 LLM 提取；.pdf 自动为 True
    db: DBSession = Depends(get_db),
):
    """文件录入题库：提取文本后走与 /import 完全相同的清洗管线 _run_import。

    PDF 提取出的文本没有「答案：」标签行，规则分段会把正文段落当成题干，
    故 .pdf 一律强制走 LLM 结构化提取真问题。
    """
    import os
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _TEXT_EXTS and ext != ".pdf":
        raise HTTPException(status_code=400, detail=f"不支持的文件类型 {ext or '（无扩展名）'}，仅支持 .pdf / .md / .txt / .json")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="文件为空")
    if ext == ".pdf":
        text = _extract_pdf_text(raw)
    else:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="文本文件解码失败（请使用 UTF-8 编码）")
    force = force_llm_extract or ext == ".pdf"
    return await _run_import(text, dedupe, db, max_questions, force)



# ---------- 后台录入任务（多文件 + 进度可查） ----------

# 录入任务注册表：单机单用户，内存态即可；任务随进程生命周期，重启即清空
IMPORT_JOBS: dict[str, dict[str, Any]] = {}
_IMPORT_JOBS_KEEP = 20  # 只保留最近 N 个任务，防无限增长


def _new_job(label: str) -> dict[str, Any]:
    job: dict[str, Any] = {
        "id": uuid.uuid4().hex[:12],
        "status": "running",          # running / done / error
        "label": label,               # 来源描述：文件名列表或「粘贴文本」
        "file_index": 0,              # 当前处理到第几个来源（从 1 起）
        "file_count": 0,
        "stage": "排队中",
        "stage_done": 0,
        "stage_total": 0,
        "result": None,               # 完成后的逐文件结果 + 总计
        "error": None,
        "created_at": time.time(),
        "finished_at": None,
    }
    IMPORT_JOBS[job["id"]] = job
    if len(IMPORT_JOBS) > _IMPORT_JOBS_KEEP:  # 按创建时间淘汰最旧的
        for old_id in sorted(IMPORT_JOBS, key=lambda k: IMPORT_JOBS[k]["created_at"])[:-_IMPORT_JOBS_KEEP]:
            IMPORT_JOBS.pop(old_id, None)
    return job


def _decode_source_text(filename: str, raw: bytes) -> tuple[str, bool]:
    """按扩展名提取文本：.pdf 走 pypdf（需强制 LLM 提取），.md/.txt/.json 直接解码。"""
    import os
    ext = os.path.splitext(filename or "")[1].lower()
    if ext == ".pdf":
        return _extract_pdf_text(raw), True
    if ext in _TEXT_EXTS:
        try:
            return raw.decode("utf-8"), False
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail=f"{filename}：文本解码失败（请使用 UTF-8 编码）")
    raise HTTPException(
        status_code=400,
        detail=f"{filename}：不支持的文件类型 {ext or '（无扩展名）'}，仅支持 .pdf / .md / .txt / .json",
    )


async def _run_import_job(
    job: dict[str, Any],
    sources: list[tuple[str, bytes]],
    text_input: Optional[str],
    dedupe: bool,
) -> None:
    """后台任务体：逐来源走 _run_import 管线，进度实时写回 job 供前端轮询。

    单个文件解析失败不中断整体：记为该文件的 errors 继续下一个。
    """
    try:
        pending: list[tuple[str, str, bool]] = []  # (来源名, 文本, 是否强制 LLM 提取)
        file_errors: list[dict[str, str]] = []
        if text_input and text_input.strip():
            pending.append(("粘贴文本", text_input, False))
        for name, raw in sources:
            try:
                text, force = _decode_source_text(name, raw)
                pending.append((name, text, force))
            except HTTPException as exc:
                file_errors.append({"file": name, "reason": str(exc.detail)})
        job["file_count"] = len(pending)

        results: list[dict[str, Any]] = []
        # 注意用 database.engine 动态引用（不要 from-import）：测试会 monkeypatch 替换引擎
        with DBSession(database.engine) as db:
            for idx, (name, text, force) in enumerate(pending, start=1):
                job["file_index"] = idx

                def _progress(stage: str, done: int, total: int) -> None:
                    job["stage"] = stage
                    job["stage_done"] = done
                    job["stage_total"] = total

                r = await _run_import(text, dedupe, db, None, force, progress=_progress)
                r["file"] = name
                results.append(r)
        totals = {
            key: sum(len(r[key]) for r in results) for key in ("imported", "skipped", "enriched", "errors")
        }
        job["result"] = {"files": results, "totals": totals, "file_errors": file_errors}
        job["status"] = "done"
        job["stage"] = "完成"
    except Exception as exc:  # 任务级失败：置 error，前端轮询可见
        job["status"] = "error"
        job["error"] = str(exc)
    finally:
        job["finished_at"] = time.time()


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
    job = _new_job(label)
    asyncio.create_task(_run_import_job(job, sources, text, dedupe))
    return {"job_id": job["id"], "status": job["status"]}


def _job_view(job: dict[str, Any]) -> dict[str, Any]:
    return {k: job.get(k) for k in (
        "id", "status", "label", "file_index", "file_count",
        "stage", "stage_done", "stage_total", "result", "error",
        "created_at", "finished_at",
    )}


@router.get("/import-jobs/latest")
def bank_import_job_latest():
    """最近一次录入任务：前端打开录入面板时调用，任务还在跑就重新挂上轮询。"""
    if not IMPORT_JOBS:
        return {"job": None}
    return {"job": _job_view(max(IMPORT_JOBS.values(), key=lambda j: j["created_at"]))}


@router.get("/import-jobs/{job_id}")
def bank_import_job_status(job_id: str):
    """录入任务进度：status/stage/进度计数；完成后带 result（逐文件清单 + 总计）。"""
    job = IMPORT_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在或已被清理")
    return _job_view(job)
