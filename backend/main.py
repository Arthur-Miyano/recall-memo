# -*- coding: utf-8 -*-
"""FastAPI 入口：uvicorn main:app --workers 1"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api import assistant, bank, datamove, events as events_api, health, home, llm, notes, sessions, settings, stats
from application.uploads import UploadRejectedError
from database import init_db
from infrastructure.documents import DocumentParseError
from llm.errors import (
    LLMAuthenticationError,
    LLMError,
    LLMOutputValidationError,
    LLMRateLimitError,
    LLMRequestError,
    LLMTemporaryError,
    LLMTimeoutError,
)
from llm.router import LLMProviderUnavailableError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时建表
    init_db()
    yield


app = FastAPI(title="程序员八股背诵 Agent", lifespan=lifespan)


# ----------------------------------------------------------------------
# 请求链路与 LLM 错误边界（修复方案 §4.2）：request_id + 稳定错误结构
# ----------------------------------------------------------------------

@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """每个请求生成 request_id：挂响应头，错误响应体内也带上，便于贯通排障。"""
    request.state.request_id = uuid4().hex[:12]
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


# 异常类型 → (HTTP 状态码, 稳定错误码, 对外消息)。对外消息不含 Provider 原始响应/
# 内部 URL/请求头/Prompt/异常原文——那些只随 __cause__ 链进服务端脱敏日志。
_LLM_ERROR_MAP: list[tuple[type[LLMError], int, str, str]] = [
    (LLMTimeoutError, 504, "LLM_TIMEOUT", "模型服务响应超时，请稍后重试"),
    (LLMRateLimitError, 503, "LLM_RATE_LIMITED", "模型服务限流中，请稍后重试"),
    (LLMAuthenticationError, 503, "LLM_AUTH_FAILED", "模型 API Key 认证失败，请到设置页检查模型与 Key 配置"),
    (LLMRequestError, 500, "LLM_REQUEST_INVALID", "模型请求参数有误（模型名/输入长度），请检查设置页配置"),
    (LLMOutputValidationError, 502, "LLM_OUTPUT_INVALID", "模型返回内容未通过校验，请重试"),
    (LLMTemporaryError, 503, "LLM_PROVIDER_UNAVAILABLE", "模型服务暂不可用，请稍后重试"),
    (LLMProviderUnavailableError, 503, "LLM_PROVIDER_UNAVAILABLE", "模型服务暂不可用，请检查模型配置或稍后重试"),
]


@app.exception_handler(LLMError)
async def llm_error_handler(request: Request, exc: LLMError) -> JSONResponse:
    """LLM 错误统一出口：稳定结构 {error: {code, message}, request_id}。"""
    status, code, message = 503, "LLM_PROVIDER_UNAVAILABLE", "模型服务暂不可用，请检查模型配置或稍后重试"
    for cls, s, c, m in _LLM_ERROR_MAP:
        if isinstance(exc, cls):
            status, code, message = s, c, m
            break
    request_id = getattr(request.state, "request_id", None)
    logger.warning("LLM 错误 [%s] request_id=%s：%s", code, request_id, exc)
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}, "request_id": request_id},
    )


# ----------------------------------------------------------------------
# 上传/导入策略错误（修复方案 §5）：稳定 4xx 错误码，与 LLM 错误同一结构
# ----------------------------------------------------------------------

@app.exception_handler(UploadRejectedError)
@app.exception_handler(DocumentParseError)
async def upload_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """上传策略/文档解析错误统一出口：4xx + {error: {code, message}, request_id}。"""
    status = getattr(exc, "status", 400)
    code = getattr(exc, "code", "UPLOAD_REJECTED")
    request_id = getattr(request.state, "request_id", None)
    logger.warning("上传被拒绝 [%s] request_id=%s：%s", code, request_id, exc)
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": str(exc)}, "request_id": request_id},
    )

# 本地开发：允许 Vite dev server 跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(llm.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(home.router, prefix="/api")
app.include_router(bank.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(datamove.router, prefix="/api")
app.include_router(assistant.router, prefix="/api")
app.include_router(notes.router, prefix="/api")
app.include_router(events_api.router, prefix="/api")

# 生产模式：托管前端构建产物（frontend/dist），SPA 路由回退到 index.html
# 开发模式不存在 dist 时跳过，走 Vite dev server + /api 代理
DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def mount_spa(app: FastAPI, dist_dir: Path) -> bool:
    """把 dist 挂到 app 上：assets 静态目录 + SPA 回退。dist 不存在则不动，返回是否已挂载。

    独立成函数是为了让测试能用临时目录构造最小 dist，
    不依赖真实前端构建产物（frontend/dist 被 gitignore，全新环境下安全用例不能整组跳过）。
    """
    if not dist_dir.is_dir():
        return False
    assets_dir = dist_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # 未匹配的 /api 路径仍返回 404，不回退成页面
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404, detail="Not Found")
        # 静态文件原样返回；路径必须解析后仍落在 dist 内（防 ../ 穿越读到 .env 等文件）
        candidate = (dist_dir / full_path).resolve()
        if full_path and candidate.is_relative_to(dist_dir) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist_dir / "index.html")

    return True


mount_spa(app, DIST_DIR)
