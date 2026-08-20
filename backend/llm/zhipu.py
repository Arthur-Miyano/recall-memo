# -*- coding: utf-8 -*-
"""智谱（bigmodel.cn）Provider（OpenAI 兼容接口）。

端点与默认模型以官方文档为准（2026-08 核实）：
- base_url：https://open.bigmodel.cn/api/paas/v4
  https://docs.bigmodel.cn/cn/guide/develop/openai/introduction
- 默认模型 glm-4.7-flash：免费轻量款（GLM-4.5-Flash 已公告即将下线）
  https://docs.bigmodel.cn/cn/guide/models/free/glm-4.7-flash
"""
from typing import Any

from .base import BaseLLMClient


class ZhipuClient(BaseLLMClient):
    name = "zhipu"
    base_url = "https://open.bigmodel.cn/api/paas/v4"
    model = "glm-4.7-flash"

    def _extract_content(self, data: dict[str, Any]) -> str:
        return data["choices"][0]["message"]["content"]
