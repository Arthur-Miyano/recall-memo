# -*- coding: utf-8 -*-
"""LLM 路由：按 LLM_PROVIDER_PRIORITY 顺序尝试可用 Provider，失败自动切换下一个。"""
import logging
from typing import Any, Optional, Type

from config import settings
from .base import BaseLLMClient
from .deepseek import DeepSeekClient
from .kimi import KimiClient

logger = logging.getLogger(__name__)

# Provider 注册表：新增 Provider（如 Zhipu/Doubao）时实现 BaseLLMClient 并在此注册即可
PROVIDER_REGISTRY: dict[str, Type[BaseLLMClient]] = {
    "deepseek": DeepSeekClient,
    "kimi": KimiClient,
}

# 各 Provider 的 api key 从 settings 哪个字段读取
PROVIDER_KEY_ATTR: dict[str, str] = {
    "deepseek": "deepseek_api_key",
    "kimi": "kimi_api_key",
}


class LLMProviderUnavailableError(RuntimeError):
    """所有 Provider 均不可用或全部调用失败。"""


class LLMRouter:
    """按优先级调度 Provider：超时/限流/报错自动切换下一个。"""

    def __init__(self) -> None:
        self._clients: dict[str, BaseLLMClient] = {}
        for name, cls in PROVIDER_REGISTRY.items():
            api_key = getattr(settings, PROVIDER_KEY_ATTR.get(name, ""), "")
            self._clients[name] = cls(api_key=api_key, timeout=settings.llm_timeout)

    def get_client(self, name: str) -> Optional[BaseLLMClient]:
        return self._clients.get(name)

    async def chat(
        self,
        messages: list[dict[str, str]],
        provider: Optional[str] = None,
        **kwargs: Any,
    ) -> tuple[str, str]:
        """调用 LLM，返回 (实际使用的 provider 名称, 模型回复文本)。

        provider 为 None 时按 LLM_PROVIDER_PRIORITY 顺序尝试；
        指定 provider 时强制使用该 Provider（不可用或失败直接抛错）。
        """
        if provider:
            client = self._clients.get(provider)
            if client is None:
                raise LLMProviderUnavailableError(f"未注册的 Provider：{provider}")
            if not client.available:
                raise LLMProviderUnavailableError(f"Provider {provider} 未配置 API Key，不可用")
            content = await client.chat(messages, **kwargs)
            return provider, content

        errors: list[str] = []
        tried = False
        for name in settings.provider_priority:
            client = self._clients.get(name)
            if client is None or not client.available:
                continue
            tried = True
            try:
                content = await client.chat(messages, **kwargs)
                return name, content
            except Exception as exc:  # 超时/限流/报错均切换到下一个
                logger.warning("Provider %s 调用失败，切换到下一个：%s", name, exc)
                errors.append(f"{name}: {exc}")

        if not tried:
            raise LLMProviderUnavailableError("没有任何已配置 API Key 的 Provider 可用")
        raise LLMProviderUnavailableError("所有 Provider 调用均失败：" + "; ".join(errors))


# 全局单例
llm_router = LLMRouter()
