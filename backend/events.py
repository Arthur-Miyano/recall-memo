# -*- coding: utf-8 -*-
"""进程内事件总线：Agent 活跃事件的 pub/sub，供 /api/events SSE 端点广播。

单进程单用户工具：订阅者为一组 asyncio.Queue（每个 SSE 连接一个），publish 非阻塞投递。
事件格式：{"agent": "面试官", "label": "提问中…", "ts": 1712345678.9}
"""
import asyncio
import time

# 单个订阅队列容量：SSE 客户端卡住读不动时丢弃事件，而不是撑爆内存或阻塞生产端
_QUEUE_MAXSIZE = 100

# 订阅者集合：SSE 连接 subscribe 加入，断开时 unsubscribe 移除
_subscribers: set[asyncio.Queue] = set()


def publish(agent: str, label: str) -> None:
    """广播一条 Agent 活跃事件。绝不抛异常：埋点不允许影响主流程。"""
    try:
        event = {"agent": str(agent), "label": str(label), "ts": time.time()}
        for queue in list(_subscribers):
            try:
                queue.put_nowait(event)
            except Exception:
                continue  # 该订阅者队列满/已关闭：丢弃这条，不拖累其他订阅者
    except Exception:
        pass


def subscribe() -> asyncio.Queue:
    """注册一个订阅者队列（由 SSE 连接持有，断开时必须 unsubscribe）。"""
    queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
    _subscribers.add(queue)
    return queue


def unsubscribe(queue: asyncio.Queue) -> None:
    """取消订阅（SSE 连接断开清理，防泄漏）。"""
    _subscribers.discard(queue)


def subscriber_count() -> int:
    """当前订阅数（测试与调试用）。"""
    return len(_subscribers)
