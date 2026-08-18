# -*- coding: utf-8 -*-
"""LLM 用量落库与计价。

用量在 BaseLLMClient.chat 拿到响应后写入（响应 JSON 的 usage 字段）；
花费不写库，在查询时按本模块单价表实时折算——单价调整后历史数据自动按新价重估。
"""
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 单价表：元 / 1M tokens（手工维护，价格调整改这里即可）
# DeepSeek-V3.2：缓存命中价更低（输入 ¥0.2/1M），这里按缓存未命中价估，属上限估计
PRICE_PER_1M: dict[str, dict[str, float]] = {
    "deepseek-chat": {"input": 2.0, "output": 3.0},
    "moonshot-v1-8k": {"input": 12.0, "output": 12.0},
    "moonshot-v1-32k": {"input": 24.0, "output": 24.0},
    "kimi-k2-0905-preview": {"input": 4.0, "output": 16.0},
}
# 未收录模型按 DeepSeek 价估（当前主用模型）
DEFAULT_PRICE = {"input": 2.0, "output": 3.0}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """按单价表折算单次调用花费（元）。"""
    price = PRICE_PER_1M.get(model, DEFAULT_PRICE)
    return (prompt_tokens * price["input"] + completion_tokens * price["output"]) / 1_000_000


def record_usage(provider: str, model: str, usage: Optional[dict[str, Any]]) -> None:
    """把一次调用的 usage 落库。用量统计绝不影响主流程：任何异常只记日志。"""
    if not usage:
        return
    try:
        prompt = int(usage.get("prompt_tokens") or 0)
        completion = int(usage.get("completion_tokens") or 0)
        total = int(usage.get("total_tokens") or (prompt + completion))
        if not (prompt or completion or total):
            return
        # 延迟导入：避免 llm 包与 database 模块的循环依赖
        from database import engine
        from models import LLMUsage
        from sqlmodel import Session as DBSession

        with DBSession(engine) as session:
            session.add(LLMUsage(
                provider=provider, model=model,
                prompt_tokens=prompt, completion_tokens=completion, total_tokens=total,
            ))
            session.commit()
    except Exception:
        logger.warning("LLM 用量落库失败（不影响主流程）", exc_info=True)
