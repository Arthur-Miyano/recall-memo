# -*- coding: utf-8 -*-
"""本地安全边界（修复方案 §10）：Host/Origin 校验 + 本地令牌 + 基础响应头。

威胁模型：应用强制绑定 127.0.0.1、单用户本地运行，防的是浏览器里的恶意网页
（DNS 重绑定伪造 Host 读接口、跨域表单/fetch 打写接口），不防本机进程。

- Host 校验：/api 只接受回环 Host（任意端口，兼容 Vite dev 代理转发时 Host 不变）；
- Origin 校验：带 Origin 的写请求必须来自回环源（浏览器跨域写必带 Origin；
  curl/脚本无 Origin，由 Host 校验兜底）；
- 本地令牌：启动时生成，经 GET /api/health 下发给前端页面（跨域网页受 SOP/CORS
  限制读不到响应体），敏感写接口要求 X-Local-Token 头。
  令牌只存内存：不落盘、不进日志、不进仓库，重启即换新。

未来若允许监听 0.0.0.0 / 云端部署 / 多用户，本节必须升级为发布阻断条件（见方案 §10 末段）。
"""
import re
import secrets
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse

LOCAL_TOKEN_HEADER = "X-Local-Token"

# 启动时生成的本地随机令牌：每次重启换新；前端经 /api/health 获取，403 时自动重取重试
LOCAL_TOKEN = secrets.token_urlsafe(32)

# 回环主机名（不限制端口：8000 生产托管 / 5173 Vite dev 代理）
# testserver 仅 httpx TestClient 默认 Host，公网不可解析，仅测试出现
_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1", "testserver"}

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# 敏感接口（§10：设置、数据库导入导出、删除、批量迁移）：要求 X-Local-Token 头。
# 健康检查、会话训练、笔记、题库浏览等正常业务读写不在此列，不被令牌挡住。
_SENSITIVE: list[tuple[str, "re.Pattern[str]"]] = [
    ("POST", re.compile(r"^/api/settings/llm$")),            # 改模型/Key（写 .env）
    ("GET", re.compile(r"^/api/settings/export$")),          # 整库导出（GET 但敏感）
    ("POST", re.compile(r"^/api/settings/import-db$")),      # 整库合并导入
    ("DELETE", re.compile(r"^/api/bank/questions/\d+$")),    # 删除题目（连同答题记录）
    ("POST", re.compile(r"^/api/bank/questions/migrate$")),  # 批量迁移
]

# 基础响应头（§10）：CSP / nosniff / Referrer-Policy / 禁止 iframe 嵌入
# style-src 放 'unsafe-inline'：模板大量 style="" 属性；script-src 严格 'self'（Vite 产物无内联脚本）
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; connect-src 'self'; font-src 'self' data:; "
        "object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}


def _hostname(host: str) -> str:
    """Host 头 → 主机名（小写、去端口；兼容 IPv6 字面量 [::1]:port）。"""
    host = (host or "").strip().lower()
    if host.startswith("["):
        return host[1:host.find("]")] if "]" in host else host
    return host.split(":", 1)[0]


def _is_sensitive(method: str, path: str) -> bool:
    return any(method == m and p.match(path) for m, p in _SENSITIVE)


def _reject(request: Request, code: str, message: str) -> JSONResponse:
    """403 + 稳定错误码，与 LLM/上传错误同一结构（§4.2）；request_id 由外层中间件已写入。"""
    return JSONResponse(
        status_code=403,
        content={
            "error": {"code": code, "message": message},
            "request_id": getattr(request.state, "request_id", None),
        },
    )


async def local_guard_middleware(request: Request, call_next):
    """/api 访问闸门：Host 校验 → Origin 校验 → 敏感接口令牌校验。"""
    path = request.url.path
    if path.startswith("/api"):
        if _hostname(request.headers.get("host", "")) not in _ALLOWED_HOSTS:
            return _reject(request, "FORBIDDEN_HOST", "仅允许本机回环地址访问")
        origin = request.headers.get("origin")
        if origin and request.method in _UNSAFE_METHODS:
            if (urlsplit(origin).hostname or "").lower() not in _ALLOWED_HOSTS:
                return _reject(request, "FORBIDDEN_ORIGIN", "仅允许本机页面发起的写请求")
        if _is_sensitive(request.method, path):
            token = request.headers.get(LOCAL_TOKEN_HEADER, "")
            if not token:
                return _reject(request, "LOCAL_TOKEN_REQUIRED", "缺少本地令牌：请从官方启动入口打开页面")
            if not secrets.compare_digest(token, LOCAL_TOKEN):
                return _reject(request, "LOCAL_TOKEN_INVALID", "本地令牌无效：后端重启后请刷新页面重试")
    return await call_next(request)


async def security_headers_middleware(request: Request, call_next):
    """所有响应挂基础安全响应头（setdefault：不覆盖路由已显式设置的同名头）。"""
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response
