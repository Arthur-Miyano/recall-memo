# -*- coding: utf-8 -*-
"""LLM 统一封装层：抽象基类 + 各 Provider 实现 + 优先级路由 + 统一异常分类。"""
from .base import BaseLLMClient
from .deepseek import DeepSeekClient
from .kimi import KimiClient
from .zhipu import ZhipuClient
from .doubao import DoubaoClient
from .errors import (
    LLMAuthenticationError,
    LLMError,
    LLMOutputValidationError,
    LLMRateLimitError,
    LLMRequestError,
    LLMTemporaryError,
    LLMTimeoutError,
)
from .router import LLMProviderUnavailableError, LLMRouter, llm_router

__all__ = [
    "BaseLLMClient", "DeepSeekClient", "KimiClient", "ZhipuClient", "DoubaoClient",
    "LLMRouter", "llm_router",
    "LLMError", "LLMTimeoutError", "LLMRateLimitError", "LLMTemporaryError",
    "LLMAuthenticationError", "LLMRequestError", "LLMOutputValidationError",
    "LLMProviderUnavailableError",
]
