# -*- coding: utf-8 -*-
"""本地安全边界（修复方案 §10）：Host/Origin 校验、本地令牌、基础响应头。

client fixture 默认带正确 X-Local-Token（见 conftest）；
反例用空头（→ LOCAL_TOKEN_REQUIRED）或错 token（→ LOCAL_TOKEN_INVALID）覆盖。
"""
import pytest

from infrastructure.localguard import LOCAL_TOKEN, LOCAL_TOKEN_HEADER

# 敏感接口（§10 清单：设置、数据库导入导出、删除、批量迁移）+ 过闸后的代表性落点
SENSITIVE_CASES = [
    ("POST", "/api/settings/llm", {"json": {"provider": "openai"}}),
    ("GET", "/api/settings/export", {}),
    ("POST", "/api/settings/import-db", {}),
    ("DELETE", "/api/bank/questions/999", {}),
    ("POST", "/api/bank/questions/migrate", {"json": {"question_ids": [], "to_stack": "go"}}),
]


class TestHostGuard:
    def test_forbidden_host_rejected(self, client):
        resp = client.get("/api/health", headers={"Host": "evil.example.com"})
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN_HOST"
        assert resp.json()["request_id"]  # 稳定错误结构带 request_id（§4.2）

    @pytest.mark.parametrize("host", ["127.0.0.1:8000", "localhost:5173", "127.0.0.1", "localhost"])
    def test_loopback_hosts_allowed(self, client, host):
        assert client.get("/api/health", headers={"Host": host}).status_code == 200


class TestOriginGuard:
    def test_forbidden_origin_on_write_rejected(self, client):
        resp = client.post("/api/notes", json={"title": "x"}, headers={"Origin": "http://evil.example.com"})
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN_ORIGIN"

    @pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:8000"])
    def test_loopback_origin_on_write_allowed(self, client, origin):
        resp = client.post("/api/notes", json={"title": "x"}, headers={"Origin": origin})
        assert resp.status_code != 403

    def test_write_without_origin_allowed(self, client):
        """curl/脚本无 Origin：Host 校验已过则放行（防浏览器跨域，不防本机进程）。"""
        assert client.post("/api/notes", json={"title": "x"}).status_code != 403


class TestLocalToken:
    def test_health_issues_token(self, client):
        """下发通道：GET /api/health 返回当前令牌（跨域网页受 SOP/CORS 限制读不到）。"""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["local_token"] == LOCAL_TOKEN

    @pytest.mark.parametrize(("method", "path", "kwargs"), SENSITIVE_CASES)
    def test_sensitive_without_token_rejected(self, client, method, path, kwargs):
        resp = client.request(method, path, headers={LOCAL_TOKEN_HEADER: ""}, **kwargs)
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "LOCAL_TOKEN_REQUIRED"

    @pytest.mark.parametrize(("method", "path", "kwargs"), SENSITIVE_CASES)
    def test_sensitive_with_wrong_token_rejected(self, client, method, path, kwargs):
        resp = client.request(method, path, headers={LOCAL_TOKEN_HEADER: "sk-wrong-token"}, **kwargs)
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "LOCAL_TOKEN_INVALID"

    @pytest.mark.parametrize(("method", "path", "kwargs"), SENSITIVE_CASES)
    def test_sensitive_with_correct_token_passes_guard(self, client, method, path, kwargs):
        """正确令牌过闸（落到业务层的状态码由业务决定，只要不是 403）。"""
        resp = client.request(method, path, **kwargs)  # client 默认带正确令牌
        assert resp.status_code != 403

    def test_normal_business_not_blocked(self, client):
        """普通业务读写不要求令牌：健康检查 / 题库浏览 / 笔记 / 会话训练不挡。"""
        no_token = {LOCAL_TOKEN_HEADER: ""}
        assert client.get("/api/health", headers=no_token).status_code == 200
        assert client.get("/api/bank/overview", headers=no_token).status_code == 200
        assert client.get("/api/settings/llm", headers=no_token).status_code == 200
        assert client.post("/api/notes", json={"title": "x"}, headers=no_token).status_code != 403
        # 删除笔记/助理会话属正常内容管理，不在 §10 敏感清单
        assert client.delete("/api/notes/999", headers=no_token).status_code != 403
        assert client.delete("/api/assistant/sessions/999", headers=no_token).status_code != 403


class TestSecurityHeaders:
    @pytest.mark.parametrize("path", ["/api/health", "/api/bank/overview"])
    def test_headers_on_normal_responses(self, client, path):
        resp = client.get(path)
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["Referrer-Policy"] == "no-referrer"
        csp = resp.headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_headers_on_guard_rejection(self, client):
        """guard 的 403 同样带安全响应头（headers 中间件在 guard 外层）。"""
        resp = client.get("/api/health", headers={"Host": "evil.example.com"})
        assert resp.status_code == 403
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
