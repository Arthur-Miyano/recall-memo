# -*- coding: utf-8 -*-
"""API 路由包：统一 re-export 全部 router 模块，main.py 一把导入。"""
from . import assistant, bank, health, home, llm, sessions, settings, stats

__all__ = ["assistant", "bank", "health", "home", "llm", "sessions", "settings", "stats"]
