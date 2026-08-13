# -*- coding: utf-8 -*-
"""LLM 抽象基类：统一 chat 接口，所有 Provider 实现继承此类。"""
from abc import ABC, abstractmethod
from typing import Any

import httpx


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

    @property
    def available(self) -> bool:
        """是否可用：配置了 api key 才可用。"""
        return bool(self.api_key)

    async def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """发送对话请求，返回模型的文本回复。"""
        if not self.available:
            raise RuntimeError(f"Provider {self.name} 未配置 API Key，不可用")
        payload: dict[str, Any] = {"model": self.model, "messages": messages, **kwargs}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        return self._extract_content(data)

    @abstractmethod
    def _extract_content(self, data: dict[str, Any]) -> str:
        """从响应 JSON 中取出文本内容（各 Provider 结构若有差异在此适配）。"""
        ...
