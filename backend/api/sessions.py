# -*- coding: utf-8 -*-
"""会话接口：驱动记忆训练 / 面试模拟 / 回忆三种模式的完整闭环（JSON 交互）。"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session as DBSession, select

from agents import StateError, orchestrator
from agents.orchestrator import get_session_info
from api.deps import get_db
from models import Question, RetryQueueItem, Session

router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    mode: str = "memorize"  # memorize（记忆训练）/ interview（面试模拟）/ review（回忆）
    stack: Optional[str] = None  # 技术栈筛选：python / agent / vue3 / mixed
    count: int = Field(default=3, ge=1, le=10)  # 各模式题量上限在总控按模式校验


class AnswerRequest(BaseModel):
    answer: str
    # 调用方标记的开始作答时间（面试模式时间压力：2 分钟内必须开始作答）
    started_at: Optional[datetime] = None


def _handle_state_error(exc: StateError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.post("")
async def create_session(req: CreateSessionRequest, db: DBSession = Depends(get_db)):
    """开始会话：按模式抽题。记忆/回忆模式返回题目列表（含答案）；面试模式直接返回第一题。"""
    try:
        return await orchestrator.run(
            "create_session", db=db, mode=req.mode, tech_stack=req.stack, count=req.count
        )
    except StateError as exc:
        raise _handle_state_error(exc) from exc


@router.post("/{session_id}/start_quiz")
async def start_quiz(session_id: int, db: DBSession = Depends(get_db)):
    """开始考核（记忆/回忆模式）：打乱顺序，返回第一题变体题干（不含答案）。"""
    try:
        return await orchestrator.run("start_quiz", db=db, session_id=session_id)
    except StateError as exc:
        raise _handle_state_error(exc) from exc


@router.get("/{session_id}/current")
async def current_question(session_id: int, db: DBSession = Depends(get_db)):
    """当前题：变体题干（考核模式含关键词提示；面试模式含追问标识与出题时间），不含答案。"""
    try:
        return await orchestrator.run("current", db=db, session_id=session_id)
    except StateError as exc:
        raise _handle_state_error(exc) from exc


@router.post("/{session_id}/answer")
async def submit_answer(session_id: int, req: AnswerRequest, db: DBSession = Depends(get_db)):
    """提交回答：考核模式即时返回评分；面试模式只回执"已记录"并推进下一题。"""
    try:
        return await orchestrator.run(
            "answer", db=db, session_id=session_id, answer=req.answer,
            started_at=req.started_at.isoformat() if req.started_at else None,
        )
    except StateError as exc:
        raise _handle_state_error(exc) from exc


@router.post("/{session_id}/skip")
async def skip_question(session_id: int, db: DBSession = Depends(get_db)):
    """面试跳过：标记为失败（总分 0），不消耗补答机会、不给补答，推进下一题。"""
    try:
        return await orchestrator.run("skip", db=db, session_id=session_id)
    except StateError as exc:
        raise _handle_state_error(exc) from exc


@router.get("/{session_id}/review")
async def review_report(session_id: int, db: DBSession = Depends(get_db)):
    """终局复盘报告：逐题对照、各维度得分、薄弱点分析、学习建议、错题去向（已入待补答队列）。"""
    try:
        return await orchestrator.run("review", db=db, session_id=session_id)
    except StateError as exc:
        raise _handle_state_error(exc) from exc


@router.get("/retry-queue")
def retry_queue(db: DBSession = Depends(get_db)):
    """待补答队列：面试/考核答错（或跳过）的题，在记忆训练中优先重背，答及格后出队。"""
    items = db.exec(select(RetryQueueItem).order_by(RetryQueueItem.created_at)).all()
    return {
        "count": len(items),
        "items": [
            {
                "question_id": item.question_id,
                "stem": (q.stem if q else ""),
                "tech_stack": (q.tech_stack if q else ""),
                "source": item.source,
                "created_at": item.created_at.isoformat(),
            }
            for item in items
            for q in [db.get(Question, item.question_id)]
        ],
    }


@router.get("/latest-review")
def latest_review(db: DBSession = Depends(get_db)):
    """最近一次已生成复盘报告的面试场次（复盘页无 session_id 时的入口）。"""
    session = db.exec(
        select(Session)
        .where(Session.state == "INTERVIEW_REVIEW")
        .order_by(Session.updated_at.desc())
    ).first()
    if session is None or not (session.context or {}).get("review_report"):
        raise HTTPException(status_code=404, detail="暂无复盘报告，请先完成一场面试模拟")
    return session.context["review_report"]


@router.post("/{session_id}/retry")
async def retry_question(session_id: int, db: DBSession = Depends(get_db)):
    """旧"复盘补答"端点已下线：答错的题自动进待补答队列，在记忆训练中重背。"""
    raise HTTPException(status_code=410, detail="补答已迁移到记忆训练：答错的题自动进入待补答队列，请在记忆训练中重背")


@router.get("/{session_id}")
async def session_info(session_id: int, db: DBSession = Depends(get_db)):
    """会话状态（含当前状态机状态与活跃 Agent 名）。"""
    try:
        return get_session_info(db, session_id)
    except StateError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
