# -*- coding: utf-8 -*-
"""Agent 基类：所有业务 Agent 继承此类。"""
from abc import ABC, abstractmethod
from typing import Any

from llm import LLMRouter

# 判定"成功"的总分阈值：总分 >= 该值记为一次成功（策略/助理共用）
SCORE_PASS_THRESHOLD = 60.0


def consecutive_success(records: list) -> int:
    """从最近一条往前数"不经补答成功"的连续次数。

    补答成功不算"不经补答"，失败/跳过/补答都会中断连续计数（策略排除规则与助理统计共用）。
    """
    consecutive = 0
    for r in reversed(records):
        if not r.skipped and not r.is_retry and r.score_total is not None and r.score_total >= SCORE_PASS_THRESHOLD:
            consecutive += 1
        else:
            break
    return consecutive


class BaseAgent(ABC):
    """Agent 抽象基类。

    - name：Agent 名称，用于"当前活跃 Agent"展示与日志
    - llm：共享的 LLM 路由器（多 Provider 按优先级自动切换）
    - run：Agent 的统一异步入口，参数与返回值由各子类按职责定义
    """

    name: str = "base"

    def __init__(self, llm_router: LLMRouter) -> None:
        self.llm = llm_router

    @abstractmethod
    async def run(self, *args: Any, **kwargs: Any) -> Any:
        """Agent 主入口（异步）。"""
        ...
