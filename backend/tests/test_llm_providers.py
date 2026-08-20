# -*- coding: utf-8 -*-
"""智谱/豆包 Provider 接入覆盖：

- client 构造与可用性判断（无真实 Key，全部本地断言/mock）；
- router 注册表与优先级切换包含新 Provider；
- settings 接口对新 Provider 的读写（响应只回掩码，不泄露完整 Key）；
- 两家均不按量计价（只记 token 用量）。
"""
import os

import pytest

from config import settings
from llm import DoubaoClient, ZhipuClient


class TestNewProviderClients:
    def test_zhipu_client_defaults(self):
        c = ZhipuClient(api_key="")
        assert c.name == "zhipu"
        assert c.base_url == "https://open.bigmodel.cn/api/paas/v4"
        assert c.model == "glm-4.7-flash"
        assert c.available is False
        assert ZhipuClient(api_key="zk-x").available is True

    def test_doubao_client_defaults(self):
        c = DoubaoClient(api_key="")
        assert c.name == "doubao"
        assert c.base_url == "https://ark.cn-beijing.volces.com/api/v3"
        # 默认模型可为模型 ID；推理接入点 ep-xxx 也可直接当 model 用（设置面板覆盖）
        assert c.model == "doubao-seed-2-0-mini-260428"
        assert c.available is False
        assert DoubaoClient(api_key="dk-x").available is True

    def test_extract_content_openai_shape(self):
        data = {"choices": [{"message": {"content": "你好"}}]}
        assert ZhipuClient(api_key="x")._extract_content(data) == "你好"
        assert DoubaoClient(api_key="x")._extract_content(data) == "你好"


class TestRouterRegistration:
    def test_registry_and_key_attr(self):
        from llm.router import PROVIDER_ENV_VAR, PROVIDER_KEY_ATTR, PROVIDER_REGISTRY

        assert set(PROVIDER_REGISTRY) == {"deepseek", "kimi", "zhipu", "doubao"}
        assert PROVIDER_KEY_ATTR["zhipu"] == "zhipu_api_key"
        assert PROVIDER_KEY_ATTR["doubao"] == "doubao_api_key"
        assert PROVIDER_ENV_VAR["zhipu"] == "ZHIPU_API_KEY"
        assert PROVIDER_ENV_VAR["doubao"] == "DOUBAO_API_KEY"

    def test_build_clients_reads_settings_keys(self, monkeypatch):
        from llm.router import LLMRouter

        monkeypatch.setattr(settings, "zhipu_api_key", "zk-test")
        monkeypatch.setattr(settings, "doubao_api_key", "")
        clients = LLMRouter._build_clients()
        assert clients["zhipu"].available is True
        assert clients["doubao"].available is False

    async def test_priority_fallback_covers_new_providers(self, monkeypatch):
        """优先级 zhipu -> doubao：zhipu 调用失败自动切到 doubao。"""
        from llm.router import LLMRouter

        monkeypatch.setattr(settings, "llm_provider_priority", "zhipu,doubao")
        monkeypatch.setattr(settings, "zhipu_api_key", "zk-test")
        monkeypatch.setattr(settings, "doubao_api_key", "dk-test")
        monkeypatch.setattr(settings, "llm_model", "")
        router = LLMRouter()

        async def fail(messages, **kwargs):
            raise RuntimeError("boom")

        async def ok(messages, **kwargs):
            return "你好"

        monkeypatch.setattr(router.get_client("zhipu"), "chat", fail)
        monkeypatch.setattr(router.get_client("doubao"), "chat", ok)
        provider, content = await router.chat([{"role": "user", "content": "hi"}])
        assert (provider, content) == ("doubao", "你好")

    async def test_unconfigured_new_provider_skipped(self, monkeypatch):
        """新 Provider 未配 Key 时视为不可用，直接跳过。"""
        from llm.router import LLMProviderUnavailableError, LLMRouter

        monkeypatch.setattr(settings, "llm_provider_priority", "zhipu,doubao")
        monkeypatch.setattr(settings, "zhipu_api_key", "")
        monkeypatch.setattr(settings, "doubao_api_key", "")
        router = LLMRouter()
        with pytest.raises(LLMProviderUnavailableError, match="没有任何"):
            await router.chat([{"role": "user", "content": "hi"}])


class TestUsageUnpriced:
    def test_new_providers_not_priced(self):
        from datetime import datetime

        from llm.usage import UNPRICED_PROVIDERS, estimate_cost

        assert {"zhipu", "doubao"} <= UNPRICED_PROVIDERS
        at = datetime(2026, 8, 19, 10).astimezone()
        assert estimate_cost("zhipu", "glm-4.7-flash", 0, 1000, 1000, at) is None
        assert estimate_cost("doubao", "doubao-seed-2-0-mini-260428", 0, 1000, 1000, at) is None


@pytest.fixture()
def isolated_settings(tmp_path, monkeypatch):
    """隔离 settings 副作用：临时 .env + 快照恢复 settings 字段与相关环境变量。"""
    from api import settings as settings_api

    env_path = tmp_path / ".env"
    env_path.write_text(
        "# 注释行\nDEEPSEEK_API_KEY=sk-olddeepseekkey123456\nOTHER_LINE=保留我\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_api, "ENV_PATH", env_path)

    fields = (
        "deepseek_api_key", "kimi_api_key", "zhipu_api_key", "doubao_api_key",
        "llm_model", "llm_provider_priority",
    )
    snapshot = {f: getattr(settings, f) for f in fields}
    env_names = (
        "DEEPSEEK_API_KEY", "KIMI_API_KEY", "ZHIPU_API_KEY", "DOUBAO_API_KEY",
        "LLM_MODEL", "LLM_PROVIDER_PRIORITY",
    )
    env_snapshot = {k: os.environ.get(k) for k in env_names}
    yield env_path
    for f, v in snapshot.items():
        setattr(settings, f, v)
    for k, v in env_snapshot.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class TestSettingsApiNewProviders:
    def test_get_lists_new_providers_and_env_vars(self, client, isolated_settings):
        data = client.get("/api/settings/llm").json()
        assert set(data["providers"]) == {"deepseek", "kimi", "zhipu", "doubao"}
        assert data["env_detected"]["zhipu"]["env_var"] == "ZHIPU_API_KEY"
        assert data["env_detected"]["doubao"]["env_var"] == "DOUBAO_API_KEY"

    def test_post_zhipu_writes_env_and_masks_key(self, client, isolated_settings):
        new_key = "zhipu-testkey-abcdef123456"
        resp = client.post(
            "/api/settings/llm",
            json={"provider": "zhipu", "api_key": new_key, "model": "glm-4.7-flash"},
        )
        assert resp.status_code == 200
        assert new_key not in resp.text, "POST 响应泄露了完整 API Key！"
        assert resp.json()["key_masked"] == "zhi••••3456"

        content = isolated_settings.read_text(encoding="utf-8")
        assert f"ZHIPU_API_KEY={new_key}" in content
        assert "# 注释行" in content and "OTHER_LINE=保留我" in content
        assert "LLM_PROVIDER_PRIORITY=zhipu," in content
        assert settings.zhipu_api_key == new_key
        assert settings.provider_priority[0] == "zhipu"

    def test_post_doubao_promoted_to_priority_first(self, client, isolated_settings):
        resp = client.post("/api/settings/llm", json={"provider": "doubao"})
        assert resp.status_code == 200
        assert settings.provider_priority[0] == "doubao"
        content = isolated_settings.read_text(encoding="utf-8")
        assert content.startswith("# 注释行")
        assert "LLM_PROVIDER_PRIORITY=doubao," in content
