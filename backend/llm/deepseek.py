# -*- coding: utf-8 -*-
"""DeepSeek Provider（OpenAI 兼容接口）。"""
from typing import Any

from .base import BaseLLMClient


class DeepSeekClient(BaseLLMClient):
    name = "deepseek"
    base_url = "https://api.deepseek.com"
    model = "deepseek-v4-flash"

    def _extract_content(self, data: dict[str, Any]) -> str:
        return data["choices"][0]["message"]["content"]
