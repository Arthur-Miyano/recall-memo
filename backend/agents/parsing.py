# -*- coding: utf-8 -*-
"""LLM 输出的 JSON 抠取公共实现（grader / assistant / importer 复用）。"""
import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def parse_json_object(content: str, log_label: Optional[str] = None) -> dict[str, Any]:
    """从模型输出中稳健地提取 JSON 对象（容忍代码块围栏与前后杂文本）。

    失败一律返回 {}；log_label 非空时记 warning 日志（评分 Agent 需要排查用，
    复盘分析等容错路径传 None 静默处理）。
    """
    text = _FENCE_RE.sub("", content.strip()).strip()
    match = _OBJECT_RE.search(text)
    if not match:
        if log_label:
            logger.warning("%s输出中未找到 JSON：%s", log_label, content[:200])
        return {}
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        if log_label:
            logger.warning("%sJSON 解析失败：%s", log_label, content[:200])
        return {}
    return data if isinstance(data, dict) else {}


def extract_json_array(raw: str) -> list[dict]:
    """从 LLM 回复里抠出 JSON 数组（容忍前后多余文字/代码块）。

    与 parse_json_object 的语义差异：找不到数组时抛 ValueError（导入流程据此走重试/降级），
    且不做代码块围栏剥离（题库导入的容错更宽，由调用方决定是否重试）。
    """
    match = _ARRAY_RE.search(raw.strip())
    if not match:
        raise ValueError("LLM 回复中不含 JSON 数组")
    data = json.loads(match.group(0))
    return [d for d in data if isinstance(d, dict)]
