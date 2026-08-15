# -*- coding: utf-8 -*-
"""pytest 公共夹具：临时 SQLite 库 + 假 LLM。

两条红线：
1. 所有测试只使用 tmp_path 下的临时 SQLite，绝不触碰 data/bagu.db 真实库；
   （导入 database 模块只会 create_engine，不会连接/建文件，真实库文件不会被创建或修改。）
2. FakeLLM 接管全局 llm_router.chat，按 system prompt 内容分发可编程的假响应，
   绝不产生真实网络请求。
"""
import json
import re
from pathlib import Path

import pytest
from sqlmodel import SQLModel, create_engine
from sqlmodel import Session as DBSession

import models  # noqa: F401  注册全部表定义到 metadata
import database


# ----------------------------------------------------------------------
# 临时数据库
# ----------------------------------------------------------------------

@pytest.fixture()
def test_engine(tmp_path, monkeypatch):
    """临时 SQLite 引擎：建表后替换 database.engine（init_db / 维护函数均走该引擎）。"""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    return engine


@pytest.fixture()
def db(test_engine):
    """直读数据库的 SQLModel Session（用于 arrange/assert 与直接调用 Agent）。"""
    with DBSession(test_engine) as session:
        yield session


@pytest.fixture()
def seed_questions(db):
    """插入题目的工厂：make(n, stack=..., answer=...) -> list[Question]。"""
    from models import Question

    def make(n: int, stack: str = "python", **kwargs) -> list[Question]:
        questions = []
        for i in range(n):
            q = Question(
                stem=kwargs.get("stem", f"测试题干 {stack}-{i}：这是什么？"),
                answer=kwargs.get("answer", f"这是 {stack}-{i} 的标准答案，包含若干关键技术点。"),
                tech_stack=stack,
                keywords=kwargs.get("keywords", [f"kw{i}"]),
                tags=kwargs.get("tags", [stack, "测试知识点"]),
            )
            db.add(q)
            questions.append(q)
        db.commit()
        for q in questions:
            db.refresh(q)
        return questions

    return make


# ----------------------------------------------------------------------
# 假 LLM：按 system prompt 内容分发，测试可编程各项返回值
# ----------------------------------------------------------------------

class FakeLLM:
    """可编程假 LLM。属性即响应内容，测试可随意改写。"""

    def __init__(self) -> None:
        # 评分：默认高分通过
        self.score: dict = {
            "accuracy": 80, "logic": 80, "naturalness": 80,
            "missed_points": [], "comment": "（假评分）", "annotated_answer": None,
        }
        # 评分原始输出（非 None 时优先于 self.score，用于构造围栏/坏 JSON）
        self.score_raw: str | None = None
        # 面试官变体：返回 prefix + 原题干
        self.variant_prefix: str = "（变体提问）"
        # 规则解析兜底提取 / PDF 强制提取：返回的题目数组
        self.extract_items: list[dict] = []
        self.pdf_items: list[dict] = []
        # 补全：None 表示按 payload 的 index 自动补 answer/tech_stack
        self.enrich_items: list[dict] | None = None
        # 复盘分析
        self.review_analysis: dict = {
            "weak_points": ["假薄弱点"],
            "misunderstandings": "未发现明显理解偏差",
            "reciting_notes": "无明显背诵痕迹",
            "overall": "（假整体点评）",
        }
        # 助理对话回复
        self.chat_reply: str = "（假 LLM 回复）"
        # 调用记录：[system_prompt 前 40 字]（分发关键字最远出现在第 30 字左右）
        self.calls: list[str] = []

    async def chat(self, messages, **kwargs):
        system = messages[0]["content"] if messages else ""
        user = messages[-1]["content"] if messages else ""
        self.calls.append(system[:40])

        if "评分专家" in system:
            return "fake", self.score_raw if self.score_raw is not None else json.dumps(self.score, ensure_ascii=False)
        if "改写成自然的面试官口吻" in system:
            stem = ""
            m = re.search(r"【标准题干】(.+?)\n", user)
            if m:
                stem = m.group(1).strip()
            return "fake", f"{self.variant_prefix}{stem}"
        if "整理成结构化面试题" in system:
            return "fake", json.dumps(self.extract_items, ensure_ascii=False)
        if "提取真正的面试题" in system:
            return "fake", json.dumps(self.pdf_items, ensure_ascii=False)
        if "补全缺失字段" in system:
            if self.enrich_items is not None:
                return "fake", json.dumps(self.enrich_items, ensure_ascii=False)
            # 默认：按 payload 中出现的 index 逐个补全 answer / tech_stack
            items = [
                {
                    "index": int(i),
                    "answer": "（假补全答案）这是 LLM 生成的标准答案。",
                    "tech_stack": "python",
                    "knowledge_point": "假知识点",
                    "keywords": ["假关键词"],
                    "difficulty": "medium",
                }
                for i in re.findall(r'"index":\s*(\d+)', user)
            ]
            return "fake", json.dumps(items, ensure_ascii=False)
        if "终局复盘分析" in system:
            return "fake", json.dumps(self.review_analysis, ensure_ascii=False)
        if "记忆助手" in system:
            return "fake", self.chat_reply
        return "fake", self.chat_reply


@pytest.fixture()
def fake_llm(monkeypatch):
    """把全局 llm_router.chat 替换为 FakeLLM（实例属性遮蔽，所有 Agent 共用）。"""
    from llm import llm_router

    fake = FakeLLM()
    monkeypatch.setattr(llm_router, "chat", fake.chat)
    return fake


@pytest.fixture()
def fake_router(fake_llm):
    """给直接实例化的 Agent 用的伪 router（仅需 .chat）。"""
    from types import SimpleNamespace

    return SimpleNamespace(chat=fake_llm.chat)


# ----------------------------------------------------------------------
# TestClient：真实路由 + 假 LLM + 临时库
# ----------------------------------------------------------------------

@pytest.fixture()
def client(test_engine, fake_llm):
    """FastAPI TestClient：get_db 依赖重定向到临时库。

    进入上下文时跑 lifespan -> init_db()，此时 database.engine 已被替换为临时引擎，
    因此建表/迁移/索引/孤儿会话清理全部落在临时库上。
    """
    from fastapi.testclient import TestClient

    from api.deps import get_db
    from main import app

    def override_get_db():
        with DBSession(test_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
