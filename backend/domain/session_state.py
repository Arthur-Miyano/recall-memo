# -*- coding: utf-8 -*-
"""会话状态机与 mode 定义（修复方案 §6.1 的唯一权威来源）。

本模块不依赖 FastAPI、数据库与 Agent，Orchestrator、启动清理、API 与测试全部引用这里。
向后兼容：`from agents.orchestrator import SessionState` 等旧导入路径仍可用（orchestrator
从这里 re-export）。
"""
from enum import Enum


class SessionState(str, Enum):
    """会话状态机，见文档 3.3。"""

    IDLE = "IDLE"
    # 记忆训练模式
    MEMORIZE_SHOW = "MEMORIZE_SHOW"  # 展示题干+答案供记忆
    MEMORIZE_QUIZ = "MEMORIZE_QUIZ"  # 打乱顺序考核中
    # 面试模拟模式
    INTERVIEW_SELECT = "INTERVIEW_SELECT"  # 选技术栈/题量（抽题中）
    INTERVIEW_ASK = "INTERVIEW_ASK"  # 展示变体题干
    INTERVIEW_ANSWER = "INTERVIEW_ANSWER"  # 等待回答（2 分钟计时由前端做）
    INTERVIEW_SCORE = "INTERVIEW_SCORE"  # 评分中（评分+助理并行，不透露给用户）
    INTERVIEW_REVIEW = "INTERVIEW_REVIEW"  # 终局复盘
    # 回忆模式
    REVIEW_SHOW = "REVIEW_SHOW"  # 展示题干+答案供回忆
    REVIEW_QUIZ = "REVIEW_QUIZ"  # 打乱顺序考核中


# EXPIRED 是状态机不认识的终态标记：启动清理把昨天及更早的进行中会话置为该值，
# 之后任何操作自然抛 StateError（见 database.expire_stale_sessions）
EXPIRED_STATE = "EXPIRED"

# 会话终态：处于这些状态的会话不算"进行中"
TERMINAL_SESSION_STATES = frozenset({
    SessionState.IDLE.value, SessionState.INTERVIEW_REVIEW.value, EXPIRED_STATE,
})

# state 列的全部合法值（状态机 + EXPIRED 终态标记）
VALID_SESSION_STATES = tuple(s.value for s in SessionState) + (EXPIRED_STATE,)

# mode 列的合法值（review 为预留模式）
VALID_SESSION_MODES = ("memorize", "interview", "review")
