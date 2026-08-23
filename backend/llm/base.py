# -*- coding: utf-8 -*-
"""LLM 抽象基类：统一 chat 接口，所有 Provider 实现继承此类。"""
import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx

from .errors import (
    LLMAuthenticationError,
    LLMError,
    LLMRateLimitError,
    LLMRequestError,
    LLMTemporaryError,
    LLMTimeoutError,
)
from .usage import record_attempt, record_usage

logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    """LLM Provider 抽象基类（OpenAI 兼容的 /chat/completions 协议）。"""

    #: Provider 名称（路由与日志用）
    name: str = "base"
    #: API base_url
    base_url: str = ""
    #: 默认模型
    model: str = ""

    def __init__(self, api_key: str, timeout: float = 60.0) -> None:
        self.api_key = api_key
        self.timeout = timeout
        # 惰性单例 AsyncClient：首次请求时创建，之后复用（见 _get_client）
        self._client: httpx.AsyncClient | None = None

    @property
    def available(self) -> bool:
        """是否可用：配置了 api key 才可用。"""
        return bool(self.api_key)

    def _get_client(self) -> httpx.AsyncClient:
        """惰性单例 AsyncClient：进程生命周期内复用，避免每次请求新建 TCP/TLS 连接。

        超时与鉴权头固定在客户端上；Provider 实例随 LLMRouter.reload() 重建时
        旧客户端随之废弃（旧连接由 httpx GC 兜底关闭，reload 是低频操作，可接受）。
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
        return self._client

    def _classify_error(self, exc: Exception) -> Exception:
        """把底层 httpx/SDK 异常映射为统一分类（修复方案 §4.1）。

        映射规则：超时→LLMTimeoutError；401/403→认证；429→限流；
        400/404/422→请求错误（不切换）；5xx/网络故障→临时错误。
        异常消息只含 Provider 名与状态码，不含 URL/请求头/响应原文。
        """
        if isinstance(exc, LLMError):
            return exc
        if isinstance(exc, httpx.TimeoutException):
            return LLMTimeoutError(f"Provider {self.name} 请求超时（{self.timeout:.0f}s）")
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            # 脱敏日志：只记 Provider 名与状态码；响应原文随 __cause__ 链留在 exc_info 里
            logger.warning("Provider %s 返回 HTTP %s", self.name, status, exc_info=True)
            if status in (401, 403):
                return LLMAuthenticationError(f"Provider {self.name} API Key 认证失败（HTTP {status}）")
            if status == 429:
                return LLMRateLimitError(f"Provider {self.name} 触发限流（HTTP 429）")
            if status in (400, 404, 422):
                return LLMRequestError(f"Provider {self.name} 请求被拒绝（HTTP {status}），请检查模型名与参数")
            if 500 <= status < 600:
                return LLMTemporaryError(f"Provider {self.name} 服务暂时故障（HTTP {status}）")
            return LLMRequestError(f"Provider {self.name} 请求失败（HTTP {status}）")
        if isinstance(exc, httpx.TransportError):
            logger.warning("Provider %s 网络连接失败", self.name, exc_info=True)
            return LLMTemporaryError(f"Provider {self.name} 网络连接失败")
        logger.exception("Provider %s 调用出现未预期异常", self.name)
        return exc

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """发送对话请求，返回模型的文本回复。失败抛统一分类的 LLMError。"""
        if not self.available:
            raise LLMAuthenticationError(f"Provider {self.name} 未配置 API Key，不可用")
        payload: dict[str, Any] = {"model": self.model, "messages": messages, **kwargs}
        try:
            resp = await self._get_client().post("/chat/completions", json=payload)
            resp.raise_for_status()
        except Exception as exc:
            # 失败调用也记账：官网对失败请求同样计费（至少输入部分），按输入长度估算落库
            record_attempt(self.name, self.model, messages)
            classified = self._classify_error(exc)
            if classified is exc:
                raise
            raise classified from exc
        try:
            data = resp.json()
            content = self._extract_content(data)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            # 2xx 但响应结构无法识别：按临时故障处理（计费口径同失败请求）
            record_attempt(self.name, self.model, messages)
            logger.warning("Provider %s 返回了无法识别的响应结构", self.name, exc_info=True)
            raise LLMTemporaryError(f"Provider {self.name} 返回了无法识别的响应结构") from exc
        # token 用量落库（仪表盘"API 消耗"板块）；失败只记日志，不影响主流程
        record_usage(self.name, self.model, data.get("usage"))
        return content

    @abstractmethod
    def _extract_content(self, data: dict[str, Any]) -> str:
        """从响应 JSON 中取出文本内容（各 Provider 结构若有差异在此适配）。"""
        ...
