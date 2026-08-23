# -*- coding: utf-8 -*-
"""LLM 错误边界（修复方案 §4）行为测试：

- _classify_error：超时 / 401 / 403 / 429 / 400 / 404 / 422 / 5xx / 网络 → 统一异常分类，
  且分类后的消息不含 URL 等内部细节；
- LLMRouter：仅可切换错误（超时/限流/临时）触发故障切换，认证与请求错误不切换；
  单 Provider 最多重试 1 次；限流先退避；总调用受统一截止时间约束；
- 对外 API：稳定错误结构 {error: {code, message}, request_id}，响应不含 Provider 内部细节；
- Orchestrator._classify_operation_error：按异常类型（而非字符串）映射稳定 error_code。
"""
import asyncio
import time

import httpx
import pytest

from config import settings
from llm import DeepSeekClient
from llm.errors import (
    LLMAuthenticationError,
    LLMOutputValidationError,
    LLMRateLimitError,
    LLMRequestError,
    LLMTemporaryError,
    LLMTimeoutError,
)
from llm.router import LLMProviderUnavailableError, LLMRouter

_MESSAGES = [{"role": "user", "content": "hi"}]
# 故意带内部细节的"敏感"标记，用于断言这些内容不出现在分类消息/对外响应里
_SENSITIVE_URL = "https://internal-llm.example.com/v1/chat/completions"
_SENSITIVE_KEY = "sk-secret-key-12345"


def _status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", _SENSITIVE_URL, headers={"Authorization": f"Bearer {_SENSITIVE_KEY}"})
    return httpx.HTTPStatusError(
        f"HTTP {status}", request=request, response=httpx.Response(status, request=request)
    )


# ---------------------------------------------------------------------------
# _classify_error：底层异常 → 统一分类
# ---------------------------------------------------------------------------

class TestClassifyError:
    client = DeepSeekClient(api_key="dk-x")

    @pytest.mark.parametrize("status", [401, 403])
    def test_auth_status(self, status):
        assert isinstance(self.client._classify_error(_status_error(status)), LLMAuthenticationError)

    def test_rate_limit(self):
        assert isinstance(self.client._classify_error(_status_error(429)), LLMRateLimitError)

    @pytest.mark.parametrize("status", [400, 404, 422])
    def test_request_error(self, status):
        assert isinstance(self.client._classify_error(_status_error(status)), LLMRequestError)

    @pytest.mark.parametrize("status", [500, 502, 503])
    def test_server_error_is_temporary(self, status):
        assert isinstance(self.client._classify_error(_status_error(status)), LLMTemporaryError)

    def test_timeout(self):
        exc = httpx.TimeoutException("read timeout", request=httpx.Request("POST", _SENSITIVE_URL))
        assert isinstance(self.client._classify_error(exc), LLMTimeoutError)

    def test_network_failure_is_temporary(self):
        exc = httpx.ConnectError("connection refused", request=httpx.Request("POST", _SENSITIVE_URL))
        assert isinstance(self.client._classify_error(exc), LLMTemporaryError)

    def test_llm_error_passthrough(self):
        """已是统一分类的异常原样透传，不再二次分类。"""
        original = LLMRateLimitError("限流")
        assert self.client._classify_error(original) is original

    def test_classified_message_is_sanitized(self):
        """分类后的异常消息不含 URL/Key 等内部细节（原文只随 __cause__ 进服务端日志）。"""
        for raw in (_status_error(401), _status_error(429), _status_error(500)):
            message = str(self.client._classify_error(raw))
            assert _SENSITIVE_URL not in message
            assert _SENSITIVE_KEY not in message

    async def test_chat_maps_http_status(self, monkeypatch):
        """chat() 端到端：MockTransport 返回 429 → 抛 LLMRateLimitError。"""
        client = DeepSeekClient(api_key="dk-x")

        def handler(request):
            return httpx.Response(429, json={"error": {"message": "rate limited"}})

        monkeypatch.setattr(client, "_client", httpx.AsyncClient(
            base_url=client.base_url, transport=httpx.MockTransport(handler),
        ))
        with pytest.raises(LLMRateLimitError):
            await client.chat(_MESSAGES)


# ---------------------------------------------------------------------------
# LLMRouter：切换决策 / 重试上限 / 统一截止时间
# ---------------------------------------------------------------------------

def _router(monkeypatch) -> LLMRouter:
    """构造 deepseek + kimi 两家可用的 router（chat 由各自测试自行替换）。"""
    monkeypatch.setattr(settings, "llm_provider_priority", "deepseek,kimi")
    monkeypatch.setattr(settings, "deepseek_api_key", "dk-test")
    monkeypatch.setattr(settings, "kimi_api_key", "kk-test")
    monkeypatch.setattr(settings, "llm_model", "")
    return LLMRouter()


class _Probe:
    """可编程 Provider chat：按队列抛错/返回，记录调用次数。"""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def chat(self, messages, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0) if self.outcomes else "ok"
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class TestRouterFailover:
    async def test_switchable_error_fails_over(self, monkeypatch):
        """临时故障（5xx/网络类）：重试 1 次仍失败 → 切到下一个 Provider。"""
        router = _router(monkeypatch)
        deepseek = _Probe(LLMTemporaryError("503"), LLMTemporaryError("503"))
        kimi = _Probe("kimi 回复")
        monkeypatch.setattr(router.get_client("deepseek"), "chat", deepseek.chat)
        monkeypatch.setattr(router.get_client("kimi"), "chat", kimi.chat)
        provider, content = await router.chat(_MESSAGES)
        assert (provider, content) == ("kimi", "kimi 回复")
        assert deepseek.calls == 2, "单 Provider 最多重试 1 次（共 2 次调用）"
        assert kimi.calls == 1

    async def test_auth_error_no_failover(self, monkeypatch):
        """认证失败：不切换（换 Provider 解决不了配置问题），直接上抛。"""
        router = _router(monkeypatch)
        deepseek = _Probe(LLMAuthenticationError("401"))
        kimi = _Probe("kimi 回复")
        monkeypatch.setattr(router.get_client("deepseek"), "chat", deepseek.chat)
        monkeypatch.setattr(router.get_client("kimi"), "chat", kimi.chat)
        with pytest.raises(LLMAuthenticationError):
            await router.chat(_MESSAGES)
        assert deepseek.calls == 1, "认证错误不重试"
        assert kimi.calls == 0, "认证错误不切换"

    async def test_request_error_no_failover(self, monkeypatch):
        """请求错误（模型不存在/Prompt 过长）：不切换，直接上抛。"""
        router = _router(monkeypatch)
        deepseek = _Probe(LLMRequestError("404"))
        kimi = _Probe("kimi 回复")
        monkeypatch.setattr(router.get_client("deepseek"), "chat", deepseek.chat)
        monkeypatch.setattr(router.get_client("kimi"), "chat", kimi.chat)
        with pytest.raises(LLMRequestError):
            await router.chat(_MESSAGES)
        assert deepseek.calls == 1
        assert kimi.calls == 0

    async def test_single_provider_retry_limit(self, monkeypatch):
        """指定 Provider：可切换错误也只重试 1 次，之后原样抛出。"""
        router = _router(monkeypatch)
        deepseek = _Probe(LLMTemporaryError("503"), LLMTemporaryError("503"), "不会再被用到")
        monkeypatch.setattr(router.get_client("deepseek"), "chat", deepseek.chat)
        with pytest.raises(LLMTemporaryError):
            await router.chat(_MESSAGES, provider="deepseek")
        assert deepseek.calls == 2

    async def test_retry_succeeds_on_second_attempt(self, monkeypatch):
        """第一次超时、重试成功：不再切换，直接返回当前 Provider 结果。"""
        router = _router(monkeypatch)
        deepseek = _Probe(LLMTimeoutError("超时"), "重试成功")
        kimi = _Probe("kimi 回复")
        monkeypatch.setattr(router.get_client("deepseek"), "chat", deepseek.chat)
        monkeypatch.setattr(router.get_client("kimi"), "chat", kimi.chat)
        provider, content = await router.chat(_MESSAGES)
        assert (provider, content) == ("deepseek", "重试成功")
        assert kimi.calls == 0

    async def test_rate_limit_backs_off_before_retry(self, monkeypatch):
        """429 限流：退避后再重试（退避时长取自 RATE_LIMIT_BACKOFF）。"""
        import llm.router as router_mod

        router = _router(monkeypatch)
        deepseek = _Probe(LLMRateLimitError("429"), "退避后成功")
        monkeypatch.setattr(router.get_client("deepseek"), "chat", deepseek.chat)
        slept: list[float] = []

        async def fake_sleep(seconds):
            slept.append(seconds)

        monkeypatch.setattr(router_mod.asyncio, "sleep", fake_sleep)
        provider, content = await router.chat(_MESSAGES, provider="deepseek")
        assert content == "退避后成功"
        assert deepseek.calls == 2
        assert slept == [router_mod.RATE_LIMIT_BACKOFF]

    async def test_overall_deadline_caps_total_calls(self, monkeypatch):
        """统一截止时间：Provider 挂死时 wait_for 钳制单次调用，总耗时不超截止时间预算。"""
        monkeypatch.setattr(settings, "llm_timeout", 0.2)  # 截止时间 = 0.2 * 2 = 0.4s
        router = _router(monkeypatch)
        calls = 0

        async def hang(messages, **kwargs):
            nonlocal calls
            calls += 1
            await asyncio.sleep(10)
            return "不应到达"

        monkeypatch.setattr(router.get_client("deepseek"), "chat", hang)
        start = time.monotonic()
        with pytest.raises(LLMTimeoutError):
            await router.chat(_MESSAGES, provider="deepseek")
        elapsed = time.monotonic() - start
        assert elapsed < 2, f"超出统一截止时间预算（实际 {elapsed:.2f}s）"
        assert calls == 1, "截止时间耗尽后不应再发起第二次真实调用"

    async def test_all_switchable_failures_raise_unavailable(self, monkeypatch):
        """全部可切换故障都耗尽后：抛 LLMProviderUnavailableError（对外映射 503）。"""
        router = _router(monkeypatch)
        monkeypatch.setattr(router.get_client("deepseek"), "chat",
                            _Probe(LLMTemporaryError("503"), LLMTemporaryError("503")).chat)
        monkeypatch.setattr(router.get_client("kimi"), "chat",
                            _Probe(LLMTimeoutError("超时"), LLMTimeoutError("超时")).chat)
        with pytest.raises(LLMProviderUnavailableError):
            await router.chat(_MESSAGES)


# ---------------------------------------------------------------------------
# 对外 API：稳定错误结构 + request_id + 脱敏（§4.2）
# ---------------------------------------------------------------------------

class TestApiErrorContract:
    def test_llm_error_structure_and_sanitization(self, client, monkeypatch):
        """Provider 抛带敏感信息的异常：响应只有稳定结构与 request_id，不含任何内部细节。"""
        from llm import llm_router

        sensitive = (
            f"POST {_SENSITIVE_URL} Authorization: Bearer {_SENSITIVE_KEY} "
            "原始响应：{'error': 'upstream trace'}"
        )

        async def boom(messages, **kwargs):
            raise LLMProviderUnavailableError(sensitive)

        monkeypatch.setattr(llm_router, "chat", boom)
        resp = client.post("/api/assistant/chat", json={"message": "今天背了多少题？"})
        assert resp.status_code == 503
        body = resp.json()
        assert body["error"]["code"] == "LLM_PROVIDER_UNAVAILABLE"
        assert body["error"]["message"] == "模型服务暂不可用，请检查模型配置或稍后重试"
        assert body["request_id"]
        assert resp.headers["x-request-id"] == body["request_id"]
        # 脱敏红线：URL、API Key、Provider 原始响应一律不出现在响应里
        assert _SENSITIVE_URL not in resp.text
        assert _SENSITIVE_KEY not in resp.text
        assert "upstream trace" not in resp.text

    def test_error_code_varies_by_type(self, client, monkeypatch):
        """不同异常类型映射到各自的稳定 code（超时 504 / 认证 503 LLM_AUTH_FAILED）。"""
        from llm import llm_router

        async def timeout(messages, **kwargs):
            raise LLMTimeoutError("Provider deepseek 请求超时")

        monkeypatch.setattr(llm_router, "chat", timeout)
        resp = client.post("/api/assistant/chat", json={"message": "hi"})
        assert resp.status_code == 504
        assert resp.json()["error"]["code"] == "LLM_TIMEOUT"

        async def auth(messages, **kwargs):
            raise LLMAuthenticationError(f"401 from {_SENSITIVE_URL} key={_SENSITIVE_KEY}")

        monkeypatch.setattr(llm_router, "chat", auth)
        resp = client.post("/api/assistant/chat", json={"message": "hi"})
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "LLM_AUTH_FAILED"
        assert _SENSITIVE_URL not in resp.text
        assert _SENSITIVE_KEY not in resp.text


# ---------------------------------------------------------------------------
# Orchestrator：error_code 按异常类型映射（不解析字符串）
# ---------------------------------------------------------------------------

class TestClassifyOperationError:
    def test_maps_by_exception_type(self):
        from agents.orchestrator import OrchestratorAgent, StateError

        classify = OrchestratorAgent._classify_operation_error
        assert classify(StateError("状态非法")) == "STATE_ERROR"
        assert classify(LLMTimeoutError("x")) == "LLM_TIMEOUT"
        assert classify(LLMRateLimitError("x")) == "LLM_RATE_LIMITED"
        assert classify(LLMAuthenticationError("x")) == "LLM_AUTH_FAILED"
        assert classify(LLMRequestError("x")) == "LLM_REQUEST_INVALID"
        assert classify(LLMOutputValidationError("x")) == "LLM_OUTPUT_INVALID"
        assert classify(LLMTemporaryError("x")) == "LLM_UNAVAILABLE"
        assert classify(LLMProviderUnavailableError("x")) == "LLM_UNAVAILABLE"
        # 消息文本不影响分类：同名文本的非 LLM 异常仍是 INTERNAL_ERROR
        assert classify(ValueError("LLM_TIMEOUT")) == "INTERNAL_ERROR"
