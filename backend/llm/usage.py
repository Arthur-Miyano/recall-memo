# -*- coding: utf-8 -*-
"""LLM 用量落库与计价。

用量在 BaseLLMClient.chat 拿到响应后写入（响应 JSON 的 usage 字段，
DeepSeek 会额外返回 prompt_cache_hit/miss_tokens，缓存命中价低 30 倍，必须分开记）。

花费不写库，在查询时按本模块单价表实时折算——单价调整后历史数据自动按新价重估。

调研结论（2026-08，官方定价页）：
- DeepSeek 分高峰/空闲时段计价：高峰 = 北京时间 9:00-12:00、14:00-18:00，
  空闲时段价格为高峰的一半；输入还分缓存命中/未命中两档。
  https://api-docs.deepseek.com/zh-cn/quick_start/pricing
- Kimi（月之暗面）：消费端会员/套餐与开放平台 API 是两套账户两条计费；
  套餐内额度无法按 token 折算单价 → 只记 token 用量，不估算花费。
"""
import logging
from datetime import datetime
from typing import Any, Optional

from timeutil import as_local

logger = logging.getLogger(__name__)

# DeepSeek 单价表：元 / 1M tokens（手工维护，价格调整改这里即可）
# peak = 高峰（北京时间 9:00-12:00、14:00-18:00），off = 空闲（半价）
# hit = 输入缓存命中，miss = 输入缓存未命中，output = 输出
_DEEPSEEK_V4_FLASH = {
    "peak": {"hit": 0.10, "miss": 3.0, "output": 9.0},
    "off": {"hit": 0.05, "miss": 1.5, "output": 4.5},
}
PRICE_PER_1M: dict[str, dict[str, dict[str, float]]] = {
    # deepseek-chat 当前指向 deepseek-v4-flash
    "deepseek-chat": _DEEPSEEK_V4_FLASH,
    "deepseek-v4-flash": _DEEPSEEK_V4_FLASH,
    "deepseek-v4-pro": {
        "peak": {"hit": 0.30, "miss": 9.0, "output": 27.0},
        "off": {"hit": 0.15, "miss": 4.5, "output": 13.5},
    },
}
# 未收录模型按 v4-flash 价估（当前主用模型）
DEFAULT_PRICE = _DEEPSEEK_V4_FLASH

# 套餐/会员额度的 Provider：额度无法按 token 折算单价，只记用量不计价
UNPRICED_PROVIDERS = {"kimi"}

# 高峰时段（北京时间/本地时区的小时）：9-12 点、14-18 点
_PEAK_HOURS = {9, 10, 11, 14, 15, 16, 17}


def is_peak(at: datetime) -> bool:
    """调用时间是否落在 DeepSeek 高峰时段（本地时区口径，与北京时间一致）。"""
    return as_local(at).hour in _PEAK_HOURS


def estimate_cost(
    provider: str,
    model: str,
    cache_hit_tokens: int,
    cache_miss_tokens: int,
    completion_tokens: int,
    at: datetime,
) -> Optional[float]:
    """按单价表折算单次调用花费（元）。

    返回 None 表示该 Provider 为套餐/会员额度（如 Kimi），不按量计价。
    """
    if provider in UNPRICED_PROVIDERS:
        return None
    price = PRICE_PER_1M.get(model, DEFAULT_PRICE)
    tier = price["peak" if is_peak(at) else "off"]
    return (
        cache_hit_tokens * tier["hit"]
        + cache_miss_tokens * tier["miss"]
        + completion_tokens * tier["output"]
    ) / 1_000_000


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
        # DeepSeek 缓存分档：响应带 prompt_cache_hit/miss_tokens；缺省时全部按未命中估（上限口径）
        cache_hit = int(usage.get("prompt_cache_hit_tokens") or 0)
        cache_miss = int(usage.get("prompt_cache_miss_tokens") or (prompt - cache_hit))
        # 延迟导入：避免 llm 包与 database 模块的循环依赖
        from database import engine
        from models import LLMUsage
        from sqlmodel import Session as DBSession

        with DBSession(engine) as session:
            session.add(LLMUsage(
                provider=provider, model=model,
                prompt_tokens=prompt, completion_tokens=completion, total_tokens=total,
                cache_hit_tokens=cache_hit, cache_miss_tokens=cache_miss,
            ))
            session.commit()
    except Exception:
        logger.warning("LLM 用量落库失败（不影响主流程）", exc_info=True)


def record_attempt(provider: str, model: str, messages: list[dict[str, Any]]) -> None:
    """失败调用也落库：API 报错拿不到 usage，按输入字符数估算 prompt tokens。

    估算口径：中英混合约 1 token ≈ 1.5 字符（cache 全部按未命中，上限口径）。
    官网对失败请求同样计费（至少输入部分），故计入用量与花费，保证账面完整。
    用量统计绝不影响主流程：任何异常只记日志。
    """
    try:
        chars = sum(len(str(m.get("content") or "")) for m in messages)
        est = max(1, chars * 2 // 3)
        # 延迟导入：避免 llm 包与 database 模块的循环依赖
        from database import engine
        from models import LLMUsage
        from sqlmodel import Session as DBSession

        with DBSession(engine) as session:
            session.add(LLMUsage(
                provider=provider, model=model,
                prompt_tokens=est, completion_tokens=0, total_tokens=est,
                cache_hit_tokens=0, cache_miss_tokens=est,
                status="error", estimated=True,
            ))
            session.commit()
    except Exception:
        logger.warning("LLM 失败调用落库失败（不影响主流程）", exc_info=True)
