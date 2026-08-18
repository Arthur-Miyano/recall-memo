# -*- coding: utf-8 -*-
"""LLM 抽象基类：统一 chat 接口，所有 Provider 实现继承此类。"""
from abc import ABC, abstractmethod
from typing import Any

import httpx

from .usage import record_attempt, record_usage


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

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """发送对话请求，返回模型的文本回复。"""
        if not self.available:
            raise RuntimeError(f"Provider {self.name} 未配置 API Key，不可用")
        payload: dict[str, Any] = {"model": self.model, "messages": messages, **kwargs}
        try:
            resp = await self._get_client().post("/chat/completions", json=payload)
            resp.raise_for_status()
        except Exception:
            # 失败调用也记账：官网对失败请求同样计费（至少输入部分），按输入长度估算落库
            record_attempt(self.name, self.model, messages)
            raise
        data = resp.json()
        # token 用量落库（仪表盘"API 消耗"板块）；失败只记日志，不影响主流程
        record_usage(self.name, self.model, data.get("usage"))
        return self._extract_content(data)

    @abstractmethod
    def _extract_content(self, data: dict[str, Any]) -> str:
        """从响应 JSON 中取出文本内容（各 Provider 结构若有差异在此适配）。"""
        ...
