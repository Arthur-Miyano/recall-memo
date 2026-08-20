# -*- coding: utf-8 -*-
"""SSE 事件流：GET /events —— 实时广播进程内 Agent 活跃事件（见根目录 events 总线）。

协议：每条事件 `data: {"agent": "...", "label": "...", "ts": ...}\n\n`；
无事件时每 HEARTBEAT_SECONDS 秒发一行注释心跳（`: heartbeat`）防中间代理断连。
客户端断开时退订清理，防订阅泄漏。
"""
import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

import events

router = APIRouter(tags=["events"])

# 心跳间隔（秒）：过频浪费带宽，过慢会被中间代理判为死连接而断开
HEARTBEAT_SECONDS = 15.0


async def _event_stream(queue: asyncio.Queue):
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"
                continue
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    finally:
        # 客户端断开（生成器被关闭）时退订，防订阅泄漏
        events.unsubscribe(queue)


@router.get("/events")
async def stream_events():
    """订阅 Agent 活跃事件流（text/event-stream，长连接保持不断）。"""
    queue = events.subscribe()
    return StreamingResponse(
        _event_stream(queue),
        media_type="text/event-stream",
        # no-cache 防缓存；X-Accel-Buffering 防 nginx 类代理缓冲掉 SSE 流
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
