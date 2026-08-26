# -*- coding: utf-8 -*-
"""记忆树提取后台任务：按批调 LLM 生成层级大纲并落库，进度可查。

api/memtree.py 只保留 HTTP 适配；任务注册表集中在这里（与 application/importer.py
同一模式：单机内存态，任务随进程生命周期，重启即清空）。前端关闭面板/切页面不中断
任务，重开面板用 GET latest 重挂轮询。
"""
import time
import uuid
from typing import Any

from sqlmodel import Session as DBSession

import database
import events
from agents.memtree import generate_memory_trees_batch
from llm.errors import LLMError
from models import Question

# 记忆树任务注册表：单机单用户，内存态即可
MEMTREE_JOBS: dict[str, dict[str, Any]] = {}
_MEMTREE_JOBS_KEEP = 20  # 只保留最近 N 个任务，防无限增长

_BATCH_SIZE = 5  # 每次 LLM 调用处理的题数：实测批 10 容易超时，5 比较稳定


def new_memtree_job(label: str, total: int) -> dict[str, Any]:
    job: dict[str, Any] = {
        "id": uuid.uuid4().hex[:12],
        "status": "running",          # running / done / error
        "label": label,               # 范围描述：如「技术栈 Python · 只补缺树」
        "stage": "生成记忆树",
        "stage_done": 0,
        "stage_total": total,
        "result": None,               # 完成后的 {done, failed, failed_ids}
        "error": None,
        "created_at": time.time(),
        "finished_at": None,
    }
    MEMTREE_JOBS[job["id"]] = job
    if len(MEMTREE_JOBS) > _MEMTREE_JOBS_KEEP:  # 按创建时间淘汰最旧的
        for old_id in sorted(MEMTREE_JOBS, key=lambda k: MEMTREE_JOBS[k]["created_at"])[:-_MEMTREE_JOBS_KEEP]:
            MEMTREE_JOBS.pop(old_id, None)
    return job


async def run_memtree_job(job: dict[str, Any], question_ids: list[int]) -> None:
    """后台任务体：按批生成记忆树并逐批落库，进度实时写回 job 供前端轮询。

    单批 LLM 失败（含输出校验失败）不中断整体：整批记失败继续下一批；
    批内单题未返回合法树只记该题失败（下次任务可重试）。
    """
    try:
        # 注意用 database.engine 动态引用（不要 from-import）：测试会 monkeypatch 替换引擎
        with DBSession(database.engine) as db:
            questions = [db.get(Question, qid) for qid in question_ids]
            items = [
                {"id": q.id, "stem": q.stem, "answer": q.answer}
                for q in questions if q is not None
            ]
        job["stage_total"] = len(items)
        done, failed = 0, 0
        failed_ids: list[int] = []
        for i in range(0, len(items), _BATCH_SIZE):
            batch = items[i:i + _BATCH_SIZE]
            try:
                trees = await generate_memory_trees_batch(batch)
            except LLMError as exc:
                failed += len(batch)
                failed_ids.extend(q["id"] for q in batch)
                job["stage_done"] = done + failed
                events.publish("记忆树", f"整批生成失败（{len(batch)} 题）：{exc}")
                continue
            with DBSession(database.engine) as db:
                for q in batch:
                    tree = trees.get(q["id"])
                    target = db.get(Question, q["id"])
                    if tree is None or target is None:
                        failed += 1
                        failed_ids.append(q["id"])
                        continue
                    target.memory_tree = tree
                    done += 1
                db.commit()
            job["stage_done"] = done + failed
            # 顺手广播到 SSE：前端可见"记忆树提取：生成记忆树 15/40"
            events.publish("记忆树", f"生成记忆树 {job['stage_done']}/{job['stage_total']}")
        job["result"] = {"done": done, "failed": failed, "failed_ids": failed_ids}
        job["status"] = "done"
        job["stage"] = "完成"
        events.publish("记忆树", "记忆树生成完成")
    except Exception as exc:  # 任务级失败：置 error，前端轮询可见
        job["status"] = "error"
        job["error"] = str(exc)
        events.publish("记忆树", "记忆树生成失败")
    finally:
        job["finished_at"] = time.time()


def memtree_job_view(job: dict[str, Any]) -> dict[str, Any]:
    return {k: job.get(k) for k in (
        "id", "status", "label", "stage", "stage_done", "stage_total",
        "result", "error", "created_at", "finished_at",
    )}
