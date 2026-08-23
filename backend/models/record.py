# -*- coding: utf-8 -*-
"""答题记录与每日统计模型。"""
from datetime import date as date_type
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# 分数范围约束（§6.3）：NULL（未评分）或 0~100
_SCORE_CHECKS = tuple(
    CheckConstraint(f"{col} IS NULL OR ({col} >= 0 AND {col} <= 100)", name=f"ck_records_{col}")
    for col in ("score_accuracy", "score_logic", "score_naturalness", "score_total")
)


class Record(SQLModel, table=True):
    """答题记录表：一次回答的原文、各维度得分与总分。"""

    __tablename__ = "records"
    # 外键与分数范围约束只对新建库生效（既有库表结构不变，存量数据由
    # scripts/check_data_integrity.py 检查；§6.3 选不重建既有表的轻量方案）
    __table_args__ = _SCORE_CHECKS

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="sessions.id", index=True, description="所属会话 id")
    question_id: int = Field(foreign_key="questions.id", index=True, description="题目 id")
    user_answer: str = Field(default="", description="用户回答原文")
    # 评分 Agent 输出的各维度得分（0~100），见文档 2.4
    score_accuracy: Optional[float] = Field(default=None, description="内容准确性得分")
    score_logic: Optional[float] = Field(default=None, description="逻辑清晰度得分")
    score_naturalness: Optional[float] = Field(default=None, description="表达自然度得分")
    score_total: Optional[float] = Field(default=None, description="总分")
    is_reciting: Optional[bool] = Field(default=None, description="是否判定为背诵（反背诵检测）")
    # 评分 Agent 输出的标注版标准答案（[[omiss]]/[[logic]] 标记，可空）；旧库由版本迁移 v1 补列
    annotated_answer: Optional[str] = Field(default=None, description="标注版标准答案（遗漏/逻辑标记）")
    need_followup: bool = Field(default=False, description="是否需要补答/追问")
    # 面试模式：跳过的题记为失败（总分 0），但不给补答机会
    skipped: bool = Field(default=False, description="是否被跳过（判负，不可补答）")
    # 补答记录：原记录保留不覆盖，补答写为新记录并标记
    is_retry: bool = Field(default=False, description="是否补答记录")
    retry_of: Optional[int] = Field(default=None, foreign_key="records.id", description="补答对应的原记录 id")
    # 幂等写库：一条记录至多归属一个工作流操作（唯一约束，旧库由版本迁移 v6 补列+唯一索引）
    operation_id: Optional[int] = Field(
        default=None, unique=True, foreign_key="workflow_operations.id",
        description="来源工作流操作 id（一操作一记录）",
    )
    created_at: datetime = Field(default_factory=_utcnow, index=True, description="答题时间戳")


class DailyStat(SQLModel, table=True):
    """每日聚合统计表：题数、成功数、失败数。"""

    __tablename__ = "daily_stats"

    id: Optional[int] = Field(default=None, primary_key=True)
    date: date_type = Field(unique=True, index=True, description="统计日期")
    total_count: int = Field(default=0, description="当日答题总数")
    success_count: int = Field(default=0, description="当日成功数")
    fail_count: int = Field(default=0, description="当日失败数")
