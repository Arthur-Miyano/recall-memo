# -*- coding: utf-8 -*-
"""FastAPI 入口：uvicorn main:app --workers 1"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import health, llm, sessions, stats
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
