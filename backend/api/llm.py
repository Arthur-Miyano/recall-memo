# -*- coding: utf-8 -*-
"""LLM 测试接口：验证多 Provider 封装层可用。"""
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from llm import llm_router

router = APIRouter(prefix="/llm", tags=["llm"])


class LLMTestRequest(BaseModel):
    prompt: str
    provider: Optional[str] = None  # 为空则按优先级路由，指定则强制使用


class LLMTestResponse(BaseModel):
    provider: str
    content: str


@router.post("/test", response_model=LLMTestResponse)
async def llm_test(req: LLMTestRequest) -> LLMTestResponse:
    # LLM 错误由全局异常处理器返回稳定结构（main.py，§4.2）
    messages = [{"role": "user", "content": req.prompt}]
    provider, content = await llm_router.chat(messages, provider=req.provider)
    return LLMTestResponse(provider=provider, content=content)
