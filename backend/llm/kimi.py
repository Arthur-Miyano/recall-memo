# -*- coding: utf-8 -*-
"""Kimi（Moonshot）Provider（OpenAI 兼容接口）。"""
from typing import Any

from .base import BaseLLMClient


class KimiClient(BaseLLMClient):
    name = "kimi"
    base_url = "https://api.moonshot.cn/v1"
    model = "moonshot-v1-8k"

    def _extract_content(self, data: dict[str, Any]) -> str:
        return data["choices"][0]["message"]["content"]
