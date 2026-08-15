# -*- coding: utf-8 -*-
"""时区/日期口径公共 helper。

约定：数据库一律存 UTC 时间戳（见各 models 的 _utcnow），
凡涉及"用户视角的今天 / 日期归属"（daily_stats 聚合、统计分组、到期判断等），
统一经本模块转换为本地时区口径，避免 UTC+8 的 0:00~8:00 数据归错天。
本地时区取系统时区（datetime.now().astimezone()），简单可靠。
"""
from datetime import date, datetime, time, timedelta, timezone


def local_now() -> datetime:
    """当前本地时间（aware，时区为系统本地时区）。"""
    return datetime.now().astimezone()


def local_today() -> date:
    """用户视角的"今天"（本地时区日期）。"""
    return local_now().date()


def as_local(dt: datetime) -> datetime:
    """UTC 时间戳转本地时间；naive 一律按 UTC 处理（SQLite 读出会丢时区）。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone()


def local_day_start_utc(day: date) -> datetime:
    """本地某天 0 点对应的 UTC 时间（aware），用于与库中 UTC 时间戳做比较。"""
    local_midnight = datetime.combine(day, time.min, tzinfo=local_now().tzinfo)
    return local_midnight.astimezone(timezone.utc)


def days_ago_local(days: int) -> date:
    """本地今天往前数 days 天的日期（统计窗口起点常用）。"""
    return local_today() - timedelta(days=days)
