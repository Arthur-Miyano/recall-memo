# -*- coding: utf-8 -*-
"""API 覆盖（四）：settings/llm 密钥安全与 .env 写入。

安全红线断言：响应体绝不包含完整 API Key，只回掩码；
POST 写 .env 用临时文件隔离（monkeypatch ENV_PATH），绝不碰项目根的真实 .env。
"""
import os

import pytest

from config import settings


@pytest.fixture()
def isolated_settings(tmp_path, monkeypatch):
    """隔离 settings 副作用：临时 .env + 快照恢复 settings 字段与相关环境变量。"""
    from api import settings as settings_api

    env_path = tmp_path / ".env"
    env_path.write_text(
        "# 注释行\nDEEPSEEK_API_KEY=sk-olddeepseekkey123456\nKIMI_API_KEY=\nOTHER_LINE=保留我\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_api, "ENV_PATH", env_path)

    # 快照并恢复 settings 字段（端点会直接 setattr 全局 settings）
    fields = ("deepseek_api_key", "kimi_api_key", "llm_model", "llm_provider_priority")
    snapshot = {f: getattr(settings, f) for f in fields}
    env_snapshot = {k: os.environ.get(k) for k in ("DEEPSEEK_API_KEY", "KIMI_API_KEY", "LLM_MODEL", "LLM_PROVIDER_PRIORITY")}
    yield env_path
    for f, v in snapshot.items():
        setattr(settings, f, v)
    for k, v in env_snapshot.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


class TestLlmSettingsGet:
    def test_response_shape_and_no_full_key(self, client, isolated_settings):
        resp = client.get("/api/settings/llm")
        assert resp.status_code == 200
        body_text = resp.text
        data = resp.json()

        assert "providers" in data and "provider" in data
        assert "key_configured" in data and "key_masked" in data
        assert "env_detected" in data

        # 安全断言：若当前配置里有真 Key，响应体不得包含完整 Key
        real_key = settings.deepseek_api_key
        if real_key:
            assert real_key not in body_text, "响应体泄露了完整 API Key！"
            assert data["key_masked"] != real_key

    def test_mask_format(self, client, isolated_settings, monkeypatch):
        monkeypatch.setattr(settings, "deepseek_api_key", "sk-abcdefgh12345678")
        monkeypatch.setattr(settings, "llm_provider_priority", "deepseek,kimi")
        data = client.get("/api/settings/llm").json()
        assert data["key_configured"] is True
        assert data["key_masked"] == "sk-••••5678", f"掩码格式错误：{data['key_masked']}"

        # 短 key 全掩码
        monkeypatch.setattr(settings, "deepseek_api_key", "short")
        assert client.get("/api/settings/llm").json()["key_masked"] == "••••"

        # 空 key
        monkeypatch.setattr(settings, "deepseek_api_key", "")
        empty = client.get("/api/settings/llm").json()
        assert empty["key_configured"] is False
        assert empty["key_masked"] is None


class TestLlmSettingsPost:
    def test_update_writes_env_preserving_other_lines(self, client, isolated_settings):
        new_key = "sk-newtestkey9876543210ab"
        resp = client.post(
            "/api/settings/llm",
            json={"provider": "deepseek", "api_key": new_key, "model": "deepseek-chat-v3"},
        )
        assert resp.status_code == 200

        # 响应只回掩码，绝不含完整 Key
        assert new_key not in resp.text, "POST 响应泄露了完整 API Key！"
        assert resp.json()["key_masked"] == "sk-••••10ab"

        # .env：目标行原位替换，其余行（注释/其他 key/杂行）原样保留
        content = isolated_settings.read_text(encoding="utf-8")
        assert f"DEEPSEEK_API_KEY={new_key}" in content
        assert "# 注释行" in content
        assert "KIMI_API_KEY=" in content
        assert "OTHER_LINE=保留我" in content
        assert "LLM_MODEL=deepseek-chat-v3" in content
        assert "LLM_PROVIDER_PRIORITY=" in content

        # settings 已同步
        assert settings.deepseek_api_key == new_key
        assert settings.llm_model == "deepseek-chat-v3"

    def test_provider_promoted_to_priority_first(self, client, isolated_settings):
        resp = client.post("/api/settings/llm", json={"provider": "kimi"})
        assert resp.status_code == 200
        assert settings.provider_priority[0] == "kimi"
        content = isolated_settings.read_text(encoding="utf-8")
        assert "LLM_PROVIDER_PRIORITY=kimi,deepseek" in content

    def test_unsupported_provider_400(self, client, isolated_settings):
        resp = client.post("/api/settings/llm", json={"provider": "openai"})
        assert resp.status_code == 400

    def test_no_api_key_keeps_existing_line(self, client, isolated_settings):
        """不带 api_key 时不修改 .env 里的 Key 行。"""
        client.post("/api/settings/llm", json={"provider": "deepseek", "model": "m1"})
        content = isolated_settings.read_text(encoding="utf-8")
        assert "DEEPSEEK_API_KEY=sk-olddeepseekkey123456" in content

    def test_write_failure_does_not_change_runtime_settings(self, client, isolated_settings, monkeypatch):
        """持久化失败时，环境变量和当前进程配置都保持原值。"""
        from api import settings as settings_api

        old_key = settings.deepseek_api_key
        old_model = settings.llm_model
        old_priority = settings.llm_provider_priority
        old_env_key = os.environ.get("DEEPSEEK_API_KEY")
        old_env_model = os.environ.get("LLM_MODEL")
        old_env_priority = os.environ.get("LLM_PROVIDER_PRIORITY")

        def fail_write(_updates):
            raise OSError("模拟配置写入失败")

        monkeypatch.setattr(settings_api, "_write_env", fail_write)
        with pytest.raises(OSError, match="模拟配置写入失败"):
            client.post(
                "/api/settings/llm",
                json={"provider": "deepseek", "api_key": "sk-new", "model": "new-model"},
            )

        assert settings.deepseek_api_key == old_key
        assert settings.llm_model == old_model
        assert settings.llm_provider_priority == old_priority
        assert os.environ.get("DEEPSEEK_API_KEY") == old_env_key
        assert os.environ.get("LLM_MODEL") == old_env_model
        assert os.environ.get("LLM_PROVIDER_PRIORITY") == old_env_priority


class TestEnvAtomicWrite:
    """.env 原子写入 + 同进程写锁（§10）：并发不撕裂，失败不留半截。"""

    def test_concurrent_writes_no_tearing(self, isolated_settings):
        import re
        import threading

        from api.settings import _write_env

        def worker(i: int) -> None:
            for j in range(50):
                _write_env({f"TK{i}": f"v{i}-{j}-" + "x" * 100})

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        lines = isolated_settings.read_text(encoding="utf-8").splitlines()
        seen = set()
        for line in lines:
            if not line.strip() or line.startswith("#"):
                continue
            name, sep, value = line.partition("=")
            assert sep, f"撕裂行（缺 =）：{line!r}"
            if name.startswith("TK"):
                seen.add(name)
                i = int(name[2:])
                assert re.fullmatch(rf"v{i}-\d+-x{{100}}", value), f"撕裂行（值不完整）：{line!r}"
        assert seen == {f"TK{i}" for i in range(8)}
        # 原有行未受损
        assert "OTHER_LINE=保留我" in lines
        assert "# 注释行" in lines

    def test_failure_leaves_original_and_no_temp_file(self, isolated_settings, monkeypatch):
        import os as os_mod

        from api import settings as settings_api

        original = isolated_settings.read_text(encoding="utf-8")

        def boom(*args):
            raise OSError("模拟替换失败")

        monkeypatch.setattr(os_mod, "replace", boom)
        with pytest.raises(OSError, match="模拟替换失败"):
            settings_api._write_env({"NEW_KEY": "v"})
        assert isolated_settings.read_text(encoding="utf-8") == original
        assert not list(isolated_settings.parent.glob(".env.*.tmp")), "失败后残留临时文件"


class TestRouterModelOverride:
    """llm_model 只覆盖优先级第一的默认 Provider（模型名是 Provider 私有的）。"""

    def test_override_hits_default_provider_only(self, monkeypatch):
        from llm.router import LLMRouter

        monkeypatch.setattr(settings, "llm_model", "deepseek-v4-flash")
        monkeypatch.setattr(settings, "llm_provider_priority", "deepseek,kimi")
        clients = LLMRouter._build_clients()
        assert clients["deepseek"].model == "deepseek-v4-flash"
        assert clients["kimi"].model != "deepseek-v4-flash"

    def test_override_follows_priority_order(self, monkeypatch):
        """默认 Provider 换成 kimi 时，覆盖跟着优先级走。"""
        from llm.router import LLMRouter

        monkeypatch.setattr(settings, "llm_model", "kimi-k3")
        monkeypatch.setattr(settings, "llm_provider_priority", "kimi,deepseek")
        clients = LLMRouter._build_clients()
        assert clients["kimi"].model == "kimi-k3"
        assert clients["deepseek"].model != "kimi-k3"
