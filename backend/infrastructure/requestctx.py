# -*- coding: utf-8 -*-
"""request_id 贯通（修复方案 §11）：contextvars 传递。

request_id 中间件（main.py）在进入路由前 set 本模块的 ContextVar；
下游任意深度（LLM 路由、幂等协调器、操作日志）用 current_request_id() 取同一 id，
让一次请求产生的 LLM 调用日志与操作记录能按 request_id 串起来排障。

注意反向不传播：端点内部 set 的值在 call_next 返回后不可见——本模块只用于下行传递。
"""
from contextvars import ContextVar
from typing import Optional

request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def current_request_id() -> Optional[str]:
    """当前请求的 request_id；无请求上下文（启动清理/脚本/直连 Agent）时为 None。"""
    return request_id_var.get()
