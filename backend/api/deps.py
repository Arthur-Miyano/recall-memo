# -*- coding: utf-8 -*-
"""API 公共依赖：数据库会话等（各 router 统一从这里 import，不再各自重复定义）。"""
from sqlmodel import Session as DBSession

from database import engine


def get_db():
    """每个请求一个 SQLModel Session（单 worker + SQLite，随请求关闭）。"""
    with DBSession(engine) as db:
        yield db
