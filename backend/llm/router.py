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

# 各 Provider 的 api key 对应的环境变量名（= settings 字段名大写）
PROVIDER_ENV_VAR: dict[str, str] = {name: attr.upper() for name, attr in PROVIDER_KEY_ATTR.items()}


class LLMProviderUnavailableError(RuntimeError):
    """所有 Provider 均不可用或全部调用失败。"""


class LLMRouter:
    """按优先级调度 Provider：超时/限流/报错自动切换下一个。"""

    def __init__(self) -> None:
        self._clients: dict[str, BaseLLMClient] = self._build_clients()

    @staticmethod
    def _build_clients() -> dict[str, BaseLLMClient]:
        """按当前 settings 实例化全部 Provider 客户端（llm_model 非空时覆盖默认模型名）。"""
        clients: dict[str, BaseLLMClient] = {}
        for name, cls in PROVIDER_REGISTRY.items():
            api_key = getattr(settings, PROVIDER_KEY_ATTR.get(name, ""), "")
            client = cls(api_key=api_key, timeout=settings.llm_timeout)
            if settings.llm_model:
                client.model = settings.llm_model
            clients[name] = client
        return clients

    def reload(self) -> None:
        """配置变更（设置面板写入 .env）后重建客户端，让新 Key/模型立即生效。"""
        self._clients = self._build_clients()

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
