# -*- coding: utf-8 -*-
"""会话接口：驱动记忆训练模式完整闭环（JSON 交互）。"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session as DBSession

from agents import StateError, orchestrator
from agents.orchestrator import get_session_info
from database import engine

router = APIRouter(prefix="/sessions", tags=["sessions"])


def get_db():
    """每个请求一个 SQLModel Session（单 worker + SQLite，随请求关闭）。"""
    with DBSession(engine) as db:
        yield db


class CreateSessionRequest(BaseModel):
    mode: str = "memorize"  # 本阶段仅支持 memorize，其余模式预留
    stack: Optional[str] = None  # 技术栈筛选：python / agent / vue3 / mixed
    count: Literal[3, 5, 7] = 3


class AnswerRequest(BaseModel):
    answer: str


def _handle_state_error(exc: StateError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


@router.post("")
async def create_session(req: CreateSessionRequest, db: DBSession = Depends(get_db)):
    """开始会话：抽题，进入 MEMORIZE_SHOW，返回题目列表（含标准答案，供记忆）。"""
    try:
        return await orchestrator.run(
            "create_session", db=db, mode=req.mode, tech_stack=req.stack, count=req.count
        )
    except StateError as exc:
        raise _handle_state_error(exc) from exc


@router.post("/{session_id}/start_quiz")
async def start_quiz(session_id: int, db: DBSession = Depends(get_db)):
    """开始考核：打乱顺序，进入 MEMORIZE_QUIZ，返回第一题变体题干（不含答案）。"""
    try:
        return await orchestrator.run("start_quiz", db=db, session_id=session_id)
    except StateError as exc:
        raise _handle_state_error(exc) from exc


@router.get("/{session_id}/current")
async def current_question(session_id: int, db: DBSession = Depends(get_db)):
    """当前题：变体题干 + 关键词提示，不含答案。"""
    try:
        return await orchestrator.run("current", db=db, session_id=session_id)
    except StateError as exc:
        raise _handle_state_error(exc) from exc


@router.post("/{session_id}/answer")
async def submit_answer(session_id: int, req: AnswerRequest, db: DBSession = Depends(get_db)):
    """提交回答：评分+写库并行，返回结构化评分与标准答案对照，推进到下一题。"""
    try:
        return await orchestrator.run("answer", db=db, session_id=session_id, answer=req.answer)
    except StateError as exc:
        raise _handle_state_error(exc) from exc


@router.get("/{session_id}")
async def session_info(session_id: int, db: DBSession = Depends(get_db)):
    """会话状态（含当前状态机状态与活跃 Agent 名）。"""
    try:
        return get_session_info(db, session_id)
    except StateError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
