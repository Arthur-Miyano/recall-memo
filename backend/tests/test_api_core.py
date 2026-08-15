# -*- coding: utf-8 -*-
"""API 覆盖（一）：health / home.summary / bank.overview / bank.focus。

全部走 TestClient 真实路由 + 临时库，不依赖 8000 端口运行中的服务。
"""
import re


def _seed(client, n=3, stack="python"):
    """通过导入接口快速塞题（JSON 输入不经 LLM 提取）。"""
    import json

    payload = json.dumps(
        [
            {
                "question": f"{stack} 题 {i}：这是什么？",
                "answer": f"{stack} 题 {i} 的标准答案。",
                "tech_stack": stack,
                "knowledge_point": f"知识点{i % 2}",
            }
            for i in range(n)
        ],
        ensure_ascii=False,
    )
    resp = client.post("/api/bank/import", json={"text": payload, "dedupe": False})
    assert resp.status_code == 200
    return resp.json()


class TestHealth:
    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestHomeSummary:
    def test_shape_and_date_text(self, client):
        _seed(client, 3)
        resp = client.get("/api/home/summary")
        assert resp.status_code == 200
        data = resp.json()

        # 日期文案：YYYY.MM.DD — 周三字母缩写
        assert re.fullmatch(r"\d{4}\.\d{2}\.\d{2} — (MON|TUE|WED|THU|FRI|SAT|SUN)", data["date"])
        assert "题库 3 题" in data["sub"]
        assert "已覆盖 0 题" in data["sub"]

        drawers = data["drawers"]
        assert len(drawers) == 3
        names = [d["name"] for d in drawers]
        assert names == ["记忆训练", "面试模拟", "回忆模式"]

        memorize = drawers[0]
        stats = {s["k"]: s["v"] for s in memorize["stats"]}
        assert stats["未背题数"] == "3"
        assert stats["待补答"] == "0"
        assert stats["上次训练"] == "—", "从未训练应显示 —"

    def test_empty_bank(self, client):
        resp = client.get("/api/home/summary")
        assert resp.status_code == 200
        assert "题库 0 题" in resp.json()["sub"]


class TestBankOverview:
    def test_empty(self, client):
        data = client.get("/api/bank/overview").json()
        assert data == {"done": 0, "total": 0, "stacks": []}

    def test_grouped_by_stack_and_knowledge_point(self, client):
        _seed(client, 3)
        data = client.get("/api/bank/overview").json()
        assert data["total"] == 3
        assert data["done"] == 0

        stack = data["stacks"][0]
        assert stack["key"] == "python"
        assert stack["name"] == "Python"
        assert stack["total"] == 3
        # 知识点分组：知识点0（2 题） + 知识点1（1 题）
        groups = {g["name"]: g for g in stack["groups"]}
        assert set(groups) == {"知识点0", "知识点1"}
        cell = groups["知识点0"]["cells"][0]
        assert cell["status"] == "todo"
        assert cell["retry"] is False
        assert cell["focused"] is False


class TestBankFocus:
    def test_focus_and_unfocus_group(self, client):
        _seed(client, 3)
        # 圈选 知识点0 组（2 题）
        resp = client.post("/api/bank/focus", json={"stack": "python", "group": "知识点0", "focused": True})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "changed": 2, "starred": True}

        overview = client.get("/api/bank/overview").json()
        groups = {g["name"]: g for g in overview["stacks"][0]["groups"]}
        assert groups["知识点0"]["starred"] is True
        assert all(c["focused"] for c in groups["知识点0"]["cells"])
        assert groups["知识点1"]["starred"] is False

        # 重复圈选：changed=0（幂等）
        resp = client.post("/api/bank/focus", json={"stack": "python", "group": "知识点0", "focused": True})
        assert resp.json()["changed"] == 0

        # 取消
        resp = client.post("/api/bank/focus", json={"stack": "python", "group": "知识点0", "focused": False})
        assert resp.json() == {"ok": True, "changed": 2, "starred": False}
        overview = client.get("/api/bank/overview").json()
        cells = [c for g in overview["stacks"][0]["groups"] for c in g["cells"]]
        assert not any(c["focused"] for c in cells)

    def test_focus_nonexistent_group(self, client):
        _seed(client, 2)
        resp = client.post("/api/bank/focus", json={"stack": "python", "group": "不存在", "focused": True})
        body = resp.json()
        assert body["ok"] is False
        assert body["changed"] == 0
