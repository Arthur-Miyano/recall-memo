# -*- coding: utf-8 -*-
"""记忆树提取接口（HTTP 适配层）：按栈统计覆盖情况 + 后台生成任务。

本模块只做请求解析与响应组装；任务注册表与生成流程编排在 application/memtree_jobs.py。
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session as DBSession, select

from api.deps import get_db
from application.memtree_jobs import (
    MEMTREE_JOBS, memtree_job_view, new_memtree_job, run_memtree_job,
)
from models import Question

router = APIRouter(prefix="/memtree", tags=["memtree"])


@router.get("/status")
def memtree_status(db: DBSession = Depends(get_db)):
    """按技术栈分组统计记忆树覆盖情况：栈名 / 总题数 / 已有树 / 缺树，外加总计。"""
    rows = db.exec(select(Question.tech_stack, Question.memory_tree)).all()
    groups: dict[str, dict] = {}
    for stack, tree in rows:
        g = groups.setdefault(stack, {"tech_stack": stack, "total": 0, "with_tree": 0})
        g["total"] += 1
        if tree is not None:
            g["with_tree"] += 1
    stacks = []
    for key in sorted(groups):
        g = groups[key]
        g["missing"] = g["total"] - g["with_tree"]
        stacks.append(g)
    total = {
        "tech_stack": "全部",
        "total": sum(g["total"] for g in stacks),
        "with_tree": sum(g["with_tree"] for g in stacks),
    }
    total["missing"] = total["total"] - total["with_tree"]
    return {"stacks": stacks, "total": total}


# ---------- 后台生成任务（任务体在 application/memtree_jobs.py） ----------

class MemtreeJobRequest(BaseModel):
    stack: Optional[str] = None            # 只跑该技术栈；不给 = 全部栈
    regenerate: bool = False               # true = 范围内全部题重新生成；false = 只补缺树的题
    question_ids: Optional[list[int]] = None  # 给了就只跑这些题（忽略 stack/regenerate）


@router.post("/jobs", status_code=202)
async def memtree_job_create(req: MemtreeJobRequest, db: DBSession = Depends(get_db)):
    """创建记忆树生成任务：立即返回 job_id，前端轮询进度。

    范围语义：question_ids 优先（只跑这些题）；否则按 stack 过滤（不给 = 全部栈）；
    regenerate=false 只跑 memory_tree 为空的题，true 跑范围内全部题。
    """
    if req.question_ids is not None:
        ids = list(dict.fromkeys(req.question_ids))  # 去重保序
        label = f"指定 {len(ids)} 题"
    else:
        # 缺树判断放 Python 侧：JSON 列里 None 可能落库为 'null' 字符串而非 SQL NULL
        # （SQLAlchemy JSON 默认 none_as_null=False），IS NULL 谓词查不到新插入的行
        stmt = select(Question.id, Question.memory_tree).order_by(Question.id)
        if req.stack:
            stmt = stmt.where(Question.tech_stack == req.stack)
        ids = [qid for qid, tree in db.exec(stmt).all() if req.regenerate or tree is None]
        label = f"技术栈 {req.stack} · " if req.stack else "全部栈 · "
        label += "重新生成全部" if req.regenerate else "只补缺树"
    if not ids:
        raise HTTPException(status_code=400, detail="没有需要生成的题目")
    job = new_memtree_job(label, len(ids))
    asyncio.create_task(run_memtree_job(job, ids))
    return {"job_id": job["id"], "status": job["status"]}


@router.get("/jobs/latest")
def memtree_job_latest():
    """最近一次记忆树任务：前端打开面板时调用，任务还在跑就重新挂上轮询。"""
    if not MEMTREE_JOBS:
        return {"job": None}
    return {"job": memtree_job_view(max(MEMTREE_JOBS.values(), key=lambda j: j["created_at"]))}


@router.get("/jobs/{job_id}")
def memtree_job_status(job_id: str):
    """记忆树任务进度：status/stage/进度计数；完成后带 result（成功/失败/失败题号）。"""
    job = MEMTREE_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在或已被清理")
    return memtree_job_view(job)
