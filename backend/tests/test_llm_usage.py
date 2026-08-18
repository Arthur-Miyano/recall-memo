# -*- coding: utf-8 -*-
"""LLM 用量覆盖：record_usage 落库（含容错与缓存分档）+ estimate_cost 峰谷/缓存计价
+ Kimi 套餐额度不计价 + /stats/llm-usage 聚合。"""
from datetime import datetime, timedelta, timezone

from llm.usage import (
    DEFAULT_PRICE, PRICE_PER_1M, UNPRICED_PROVIDERS,
    estimate_cost, is_peak, record_usage,
)
from models import LLMUsage


class TestRecordUsage:
    def test_writes_row_with_cache_split(self, db):
        record_usage("deepseek", "deepseek-chat", {
            "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150,
            "prompt_cache_hit_tokens": 30, "prompt_cache_miss_tokens": 70,
        })
        row = db.query(LLMUsage).one()
        assert row.provider == "deepseek"
        assert row.cache_hit_tokens == 30
        assert row.cache_miss_tokens == 70

    def test_missing_cache_fields_fall_back_to_all_miss(self, db):
        """响应没带缓存分档时，输入全部按未命中记（上限口径）。"""
        record_usage("kimi", "kimi-k3", {"prompt_tokens": 100, "completion_tokens": 5})
        row = db.query(LLMUsage).one()
        assert row.cache_hit_tokens == 0
        assert row.cache_miss_tokens == 100

    def test_none_and_zero_usage_skipped(self, db):
        record_usage("deepseek", "deepseek-chat", None)
        record_usage("deepseek", "deepseek-chat", {})
        record_usage("deepseek", "deepseek-chat", {"prompt_tokens": 0, "completion_tokens": 0})
        assert db.query(LLMUsage).count() == 0


def _at(hour: int) -> datetime:
    """构造本地某小时的调用时间（naive 按本地时区理解，as_local 转回本地仍是该小时）。"""
    return datetime(2026, 8, 18, hour).astimezone()


class TestEstimateCost:
    def test_peak_hours(self):
        assert is_peak(_at(10)) is True    # 9-12 点
        assert is_peak(_at(15)) is True    # 14-18 点
        assert is_peak(_at(13)) is False   # 午休空闲
        assert is_peak(_at(2)) is False    # 凌晨空闲

    def test_deepseek_peak_vs_offpeak(self):
        # v4-flash 高峰：miss ¥3/1M + output ¥9/1M；空闲半价
        peak = estimate_cost("deepseek", "deepseek-chat", 0, 1_000_000, 1_000_000, _at(10))
        off = estimate_cost("deepseek", "deepseek-chat", 0, 1_000_000, 1_000_000, _at(2))
        assert peak == 12.0
        assert off == 6.0

    def test_cache_hit_is_cheaper(self):
        # 全部命中（高峰 ¥0.1/1M） vs 全部未命中（高峰 ¥3/1M），差 30 倍
        hit = estimate_cost("deepseek", "deepseek-chat", 1_000_000, 0, 0, _at(10))
        miss = estimate_cost("deepseek", "deepseek-chat", 0, 1_000_000, 0, _at(10))
        assert hit == 0.1
        assert miss == 3.0

    def test_kimi_unpriced(self):
        """Kimi 为套餐/会员额度：只记 token，花费返回 None。"""
        assert "kimi" in UNPRICED_PROVIDERS
        assert estimate_cost("kimi", "kimi-k3", 0, 1_000_000, 1_000_000, _at(10)) is None

    def test_unknown_model_falls_back_to_default(self):
        tier = DEFAULT_PRICE["off"]
        expected = (100 * tier["miss"] + 100 * tier["output"]) / 1_000_000
        assert estimate_cost("deepseek", "some-new-model", 0, 100, 100, _at(2)) == expected

    def test_price_table_covers_default_models(self):
        assert "deepseek-chat" in PRICE_PER_1M
        assert "deepseek-v4-pro" in PRICE_PER_1M


def _add_usage(db, model="deepseek-chat", provider="deepseek", days_ago=0,
               prompt=1000, completion=500, cache_hit=0, cache_miss=None, hour=3):
    """插入一条用量；hour 为 UTC 小时（默认 3 点 = 本地 11 点高峰外/内取决于时区，
    测试里只关心聚合数字，用固定值即可）。"""
    row = LLMUsage(
        provider=provider, model=model,
        prompt_tokens=prompt, completion_tokens=completion,
        total_tokens=prompt + completion,
        cache_hit_tokens=cache_hit,
        cache_miss_tokens=cache_miss if cache_miss is not None else prompt - cache_hit,
        created_at=datetime(2026, 8, 18, hour, tzinfo=timezone.utc) - timedelta(days=days_ago)
        if days_ago else datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    return row


class TestLlmUsageApi:
    def test_empty(self, client):
        data = client.get("/api/stats/llm-usage").json()
        assert data["totals"] == {"cost": 0.0, "requests": 0, "tokens": 0, "unpriced_requests": 0}
        assert len(data["daily"]) == 30
        assert all(d["requests"] == 0 for d in data["daily"])
        assert data["models"] == []

    def test_aggregation_with_unpriced_provider(self, client, db):
        now = datetime.now(timezone.utc)
        priced = estimate_cost("deepseek", "deepseek-chat", 0, 1_000_000, 0, now)
        assert priced is not None and priced > 0

        _add_usage(db, prompt=1_000_000, completion=0)                              # DeepSeek，计价
        _add_usage(db, model="kimi-k3", provider="kimi", prompt=500_000,
                   completion=100_000)                                              # Kimi，不计价
        _add_usage(db, days_ago=40, prompt=1_000_000, completion=0)                 # 40 天前（出窗口）

        data = client.get("/api/stats/llm-usage?days=30").json()
        # 总计：3 次全部计入 requests/tokens；cost 只含 DeepSeek 两次；Kimi 算未计价
        assert data["totals"]["requests"] == 3
        assert data["totals"]["unpriced_requests"] == 1
        assert data["totals"]["tokens"] == 1_000_000 + 600_000 + 1_000_000
        old = estimate_cost("deepseek", "deepseek-chat", 0, 1_000_000, 0,
                            now - timedelta(days=40))
        assert data["totals"]["cost"] == round(priced + old, 2)
        # 每日只含窗口内：今天 2 次，但 cost 只有 DeepSeek 那一次
        today = data["daily"][-1]
        assert today["requests"] == 2
        assert today["cost"] == round(priced, 4)
        assert sum(d["requests"] for d in data["daily"]) == 2
        # 按模型分组：DeepSeek 计价在前；Kimi 标记 priced=False、cost=None
        assert data["models"][0]["model"] == "deepseek-chat"
        kimi = next(m for m in data["models"] if m["provider"] == "kimi")
        assert kimi["priced"] is False
        assert kimi["cost"] is None
        assert kimi["tokens"] == 600_000
