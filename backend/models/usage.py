# -*- coding: utf-8 -*-
"""LLM 用量表：每次调用的 token 消耗落库，供仪表盘"API 消耗"板块聚合。"""
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LLMUsage(SQLModel, table=True):
    """单次 LLM 调用的 token 用量（OpenAI 兼容响应的 usage 字段原样落库）。"""

    __tablename__ = "llm_usage"

    id: Optional[int] = Field(default=None, primary_key=True)
    provider: str = Field(default="", description="Provider 名：deepseek / kimi")
    model: str = Field(default="", description="实际使用的模型名")
    prompt_tokens: int = Field(default=0, description="输入 tokens")
    completion_tokens: int = Field(default=0, description="输出 tokens")
    total_tokens: int = Field(default=0, description="总 tokens")
    cache_hit_tokens: int = Field(default=0, description="输入中缓存命中的 tokens（DeepSeek 缓存计价）")
    cache_miss_tokens: int = Field(default=0, description="输入中缓存未命中的 tokens")
    created_at: datetime = Field(default_factory=_utcnow, description="调用时间（UTC）")
