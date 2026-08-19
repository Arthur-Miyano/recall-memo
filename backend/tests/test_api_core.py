# -*- coding: utf-8 -*-
"""API 覆盖（一）：health / home.summary（含动态技术栈选项）/ bank.overview / bank.focus / bank.questions 删除。

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

    def test_stack_options_dynamic_and_object_shaped(self, client):
        """技术栈选项按题库实际 stack 动态生成，形状 [{value, label}]，外加混合。"""
        _seed(client, 2, stack="python")
        _seed(client, 1, stack="go")
        data = client.get("/api/home/summary").json()

        expected = [
            {"value": "go", "label": "Go"},
            {"value": "python", "label": "Python"},
            {"value": "mixed", "label": "混合"},
        ]
        for name in ("记忆训练", "面试模拟"):
            drawer = next(d for d in data["drawers"] if d["name"] == name)
            group = drawer["optGroups"][0]
            assert group["label"] == "技术栈"
            assert group["options"] == expected, f"{name} 抽屉的技术栈选项应与题库一致"
            assert group["on"] == len(expected) - 1, "默认选中最后一项（混合）"
            assert "keys" not in group, "下标耦合的 keys 字段应已移除"

    def test_stack_options_empty_bank_only_mixed(self, client):
        """空题库时至少返回 mixed 一个选项。"""
        data = client.get("/api/home/summary").json()
        for name in ("记忆训练", "面试模拟"):
            drawer = next(d for d in data["drawers"] if d["name"] == name)
            assert drawer["optGroups"][0]["options"] == [{"value": "mixed", "label": "混合"}]


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


class TestBankDeleteQuestion:
    def test_delete_cascades_related_data(self, client, db, seed_questions):
        from sqlmodel import select

        from models import Question, QuestionFocus, QuestionGroup, Record, RetryQueueItem, Session

        q1, q2 = seed_questions(2)
        q1_id, q2_id = q1.id, q2.id
        # 关联数据：q1 的答题记录 / 重点标记 / 待补答；q2 的答题记录（应保留）
        db.add(Record(session_id=1, question_id=q1_id, score_total=40.0))
        db.add(Record(session_id=1, question_id=q2_id, score_total=90.0))
        db.add(QuestionFocus(question_id=q1_id))
        db.add(RetryQueueItem(question_id=q1_id, source="interview"))
        # 追问组：双人组（删 q1 后剩 q2）+ 单人组（删 q1 后空组连组删）
        db.add(QuestionGroup(name="双人组", question_ids=[q1_id, q2_id]))
        db.add(QuestionGroup(name="单人组", question_ids=[q1_id]))
        # 历史会话引用 q1
        db.add(Session(mode="interview", question_ids=[q1_id, q2_id],
                       quiz_order=[q2_id, q1_id], current_question_id=q1_id))
        db.commit()

        resp = client.delete(f"/api/bank/questions/{q1_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True and body["deleted"] == q1_id
        assert body["removed_records"] == 1
        assert body["removed_focus"] is True
        assert body["removed_retry"] is True
        assert body["removed_groups"] == 1
        assert body["touched_sessions"] == 1

        # 结束本 session 的旧事务快照，否则看不到另一个连接（接口侧）提交的删除
        db.rollback()

        # 题目本体与关联全部清干净
        assert db.get(Question, q1_id) is None
        assert db.get(Question, q2_id) is not None
        remaining = db.exec(select(Record)).all()
        assert [r.question_id for r in remaining] == [q2_id]
        assert db.exec(select(QuestionFocus)).all() == []
        assert db.exec(select(RetryQueueItem)).all() == []

        # 组内其他题不受影响，空组被删
        groups = db.exec(select(QuestionGroup)).all()
        assert len(groups) == 1
        assert groups[0].name == "双人组" and groups[0].question_ids == [q2_id]

        # 会话里的引用被摘除，会话本身保留
        session = db.exec(select(Session)).one()
        assert session.question_ids == [q2_id]
        assert session.quiz_order == [q2_id]
        assert session.current_question_id is None

        # 再删一次：404
        resp = client.delete(f"/api/bank/questions/{q1_id}")
        assert resp.status_code == 404

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.delete("/api/bank/questions/9999")
        assert resp.status_code == 404
