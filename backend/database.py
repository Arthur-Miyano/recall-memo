# -*- coding: utf-8 -*-
"""数据库引擎与初始化。"""
from sqlmodel import SQLModel, create_engine

from config import settings

# check_same_thread=False：允许 FastAPI 多线程共用 SQLite 连接（单 worker 部署）
engine = create_engine(settings.database_url, echo=False, connect_args={"check_same_thread": False})


def init_db() -> None:
    """建表（若不存在）。需先导入 models 以注册表定义。"""
    import models  # noqa: F401  确保所有表已注册到 metadata

    SQLModel.metadata.create_all(engine)
