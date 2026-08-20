# -*- coding: utf-8 -*-
"""豆包（火山方舟 Ark）Provider（OpenAI 兼容接口）。

端点与模型名规则以官方文档为准（2026-08 核实）：
- base_url：https://ark.cn-beijing.volces.com/api/v3
  https://www.volcengine.com/docs/82379/1298459
- model 字段两种写法均可：
  1. 推理接入点 ID（ep-xxxxxxxx，历史沿用方式）：控制台「在线推理」创建接入点后获得，
     调用时 model 直接填这个 ep- 开头的 ID；
  2. 模型 ID（如 doubao-seed-2-0-mini-260428）：开通模型后可不建接入点直接当 model 用。
- 默认模型取当前便宜轻量款 doubao-seed-2-0-mini-260428
  （doubao-seed-1-6-flash 系 2026-09-21 下线，官方建议迁移到此；
   https://www.volcengine.com/docs/82379/1350667）
"""
from typing import Any

from .base import BaseLLMClient


class DoubaoClient(BaseLLMClient):
    name = "doubao"
    base_url = "https://ark.cn-beijing.volces.com/api/v3"
    model = "doubao-seed-2-0-mini-260428"

    def _extract_content(self, data: dict[str, Any]) -> str:
        return data["choices"][0]["message"]["content"]
