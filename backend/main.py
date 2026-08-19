# -*- coding: utf-8 -*-
"""FastAPI 入口：uvicorn main:app --workers 1"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import assistant, bank, health, home, llm, notes, sessions, settings, stats
from database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时建表
    init_db()
    yield


app = FastAPI(title="程序员八股背诵 Agent", lifespan=lifespan)

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
app.include_router(assistant.router, prefix="/api")
app.include_router(notes.router, prefix="/api")

# 生产模式：托管前端构建产物（frontend/dist），SPA 路由回退到 index.html
# 开发模式不存在 dist 时跳过，走 Vite dev server + /api 代理
DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if DIST_DIR.is_dir():
    assets_dir = DIST_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # 未匹配的 /api 路径仍返回 404，不回退成页面
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404, detail="Not Found")
        # 静态文件原样返回；路径必须解析后仍落在 dist 内（防 ../ 穿越读到 .env 等文件）
        candidate = (DIST_DIR / full_path).resolve()
        if full_path and candidate.is_relative_to(DIST_DIR) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST_DIR / "index.html")
