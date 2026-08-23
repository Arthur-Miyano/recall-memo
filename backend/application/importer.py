# -*- coding: utf-8 -*-
"""录入用例：组织完整导入流程（解析 → LLM 提取/补全 → 判重 → 入库）与后台任务状态。

api/bank.py 只保留 HTTP 适配；流程编排与任务注册表集中在这里（单机内存态）。
文档解析（PDF/文本）在 infrastructure/documents.py。
"""
import asyncio
import time
import uuid
from typing import Any, Callable, Optional

from sqlmodel import Session as DBSession, select

import database
import events
from agents import importer
from application.uploads import UploadRejectedError, check_text_length
from config import settings
from llm.errors import LLMOutputValidationError
from infrastructure.documents import DocumentParseError, decode_source_text
from models import Question


class ImportBudgetExceededError(RuntimeError):
    """单任务资源预算耗尽（LLM 请求数 / Token 预算 / 总运行时间上限，§5.1）。"""


class ImportBudget:
    """单任务资源预算：跨来源（多文件 + 粘贴文本）累计，任一维度超限即停止 LLM 调用。

    Token 按输入字符数估算（中文约 1 字 ≈ 1 token，偏保守方向）——router 不返回
    usage 明细，预算是防失控闸门而非精确计费。
    """

    def __init__(self) -> None:
        self.calls = 0
        self.tokens = 0
        self.deadline = time.monotonic() + settings.import_max_seconds

    def before_call(self, messages: list[dict[str, str]]) -> None:
        """每次 LLM 调用前记账并检查预算，超限抛 ImportBudgetExceededError。"""
        self.calls += 1
        self.tokens += sum(len(str(m.get("content") or "")) for m in messages)
        if self.calls > settings.import_max_llm_calls:
            raise ImportBudgetExceededError(
                f"单任务 LLM 请求数超过上限（{settings.import_max_llm_calls} 次）"
            )
        if self.tokens > settings.import_max_token_budget:
            raise ImportBudgetExceededError(
                f"单任务 Token 预算耗尽（约 {settings.import_max_token_budget}）"
            )
        self.check_time()

    def check_time(self) -> None:
        """总运行时间检查（供非 LLM 的长循环周期性地调用）。"""
        if time.monotonic() > self.deadline:
            raise ImportBudgetExceededError(
                f"单任务运行时间超过上限（{settings.import_max_seconds:.0f} 秒）"
            )


def _title_of(stem: str) -> str:
    """结果清单里的题目标题：题干截断。"""
    stem = stem.strip().replace("\n", " ")
    return stem if len(stem) <= 20 else stem[:19] + "…"


def _find_duplicate(stem: str, candidates: list[str]) -> tuple[Optional[str], float]:
    """在候选题干里找最相似的一条。纯 CPU 计算，由调用方放进工作线程执行。"""
    best_stem, best_sim = None, 0.0
    for other in candidates:
        sim = importer.stem_similarity(stem, other)
        if sim > best_sim:
            best_stem, best_sim = other, sim
    return best_stem, best_sim


async def run_import(text: str, dedupe: bool, db: DBSession,
                     max_questions: Optional[int] = None,
                     force_llm_extract: bool = False,
                     progress: Optional[Callable[[str, int, int], None]] = None,
                     budget: Optional[ImportBudget] = None) -> dict:
    """录入清洗共用管线（/import、/import-file 与后台录入任务共用）：

    解析 → LLM 提取/补全 → 相似度去重 → 入库。
    max_questions 在规整字段后截断条目数（同时限制 LLM 补全的规模），方便测试与分批导入；
    不传时按 settings.import_max_questions 兜底（§5.1 单任务最大题目数）。
    force_llm_extract=True 时跳过规则分段，整段按块走 LLM 提取真问题
    （PDF 提取的文本没有「答案：」标签行，规则分段会把正文段落当成题干）。
    progress 为可选回调 progress(阶段名, 已完成, 总数)，供后台录入任务汇报进度。
    budget 为可选资源预算（LLM 请求数/Token/总时长，§5.1）；不传则本任务独立一份。
    文本长度超上限抛 UploadRejectedError(TEXT_TOO_LARGE)；预算耗尽降级为错误条目，不中断已解析部分。
    """

    def _report(stage: str, done: int, total: int) -> None:
        if progress:
            progress(stage, done, total)

    check_text_length(text)
    if budget is None:
        budget = ImportBudget()
    result: dict = {"imported": [], "skipped": [], "enriched": [], "errors": []}
    if not text.strip():
        result["errors"].append({"title": "（空输入）", "reason": "没有可解析的内容"})
        return result

    # 1. 解析 + 2. LLM 结构化提取
    use_llm_extract = force_llm_extract
    items: list[dict] = []
    if not use_llm_extract:
        items, leftovers = importer.parse_text(text)
        if leftovers:
            _report("LLM 结构化提取", 0, 1)
            try:
                items += await importer.llm_extract(leftovers, budget=budget)
            except importer.LLMProviderUnavailableError as exc:
                for chunk in leftovers:
                    result["errors"].append({
                        "title": _title_of(chunk),
                        "reason": f"规则解析失败，且 LLM 不可用：{exc}",
                    })
            except ImportBudgetExceededError as exc:
                for chunk in leftovers:
                    result["errors"].append({"title": _title_of(chunk), "reason": f"已达资源上限：{exc}"})
            except ValueError as exc:
                for chunk in leftovers:
                    result["errors"].append({"title": _title_of(chunk), "reason": f"LLM 提取失败：{exc}"})
            except LLMOutputValidationError as exc:
                for chunk in leftovers:
                    result["errors"].append({"title": _title_of(chunk), "reason": f"LLM 提取输出校验失败：{exc}"})
            _report("LLM 结构化提取", 1, 1)
        # 条目大面积缺答案：这是无标签文档（整篇八股文 md/txt），规则分段把正文段落
        # 都当成了题——改走 LLM 提取真问题（与 PDF 同路径），否则补全会爆量且全是噪声
        missing = sum(1 for it in items if not str(it.get("answer") or "").strip())
        if len(items) >= 10 and missing / len(items) > 0.5:
            use_llm_extract = True
    if use_llm_extract:
        # 强制路径：整段切块走 LLM，不经过规则分段
        try:
            extracted, extract_errors = await importer.extract_questions_with_llm(
                text, progress=lambda i, n: _report("LLM 提取真问题", i, n), budget=budget,
            )
            items = extracted
            for err in extract_errors:
                result["errors"].append({"title": "（LLM 提取）", "reason": err})
        except importer.LLMProviderUnavailableError as exc:
            result["errors"].append({"title": "（LLM 提取）", "reason": f"LLM 不可用：{exc}"})
            return result
        except ImportBudgetExceededError as exc:
            result["errors"].append({"title": "（LLM 提取）", "reason": f"已达资源上限：{exc}"})
            return result

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

    # max_questions：只处理前 N 题（截断在 LLM 补全之前，避免不必要的调用）；
    # 调用方未指定时按 §5.1 的单任务最大题目数兜底
    cap = max_questions if max_questions is not None else settings.import_max_questions
    if cap >= 0:
        valid = valid[:cap]

    # 4. LLM 批量补全缺 answer / tech_stack 的题（分批调用，进度按批回报）
    try:
        enrich_marks = await importer.llm_enrich(
            valid, progress=lambda i, n: _report("AI 补全缺字段", i, n), budget=budget,
        )
    except importer.LLMProviderUnavailableError:
        enrich_marks = [{"fields": []} for _ in valid]  # 降级：不补全，后面按缺字段进 errors
    except (ValueError, LLMOutputValidationError):
        enrich_marks = [{"fields": []} for _ in valid]
    except ImportBudgetExceededError as exc:  # 预算耗尽：降级不补全，已解析的完整题照常入库
        enrich_marks = [{"fields": []} for _ in valid]
        result["errors"].append({"title": "（AI 补全）", "reason": f"已达资源上限：{exc}"})

    # 5. 去重 + 入库
    existing_stems = [q.stem for q in db.exec(select(Question)).all()]
    accepted_stems: list[str] = []
    for idx, (it, mark) in enumerate(zip(valid, enrich_marks), start=1):
        _report("去重入库", idx, len(valid))
        try:
            budget.check_time()  # 大批量判重是长循环：周期检查总运行时间上限（§5.1）
        except ImportBudgetExceededError as exc:
            result["errors"].append({"title": "（去重入库）", "reason": f"已达资源上限：{exc}，其余题目未处理"})
            break
        title = _title_of(it["stem"])
        stack = importer.normalize_stack(it.get("tech_stack")) or "other"
        answer = str(it.get("answer") or "").strip()
        if not answer:
            result["errors"].append({"title": title, "reason": "缺少标准答案，且 LLM 未能补全"})
            continue
        if not it.get("tech_stack"):
            it["tech_stack"] = stack  # LLM 也没给出分类时兜底 other（不进任何技术栈分组）
        if dedupe:
            # 相似度判重是 O(题库规模 × 导入量) 的纯 CPU 计算，放进工作线程——
            # 否则大文档导入期间事件循环被占满，其他请求（如用量面板）会整体卡住
            best_stem, best_sim = await asyncio.to_thread(
                _find_duplicate, it["stem"], existing_stems + accepted_stems
            )
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


# ---------- 后台录入任务（多文件 + 进度可查） ----------

# 录入任务注册表：单机单用户，内存态即可；任务随进程生命周期，重启即清空
IMPORT_JOBS: dict[str, dict[str, Any]] = {}
_IMPORT_JOBS_KEEP = 20  # 只保留最近 N 个任务，防无限增长


def new_job(label: str) -> dict[str, Any]:
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


async def run_import_job(
    job: dict[str, Any],
    sources: list[tuple[str, bytes]],
    text_input: Optional[str],
    dedupe: bool,
    file_errors: Optional[list[dict[str, str]]] = None,
) -> None:
    """后台任务体：逐来源走 run_import 管线，进度实时写回 job 供前端轮询。

    单个文件解析失败不中断整体：记为该文件的 errors 继续下一个。
    file_errors 为创建任务前已被上传策略拒绝的文件清单（§5.1），并入结果返回。
    """
    try:
        pending: list[tuple[str, str, bool]] = []  # (来源名, 文本, 是否强制 LLM 提取)
        file_errors = list(file_errors or [])
        if text_input and text_input.strip():
            pending.append(("粘贴文本", text_input, False))
        for name, raw in sources:
            try:
                # PDF 解析同样是 CPU 活，放工作线程，避免导入期间卡死其他请求
                text, force = await asyncio.to_thread(decode_source_text, name, raw)
                pending.append((name, text, force))
            except DocumentParseError as exc:
                file_errors.append({"file": name, "reason": str(exc)})
        job["file_count"] = len(pending)

        results: list[dict[str, Any]] = []
        # 单任务资源预算（§5.1）：LLM 请求数/Token/总时长跨全部来源累计
        budget = ImportBudget()
        # 注意用 database.engine 动态引用（不要 from-import）：测试会 monkeypatch 替换引擎
        with DBSession(database.engine) as db:
            for idx, (name, text, force) in enumerate(pending, start=1):
                job["file_index"] = idx

                def _progress(stage: str, done: int, total: int) -> None:
                    job["stage"] = stage
                    job["stage_done"] = done
                    job["stage_total"] = total
                    # 顺手广播到 SSE：前端可见"录入 Agent：LLM 提取真问题 3/10"
                    events.publish("录入", f"{name} · {stage} {done}/{total}")

                try:
                    r = await run_import(text, dedupe, db, None, force, progress=_progress, budget=budget)
                except UploadRejectedError as exc:
                    # 单来源文本超限不中断整体：记为该来源的错误继续下一个
                    r = {"imported": [], "skipped": [], "enriched": [],
                         "errors": [{"title": name, "reason": str(exc)}]}
                r["file"] = name
                results.append(r)
        totals = {
            key: sum(len(r[key]) for r in results) for key in ("imported", "skipped", "enriched", "errors")
        }
        job["result"] = {"files": results, "totals": totals, "file_errors": file_errors}
        job["status"] = "done"
        job["stage"] = "完成"
        events.publish("录入", "录入完成")
    except Exception as exc:  # 任务级失败：置 error，前端轮询可见
        job["status"] = "error"
        job["error"] = str(exc)
        events.publish("录入", "录入失败")
    finally:
        job["finished_at"] = time.time()


def job_view(job: dict[str, Any]) -> dict[str, Any]:
    return {k: job.get(k) for k in (
        "id", "status", "label", "file_index", "file_count",
        "stage", "stage_done", "stage_total", "result", "error",
        "created_at", "finished_at",
    )}
