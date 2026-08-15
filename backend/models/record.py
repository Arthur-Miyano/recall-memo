# -*- coding: utf-8 -*-
"""答题记录与每日统计模型。"""
from datetime import date as date_type
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Record(SQLModel, table=True):
    """答题记录表：一次回答的原文、各维度得分与总分。"""

    __tablename__ = "records"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(index=True, description="所属会话 id")
    question_id: int = Field(index=True, description="题目 id")
    user_answer: str = Field(default="", description="用户回答原文")
    # 评分 Agent 输出的各维度得分（0~100），见文档 2.4
    score_accuracy: Optional[float] = Field(default=None, description="内容准确性得分")
    score_logic: Optional[float] = Field(default=None, description="逻辑清晰度得分")
    score_naturalness: Optional[float] = Field(default=None, description="表达自然度得分")
    score_total: Optional[float] = Field(default=None, description="总分")
    is_reciting: Optional[bool] = Field(default=None, description="是否判定为背诵（反背诵检测）")
    # 评分 Agent 输出的标注版标准答案（[[omiss]]/[[logic]] 标记，可空）；旧库由 init_db 迁移补列
    annotated_answer: Optional[str] = Field(default=None, description="标注版标准答案（遗漏/逻辑标记）")
    need_followup: bool = Field(default=False, description="是否需要补答/追问")
    # 面试模式：跳过的题记为失败（总分 0），但不给补答机会
    skipped: bool = Field(default=False, description="是否被跳过（判负，不可补答）")
    # 补答记录：原记录保留不覆盖，补答写为新记录并标记
    is_retry: bool = Field(default=False, description="是否补答记录")
    retry_of: Optional[int] = Field(default=None, description="补答对应的原记录 id")
    created_at: datetime = Field(default_factory=_utcnow, description="答题时间戳")


class DailyStat(SQLModel, table=True):
    """每日聚合统计表：题数、成功数、失败数。"""

    __tablename__ = "daily_stats"

    id: Optional[int] = Field(default=None, primary_key=True)
    date: date_type = Field(unique=True, index=True, description="统计日期")
    total_count: int = Field(default=0, description="当日答题总数")
    success_count: int = Field(default=0, description="当日成功数")
    fail_count: int = Field(default=0, description="当日失败数")
