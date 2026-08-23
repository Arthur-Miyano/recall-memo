# -*- coding: utf-8 -*-
"""健康检查接口。"""
from fastapi import APIRouter

from infrastructure.localguard import LOCAL_TOKEN

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    # local_token：本地令牌下发通道（§10）。跨域网页受 SOP/CORS 限制读不到本响应；
    # 令牌不落盘、不进日志（uvicorn 访问日志不含响应体）
    return {"status": "ok", "local_token": LOCAL_TOKEN}
