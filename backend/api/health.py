# -*- coding: utf-8 -*-
"""健康检查接口。"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
