# -*- coding: utf-8 -*-
"""timeutil 覆盖：local_today / as_local（naive 按 UTC 处理）/ local_day_start_utc 边界 / days_ago_local。

日期边界断言不硬编码 UTC+8，而是按本机时区动态换算，保证任何时区下都可重复。
"""
from datetime import date, datetime, time, timedelta, timezone

from timeutil import as_local, days_ago_local, local_day_start_utc, local_now, local_today


def test_local_today_matches_system_local_date():
    """local_today 应与系统本地时区的当前日期一致。"""
    assert local_today() == datetime.now().astimezone().date()


def test_local_now_is_aware():
    now = local_now()
    assert now.tzinfo is not None, "local_now 必须返回带时区的时间"


def test_as_local_naive_treated_as_utc():
    """naive 时间按 UTC 处理：与显式 UTC aware 转换结果一致。"""
    naive = datetime(2024, 1, 1, 16, 0, 0)
    aware = naive.replace(tzinfo=timezone.utc)
    assert as_local(naive) == as_local(aware)
    assert as_local(naive).tzinfo is not None


def test_as_local_utc_to_local_conversion():
    """UTC 2024-01-01 16:00 转本地：本地时间 = UTC + 本机偏移。"""
    utc_dt = datetime(2024, 1, 1, 16, 0, 0, tzinfo=timezone.utc)
    local_dt = as_local(utc_dt)
    offset = local_dt.utcoffset()
    assert local_dt.replace(tzinfo=None) == datetime(2024, 1, 1, 16, 0, 0) + offset


def test_as_local_utc8_boundary_changes_date():
    """若本机为 UTC+8：UTC 前一日 16:00 整 应落入本地当天 0 点（跨日边界）。"""
    if local_now().utcoffset() != timedelta(hours=8):
        import pytest

        pytest.skip("本机不是 UTC+8，跳过 +8 专属边界断言")
    utc_dt = datetime(2024, 3, 1, 16, 0, 0, tzinfo=timezone.utc)
    assert as_local(utc_dt).date() == date(2024, 3, 2)
    # 差一分钟仍未跨日
    before = datetime(2024, 3, 1, 15, 59, 59, tzinfo=timezone.utc)
    assert as_local(before).date() == date(2024, 3, 1)


def test_local_day_start_utc_boundary():
    """本地某天 0 点对应的 UTC 时间：动态换算 + UTC+8 下为前一日 16:00。"""
    day = date(2024, 3, 2)
    start_utc = local_day_start_utc(day)

    # 动态口径：本地 0 点转 UTC
    local_midnight = datetime.combine(day, time.min).astimezone()
    assert start_utc == local_midnight.astimezone(timezone.utc)
    assert start_utc.tzinfo == timezone.utc

    # 本地 0 点转回本地日期必须仍是当天
    assert start_utc.astimezone().date() == day

    if local_now().utcoffset() == timedelta(hours=8):
        assert start_utc == datetime(2024, 3, 1, 16, 0, 0, tzinfo=timezone.utc), (
            "UTC+8 环境下本地 0 点应对应前一日 16:00 UTC"
        )


def test_local_day_start_utc_comparison_semantics():
    """窗口语义：当天本地 0:00 之后产生的 UTC 记录 >= local_day_start_utc（用于近 N 天过滤）。"""
    today = local_today()
    start = local_day_start_utc(today)
    now_utc = datetime.now(timezone.utc)
    assert now_utc >= start, "当前时刻必须落在今天窗口内"
    # 昨天 0 点窗口起点必须早于今天窗口起点
    assert local_day_start_utc(today - timedelta(days=1)) < start


def test_days_ago_local():
    assert days_ago_local(0) == local_today()
    assert days_ago_local(6) == local_today() - timedelta(days=6)
