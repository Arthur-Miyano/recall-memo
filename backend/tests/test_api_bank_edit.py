# -*- coding: utf-8 -*-
"""题库编辑接口覆盖：PATCH /api/bank/questions/{id} 与 POST /api/bank/questions/migrate。

全部走 TestClient 真实路由 + 临时库。
"""


class TestPatchQuestion:
    def test_patch_tech_stack_with_alias(self, client, seed_questions):
        """改技术栈：别名归一化（Golang → go），返回完整题目字段。"""
        q = seed_questions(1)[0]
        resp = client.patch(f"/api/bank/questions/{q.id}", json={"tech_stack": "Golang"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["tech_stack"] == "go"
        assert body["id"] == q.id and body["stem"] == q.stem
        assert set(body) >= {"id", "stem", "answer", "tech_stack", "difficulty",
                             "keywords", "tags", "variants", "created_at"}

    def test_patch_tech_stack_free_named(self, client, seed_questions):
        """改技术栈：白名单外自由命名原样保留（rust）。"""
        q = seed_questions(1)[0]
        resp = client.patch(f"/api/bank/questions/{q.id}", json={"tech_stack": "Rust"})
        assert resp.status_code == 200
        assert resp.json()["tech_stack"] == "rust"

    def test_patch_stem_and_answer(self, client, seed_questions, db):
        """改题干/答案/难度/关键词/标签。"""
        q = seed_questions(1)[0]
        resp = client.patch(f"/api/bank/questions/{q.id}", json={
            "stem": "  新的题干是什么？  ",
            "answer": "新的标准答案。",
            "difficulty": "hard",
            "keywords": ["新关键词"],
            "tags": ["go", "新知识点"],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["stem"] == "新的题干是什么？"  # 题干入库前去空白
        assert body["answer"] == "新的标准答案。"
        assert body["difficulty"] == "hard"
        assert body["keywords"] == ["新关键词"]
        assert body["tags"] == ["go", "新知识点"]

        db.rollback()  # 结束本 session 旧事务快照，读接口侧提交的结果
        db.refresh(q)
        assert q.stem == "新的题干是什么？"

    def test_patch_empty_body_400(self, client, seed_questions):
        """空请求体 / 只给空 tech_stack（视为不改）：400。"""
        q = seed_questions(1)[0]
        assert client.patch(f"/api/bank/questions/{q.id}", json={}).status_code == 400
        assert client.patch(f"/api/bank/questions/{q.id}", json={"tech_stack": ""}).status_code == 400

    def test_patch_unrecognizable_stack_400(self, client, seed_questions):
        """非空但清洗不出有效 slug 的技术栈：400。"""
        q = seed_questions(1)[0]
        resp = client.patch(f"/api/bank/questions/{q.id}", json={"tech_stack": "！！！"})
        assert resp.status_code == 400

    def test_patch_nonexistent_404(self, client):
        assert client.patch("/api/bank/questions/9999", json={"stem": "x"}).status_code == 404


class TestMigrateQuestions:
    def test_migrate_success(self, client, seed_questions, db):
        """批量迁移成功：两题迁到 go，响应带 moved/missing/to_stack。"""
        qs = seed_questions(3)
        ids = [qs[0].id, qs[1].id]
        resp = client.post("/api/bank/questions/migrate",
                           json={"question_ids": ids, "to_stack": "Golang"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "moved": 2, "missing": [], "to_stack": "go"}

        db.rollback()
        for q in qs:
            db.refresh(q)
        assert qs[0].tech_stack == "go" and qs[1].tech_stack == "go"
        assert qs[2].tech_stack == "python", "未选中的题不受影响"

    def test_migrate_partial_missing_ids(self, client, seed_questions):
        """不存在的 id 忽略但在 missing 里列出。"""
        q = seed_questions(1)[0]
        resp = client.post("/api/bank/questions/migrate",
                           json={"question_ids": [q.id, 9998, 9999], "to_stack": "rust"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True and body["moved"] == 1
        assert body["missing"] == [9998, 9999]
        assert body["to_stack"] == "rust"

    def test_migrate_empty_ids_400(self, client):
        resp = client.post("/api/bank/questions/migrate",
                           json={"question_ids": [], "to_stack": "go"})
        assert resp.status_code == 400

    def test_migrate_bad_stack_400(self, client, seed_questions):
        """目标栈无法识别（空串或清洗后为空）：400。"""
        q = seed_questions(1)[0]
        for bad in ("", "！！！"):
            resp = client.post("/api/bank/questions/migrate",
                               json={"question_ids": [q.id], "to_stack": bad})
            assert resp.status_code == 400

    def test_migrate_then_options_reflect_new_stack(self, client, seed_questions):
        """迁移后 home 抽屉的技术栈选项跟着题库变化。"""
        q = seed_questions(1)[0]
        client.post("/api/bank/questions/migrate",
                    json={"question_ids": [q.id], "to_stack": "go"})
        data = client.get("/api/home/summary").json()
        options = data["drawers"][1]["optGroups"][0]["options"]
        assert {"value": "go", "label": "Go"} in options
        assert {"value": "python", "label": "Python"} not in options
