# -*- coding: utf-8 -*-
"""LLM 用量覆盖：record_usage 落库（含容错）+ estimate_cost 计价 + /stats/llm-usage 聚合。"""
from datetime import datetime, timedelta, timezone

from llm.usage import DEFAULT_PRICE, PRICE_PER_1M, estimate_cost, record_usage
from models import LLMUsage


class TestRecordUsage:
    def test_writes_row(self, db):
        record_usage("deepseek", "deepseek-chat",
                     {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150})
        rows = db.query(LLMUsage).all()
        assert len(rows) == 1
        assert rows[0].provider == "deepseek"
        assert rows[0].prompt_tokens == 100
        assert rows[0].total_tokens == 150

    def test_none_and_zero_usage_skipped(self, db):
        record_usage("deepseek", "deepseek-chat", None)
        record_usage("deepseek", "deepseek-chat", {})
        record_usage("deepseek", "deepseek-chat", {"prompt_tokens": 0, "completion_tokens": 0})
        assert db.query(LLMUsage).count() == 0

    def test_missing_total_derived(self, db):
        record_usage("kimi", "moonshot-v1-8k", {"prompt_tokens": 10, "completion_tokens": 5})
        assert db.query(LLMUsage).one().total_tokens == 15


class TestEstimateCost:
    def test_known_model(self):
        # deepseek-chat：输入 ¥2/1M，输出 ¥3/1M → 1M 入 + 1M 出 = ¥5
        assert estimate_cost("deepseek-chat", 1_000_000, 1_000_000) == 5.0

    def test_unknown_model_falls_back_to_default(self):
        price = DEFAULT_PRICE
        expected = (100 * price["input"] + 100 * price["output"]) / 1_000_000
        assert estimate_cost("some-new-model", 100, 100) == expected

    def test_price_table_covers_default_models(self):
        assert "deepseek-chat" in PRICE_PER_1M
        assert "moonshot-v1-8k" in PRICE_PER_1M


def _add_usage(db, model="deepseek-chat", provider="deepseek", days_ago=0,
               prompt=1000, completion=500):
    row = LLMUsage(
        provider=provider, model=model,
        prompt_tokens=prompt, completion_tokens=completion,
        total_tokens=prompt + completion,
        created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )
    db.add(row)
    db.commit()
    return row


class TestLlmUsageApi:
    def test_empty(self, client):
        data = client.get("/api/stats/llm-usage").json()
        assert data["totals"] == {"cost": 0.0, "requests": 0, "tokens": 0}
        assert len(data["daily"]) == 30
        assert all(d["requests"] == 0 for d in data["daily"])
        assert data["models"] == []

    def test_aggregation(self, client, db):
        _add_usage(db, prompt=1_000_000, completion=0)                      # 今天，¥2
        _add_usage(db, model="moonshot-v1-8k", provider="kimi",
                   prompt=0, completion=100_000)                            # 今天，¥1.2
        _add_usage(db, days_ago=40, prompt=1_000_000, completion=0)         # 40 天前（出窗口），¥2

        data = client.get("/api/stats/llm-usage?days=30").json()
        # 总计为全量：3 次、¥5.2、tokens 全计
        assert data["totals"]["requests"] == 3
        assert data["totals"]["cost"] == 5.2
        assert data["totals"]["tokens"] == 1_000_000 + 100_000 + 1_000_000
        # 每日只含窗口内：今天 2 次 ¥3.2，其余为 0；40 天前的不入 daily
        today = data["daily"][-1]
        assert today["requests"] == 2
        assert today["cost"] == 3.2
        assert sum(d["requests"] for d in data["daily"]) == 2
        # 按模型分组，花费降序
        assert [m["model"] for m in data["models"]] == ["deepseek-chat", "moonshot-v1-8k"]
        assert data["models"][0]["cost"] == 4.0
        assert data["models"][1]["provider"] == "kimi"
