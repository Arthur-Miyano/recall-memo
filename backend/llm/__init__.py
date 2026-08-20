# -*- coding: utf-8 -*-
"""LLM 统一封装层：抽象基类 + 各 Provider 实现 + 优先级路由。"""
from .base import BaseLLMClient
from .deepseek import DeepSeekClient
from .kimi import KimiClient
from .zhipu import ZhipuClient
from .doubao import DoubaoClient
from .router import LLMRouter, llm_router

__all__ = [
    "BaseLLMClient", "DeepSeekClient", "KimiClient", "ZhipuClient", "DoubaoClient",
    "LLMRouter", "llm_router",
]
