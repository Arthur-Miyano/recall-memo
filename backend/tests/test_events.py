# -*- coding: utf-8 -*-
"""活跃 Agent 事件链路的测试：进程内总线（events.py）+ SSE 端点（/api/events）+ 业务埋点。

注意：
- SSE 端点不在 TestClient 里起真长连接（无限流会让响应读取永远阻塞）；
  直接调路由函数拿 StreamingResponse，消费其 body_iterator 异步生成器（带 wait_for 超时兜底）。
- 业务埋点用 monkeypatch 替换 events.publish 做断言，不起真 SSE 连接等业务事件
  （跨线程向 asyncio.Queue 投递不可靠）。
"""
import asyncio
import json

import pytest

import events
from api import events as events_api


@pytest.fixture(autouse=True)
def clean_subscribers():
    """每个用例后清空订阅者集合，防止用例间泄漏。"""
    yield
    events._subscribers.clear()


# ----------------------------------------------------------------------
# 事件总线：publish / subscribe / unsubscribe
# ----------------------------------------------------------------------

def test_publish_delivers_to_subscriber():
    q = events.subscribe()
    events.publish("面试官", "提问中…")
    event = q.get_nowait()
    assert event["agent"] == "面试官"
    assert event["label"] == "提问中…"
    assert isinstance(event["ts"], float)


def test_publish_fans_out_to_all_subscribers():
    q1, q2 = events.subscribe(), events.subscribe()
    events.publish("评分", "判分中…")
    assert q1.get_nowait()["agent"] == "评分"
    assert q2.get_nowait()["agent"] == "评分"


def test_unsubscribe_stops_delivery():
    q = events.subscribe()
    assert events.subscriber_count() == 1
    events.unsubscribe(q)
    assert events.subscriber_count() == 0
    events.publish("评分", "判分中…")
    assert q.empty()


def test_publish_with_no_subscribers_does_not_raise():
    events.publish("总控", "建场中…")


def test_publish_swallows_broken_subscriber():
    """订阅者 put_nowait 抛异常时 publish 不传播，且不影响其他订阅者。"""

    class BrokenQueue:
        def put_nowait(self, item):
            raise RuntimeError("boom")

    events._subscribers.add(BrokenQueue())
    q = events.subscribe()
    events.publish("总控", "建场中…")  # 不抛异常
    assert q.get_nowait()["agent"] == "总控"


async def test_subscribe_consume_in_loop():
    """同一事件循环内 publish → 订阅队列可 await 消费（SSE 生产端路径）。"""
    q = events.subscribe()
    events.publish("智能助理", "对话中…")
    event = await asyncio.wait_for(q.get(), timeout=1)
    assert event["agent"] == "智能助理"
    assert event["label"] == "对话中…"


# ----------------------------------------------------------------------
# SSE 端点
# 注意：不在 TestClient 里起真 SSE 长连接（无限流会让 iter_lines 永远阻塞）；
# 直接调路由函数拿 StreamingResponse，消费其 body_iterator 异步生成器。
# ----------------------------------------------------------------------

async def test_sse_endpoint_streams_published_event(monkeypatch):
    """GET /api/events：publish 的事件以 `data: {json}\n\n` 帧流出。"""
    monkeypatch.setattr(events_api, "HEARTBEAT_SECONDS", 60)  # 排除心跳干扰
    resp = await events_api.stream_events()
    assert resp.media_type == "text/event-stream"
    assert resp.headers["Cache-Control"] == "no-cache"
    assert events.subscriber_count() == 1
    stream = resp.body_iterator
    try:
        events.publish("面试官", "提问中…")
        chunk = await asyncio.wait_for(anext(stream), timeout=2)
        assert chunk.startswith("data: ")
        payload = json.loads(chunk[len("data: "):])
        assert payload["agent"] == "面试官"
        assert payload["label"] == "提问中…"
        assert isinstance(payload["ts"], float)
    finally:
        await stream.aclose()


async def test_sse_heartbeat_and_disconnect_cleanup(monkeypatch):
    """无事件时按心跳间隔发注释行；关闭流（客户端断开）后退订清理。"""
    monkeypatch.setattr(events_api, "HEARTBEAT_SECONDS", 0.05)
    resp = await events_api.stream_events()
    stream = resp.body_iterator
    chunk = await asyncio.wait_for(anext(stream), timeout=2)
    assert chunk.startswith(":")  # SSE 注释行（心跳）
    assert events.subscriber_count() == 1
    await stream.aclose()  # 等价于客户端断开：生成器 finally 退订
    assert events.subscriber_count() == 0


# ----------------------------------------------------------------------
# 业务埋点：真实业务流程触发事件（spy publish，不起真 SSE 连接）
# ----------------------------------------------------------------------

@pytest.fixture()
def published(monkeypatch):
    """记录所有 publish 调用的间谍：返回 [(agent, label), ...]。"""
    seen: list[tuple[str, str]] = []
    monkeypatch.setattr(events, "publish", lambda agent, label: seen.append((agent, label)))
    return seen


def test_create_session_publishes_strategy_event(client, seed_questions, published):
    """建场（记忆训练）走策略抽题：应广播策略 Agent 的活跃事件。"""
    seed_questions(3)
    resp = client.post("/api/sessions", json={"mode": "memorize", "stack": "python", "count": 3})
    assert resp.status_code == 200
    assert any(agent == "策略" and "抽题" in label for agent, label in published)


def test_quiz_answer_publishes_grader_event(client, seed_questions, published):
    """答题流程：评分 Agent 判分事件被广播。"""
    seed_questions(3)
    session_id = client.post(
        "/api/sessions", json={"mode": "memorize", "stack": "python", "count": 3}
    ).json()["session_id"]
    resp = client.post(f"/api/sessions/{session_id}/start_quiz")
    assert resp.status_code == 200
    assert any(agent == "面试官" for agent, _ in published)
    published.clear()
    resp = client.post(f"/api/sessions/{session_id}/answer", json={"answer": "这是我的回答"})
    assert resp.status_code == 200
    assert any(agent == "评分" and "判分" in label for agent, label in published)


def test_assistant_chat_publishes_events(client, published):
    """助手对话：开始与完成各广播一次智能助理事件。"""
    resp = client.post("/api/assistant/chat", json={"message": "我今天背得怎么样？"})
    assert resp.status_code == 200
    labels = [label for agent, label in published if agent == "智能助理"]
    assert "对话中…" in labels
    assert "答复完成" in labels
