# -*- coding: utf-8 -*-
"""LLM 路由：按 LLM_PROVIDER_PRIORITY 顺序尝试可用 Provider，仅对可切换错误类型做故障切换。"""
import asyncio
import logging
from typing import Any, Optional, Type

from config import settings
from .base import BaseLLMClient
from .deepseek import DeepSeekClient
from .errors import LLMError, LLMRateLimitError, LLMTemporaryError, LLMTimeoutError
from .kimi import KimiClient
from .zhipu import ZhipuClient
from .doubao import DoubaoClient

logger = logging.getLogger(__name__)

# Provider 注册表：新增 Provider 时实现 BaseLLMClient 并在此注册即可
PROVIDER_REGISTRY: dict[str, Type[BaseLLMClient]] = {
    "deepseek": DeepSeekClient,
    "kimi": KimiClient,
    "zhipu": ZhipuClient,
    "doubao": DoubaoClient,
}

# 各 Provider 的 api key 从 settings 哪个字段读取
PROVIDER_KEY_ATTR: dict[str, str] = {
    "deepseek": "deepseek_api_key",
    "kimi": "kimi_api_key",
    "zhipu": "zhipu_api_key",
    "doubao": "doubao_api_key",
}

# 各 Provider 的 api key 对应的环境变量名（= settings 字段名大写）
PROVIDER_ENV_VAR: dict[str, str] = {name: attr.upper() for name, attr in PROVIDER_KEY_ATTR.items()}

# 允许故障切换/重试的错误类型（修复方案 §4.1）：
# 超时、限流、临时故障（网络/5xx）。认证与请求错误不切换——换 Provider 解决不了配置/参数问题
_SWITCHABLE_ERRORS = (LLMTimeoutError, LLMRateLimitError, LLMTemporaryError)

# 单 Provider 最多重试 1 次（即最多调用 2 次）
MAX_RETRY_PER_PROVIDER = 1

# 限流退避秒数（重试前等待）
RATE_LIMIT_BACKOFF = 1.0

# 统一截止时间：一次路由调用的总预算 = 单次超时 × 该系数（容纳单 Provider 重试或一次切换）
OVERALL_TIMEOUT_FACTOR = 2


class LLMProviderUnavailableError(LLMError):
    """所有 Provider 均不可用或全部调用失败。"""


class LLMRouter:
    """按优先级调度 Provider：仅超时/限流/临时故障自动切换，认证与请求错误直接上抛。"""

    def __init__(self) -> None:
        self._clients: dict[str, BaseLLMClient] = self._build_clients()

    @staticmethod
    def _build_clients() -> dict[str, BaseLLMClient]:
        """按当前 settings 实例化全部 Provider 客户端。

        llm_model 只覆盖优先级第一的默认 Provider：模型名是 Provider 私有的，
        一刀切覆盖会把 deepseek 的模型名原样发给 Kimi 导致 400。
        """
        clients: dict[str, BaseLLMClient] = {}
        priority = settings.provider_priority
        default_provider = priority[0] if priority else None
        for name, cls in PROVIDER_REGISTRY.items():
            api_key = getattr(settings, PROVIDER_KEY_ATTR.get(name, ""), "")
            client = cls(api_key=api_key, timeout=settings.llm_timeout)
            if settings.llm_model and name == default_provider:
                client.model = settings.llm_model
            clients[name] = client
        return clients

    def reload(self) -> None:
        """配置变更（设置面板写入 .env）后重建客户端，让新 Key/模型立即生效。"""
        self._clients = self._build_clients()

    def get_client(self, name: str) -> Optional[BaseLLMClient]:
        return self._clients.get(name)

    async def _call_with_retry(
        self,
        client: BaseLLMClient,
        messages: list[dict[str, str]],
        deadline: float,
        **kwargs: Any,
    ) -> str:
        """单 Provider 调用：可切换错误最多重试 1 次（限流先退避），全程受统一截止时间约束。"""
        loop = asyncio.get_running_loop()
        for attempt in range(MAX_RETRY_PER_PROVIDER + 1):
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise LLMTimeoutError(f"Provider {client.name} 调用超出统一截止时间")
            try:
                # wait_for 把单次调用也钳制在剩余预算内，防止挂死的连接拖过截止时间
                return await asyncio.wait_for(client.chat(messages, **kwargs), timeout=remaining)
            except TimeoutError as exc:  # wait_for 自身超时（asyncio.TimeoutError 即 TimeoutError）
                exc = LLMTimeoutError(f"Provider {client.name} 调用超出统一截止时间")
                if attempt >= MAX_RETRY_PER_PROVIDER:
                    raise exc
                logger.warning("Provider %s 调用超时，重试第 %s 次", client.name, attempt + 1)
            except _SWITCHABLE_ERRORS as exc:
                if attempt >= MAX_RETRY_PER_PROVIDER:
                    raise
                if isinstance(exc, LLMRateLimitError):
                    await asyncio.sleep(RATE_LIMIT_BACKOFF)  # 限流：退避后再重试
                logger.warning(
                    "Provider %s 调用失败（%s），重试第 %s 次",
                    client.name, type(exc).__name__, attempt + 1,
                )
        raise LLMTimeoutError(f"Provider {client.name} 调用超出统一截止时间")  # pragma: no cover

    async def chat(
        self,
        messages: list[dict[str, str]],
        provider: Optional[str] = None,
        **kwargs: Any,
    ) -> tuple[str, str]:
        """调用 LLM，返回 (实际使用的 provider 名称, 模型回复文本)。

        provider 为 None 时按 LLM_PROVIDER_PRIORITY 顺序尝试；
        指定 provider 时强制使用该 Provider（不可用或失败直接抛错）。
        只对可切换错误（超时/限流/临时故障）做故障切换；认证与请求错误直接上抛。
        """
        deadline = asyncio.get_running_loop().time() + settings.llm_timeout * OVERALL_TIMEOUT_FACTOR
        if provider:
            client = self._clients.get(provider)
            if client is None:
                raise LLMProviderUnavailableError(f"未注册的 Provider：{provider}")
            if not client.available:
                raise LLMProviderUnavailableError(f"Provider {provider} 未配置 API Key，不可用")
            content = await self._call_with_retry(client, messages, deadline, **kwargs)
            return provider, content

        errors: list[str] = []
        tried = False
        for name in settings.provider_priority:
            client = self._clients.get(name)
            if client is None or not client.available:
                continue
            tried = True
            try:
                content = await self._call_with_retry(client, messages, deadline, **kwargs)
                return name, content
            except _SWITCHABLE_ERRORS as exc:
                # 日志只记错误类型名，不含 Provider 原始异常文本（脱敏）
                logger.warning("Provider %s 调用失败（%s），切换到下一个", name, type(exc).__name__)
                errors.append(f"{name}: {type(exc).__name__}")

        if not tried:
            raise LLMProviderUnavailableError("没有任何已配置 API Key 的 Provider 可用")
        raise LLMProviderUnavailableError("所有可用 Provider 均调用失败（" + "、".join(errors) + "）")


# 全局单例
llm_router = LLMRouter()
