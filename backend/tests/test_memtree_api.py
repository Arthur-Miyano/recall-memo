# -*- coding: utf-8 -*-
"""记忆树提取接口测试（/api/memtree）：分组统计 + 后台生成任务。

后台协程在 TestClient portal 的事件循环里持续推进，测试用轮询等待任务结束
（与 test_api_assistant_import.py 的 import-jobs 用例同一手法）。
FakeLLM 对记忆树批量调用落到默认分支（chat_reply），测试把它编程为合法树数组。
"""
import json
import time

import pytest
from sqlmodel import select

from application.memtree_jobs import MEMTREE_JOBS
from models import Question


@pytest.fixture(autouse=True)
def _clean_memtree_jobs():
    """任务注册表是模块级内存态：每个用例前后清空，避免跨用例污染（latest 断言）。"""
    MEMTREE_JOBS.clear()
    yield
    MEMTREE_JOBS.clear()


_SAMPLE_TREE = {
    "title": "答案大纲",
    "note": "",
    "children": [{"title": "要点一", "note": "展开说明", "children": []}],
}


def _wait_done(client, job_id: str, rounds: int = 100) -> dict:
    """轮询任务直到结束。"""
    for _ in range(rounds):
        j = client.get(f"/api/memtree/jobs/{job_id}").json()
        if j["status"] != "running":
            return j
        time.sleep(0.05)
    raise AssertionError(f"任务 {job_id} 长时间未结束：{j}")


class TestMemtreeStatus:
    def test_status_counts_by_stack(self, client, db, seed_questions):
        """按技术栈分组统计：有树/缺树计数正确，外加总计。"""
        qs = seed_questions(3, stack="python") + seed_questions(2, stack="agent")
        qs[0].memory_tree = _SAMPLE_TREE
        qs[3].memory_tree = _SAMPLE_TREE
        db.add(qs[0])
        db.add(qs[3])
        db.commit()

        d = client.get("/api/memtree/status").json()
        by_stack = {g["tech_stack"]: g for g in d["stacks"]}
        assert by_stack["python"] == {"tech_stack": "python", "total": 3, "with_tree": 1, "missing": 2}
        assert by_stack["agent"] == {"tech_stack": "agent", "total": 2, "with_tree": 1, "missing": 1}
        assert d["total"] == {"tech_stack": "全部", "total": 5, "with_tree": 2, "missing": 3}

    def test_status_empty_bank(self, client):
        d = client.get("/api/memtree/status").json()
        assert d["stacks"] == []
        assert d["total"]["total"] == 0


class TestMemtreeJobs:
    def test_no_missing_returns_400(self, client, db, seed_questions):
        """范围内没有缺树的题：400。"""
        qs = seed_questions(2)
        for q in qs:
            q.memory_tree = _SAMPLE_TREE
            db.add(q)
        db.commit()
        resp = client.post("/api/memtree/jobs", json={})
        assert resp.status_code == 400
        assert "没有需要生成的题目" in resp.json()["detail"]

    def test_empty_bank_returns_400(self, client):
        assert client.post("/api/memtree/jobs", json={}).status_code == 400

    def test_job_runs_to_done(self, client, db, seed_questions, fake_llm):
        """完整流程：只补缺树 → 202 → 轮询到 done → 题目挂上树 → latest 可重挂。"""
        qs = seed_questions(3, stack="python") + seed_questions(2, stack="agent")
        qs[0].memory_tree = _SAMPLE_TREE  # 已有树：默认模式不该动它
        db.add(qs[0])
        db.commit()
        missing = [q for q in qs if q.id != qs[0].id]
        fake_llm.chat_reply = json.dumps(
            [{"id": q.id, "tree": _SAMPLE_TREE} for q in missing], ensure_ascii=False
        )

        resp = client.post("/api/memtree/jobs", json={})
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        j = _wait_done(client, job_id)
        assert j["status"] == "done"
        assert j["result"] == {"done": 4, "failed": 0, "failed_ids": []}

        db.expire_all()  # 后台任务在另一个 session 写库：清身份映射缓存再断言
        for q in missing:
            assert db.get(Question, q.id).memory_tree == _SAMPLE_TREE
        # 已有树的题不在任务范围内
        assert db.get(Question, qs[0].id).memory_tree == _SAMPLE_TREE
        # JSON 列缺树判定与接口一致走 Python 侧（'null' 字符串不算有树）
        remaining = [q for q in db.exec(select(Question)).all() if q.memory_tree is None]
        assert remaining == []

        latest = client.get("/api/memtree/jobs/latest").json()["job"]
        assert latest["id"] == job_id
        assert latest["status"] == "done"

    def test_job_batch_failure_recorded(self, client, db, seed_questions, fake_llm):
        """整批 LLM 失败（输出无法解析）：任务仍 done，全部记失败，不挂树。"""
        seed_questions(2)
        resp = client.post("/api/memtree/jobs", json={})
        assert resp.status_code == 202
        j = _wait_done(client, resp.json()["job_id"])
        assert j["status"] == "done"
        assert j["result"]["done"] == 0
        assert j["result"]["failed"] == 2
        assert len(j["result"]["failed_ids"]) == 2

    def test_job_stack_filter_and_regenerate(self, client, db, seed_questions, fake_llm):
        """stack 过滤 + regenerate=true：范围内全部题重新生成（含已有树的）。"""
        qs = seed_questions(2, stack="python") + seed_questions(1, stack="agent")
        for q in qs:
            q.memory_tree = _SAMPLE_TREE
            db.add(q)
        db.commit()
        fake_llm.chat_reply = json.dumps(
            [{"id": q.id, "tree": _SAMPLE_TREE} for q in qs[:2]], ensure_ascii=False
        )
        resp = client.post("/api/memtree/jobs", json={"stack": "python", "regenerate": True})
        assert resp.status_code == 202
        j = _wait_done(client, resp.json()["job_id"])
        assert j["status"] == "done"
        assert j["result"]["done"] == 2  # 只跑 python 栈的 2 题
        assert set(j["result"]["failed_ids"]) == set()

    def test_job_question_ids(self, client, db, seed_questions, fake_llm):
        """question_ids 优先：只跑指定的题。"""
        qs = seed_questions(3)
        fake_llm.chat_reply = json.dumps(
            [{"id": qs[1].id, "tree": _SAMPLE_TREE}], ensure_ascii=False
        )
        resp = client.post("/api/memtree/jobs", json={"question_ids": [qs[1].id]})
        assert resp.status_code == 202
        j = _wait_done(client, resp.json()["job_id"])
        assert j["result"]["done"] == 1

    def test_job_not_found(self, client):
        assert client.get("/api/memtree/jobs/nope").status_code == 404

    def test_latest_empty(self, client):
        assert client.get("/api/memtree/jobs/latest").json() == {"job": None}
