# -*- coding: utf-8 -*-
"""笔记接口覆盖：CRUD + 划句片段追加 + 404/校验。"""


class TestNotesCrud:
    def test_create_and_get(self, client):
        created = client.post("/api/notes", json={"title": "Agent 相关知识"}).json()
        assert created["title"] == "Agent 相关知识"
        assert created["content"] == ""

        got = client.get(f"/api/notes/{created['id']}").json()
        assert got["title"] == "Agent 相关知识"

    def test_create_blank_title_falls_back(self, client):
        created = client.post("/api/notes", json={"title": "   "}).json()
        assert created["title"] == "未命名笔记"

    def test_list_brief_ordered_by_updated_desc(self, client):
        a = client.post("/api/notes", json={"title": "A"}).json()
        b = client.post("/api/notes", json={"title": "B"}).json()
        data = client.get("/api/notes").json()
        assert data["count"] == 2
        assert [i["title"] for i in data["items"]] == ["B", "A"], "后建的排前面"
        assert "content" not in data["items"][0], "列表只回摘要"
        # 更新 A 后应排到最前
        client.put(f"/api/notes/{a['id']}", json={"content": "补充内容"})
        data = client.get("/api/notes").json()
        assert data["items"][0]["title"] == "A"
        assert data["items"][0]["excerpt"] == "补充内容"
        assert b["id"] != a["id"]

    def test_update_title_and_content(self, client):
        n = client.post("/api/notes", json={"title": "旧"}).json()
        updated = client.put(f"/api/notes/{n['id']}", json={"title": "新", "content": "正文"}).json()
        assert updated["title"] == "新"
        assert updated["content"] == "正文"
        assert updated["updated_at"] >= n["updated_at"]

    def test_delete(self, client):
        n = client.post("/api/notes", json={"title": "X"}).json()
        assert client.delete(f"/api/notes/{n['id']}").json() == {"ok": True}
        assert client.get(f"/api/notes/{n['id']}").status_code == 404

    def test_missing_note_404(self, client):
        assert client.get("/api/notes/999").status_code == 404
        assert client.put("/api/notes/999", json={"title": "x"}).status_code == 404
        assert client.delete("/api/notes/999").status_code == 404
        assert client.post("/api/notes/999/append", json={"text": "x"}).status_code == 404


class TestNoteAppend:
    def test_append_with_source(self, client):
        n = client.post("/api/notes", json={"title": "片段"}).json()
        updated = client.post(
            f"/api/notes/{n['id']}/append",
            json={"text": "能用 Workflow 不用 Agent", "source": "Agent 架构模式怎么选？"},
        ).json()
        assert updated["content"] == "> 能用 Workflow 不用 Agent\n—— Agent 架构模式怎么选？"

    def test_append_without_source_and_accumulate(self, client):
        n = client.post("/api/notes", json={"title": "片段"}).json()
        client.post(f"/api/notes/{n['id']}/append", json={"text": "第一句"})
        updated = client.post(f"/api/notes/{n['id']}/append", json={"text": "第二句"}).json()
        assert updated["content"] == "> 第一句\n\n> 第二句"

    def test_append_to_existing_content(self, client):
        n = client.post("/api/notes", json={"title": "笔记"}).json()
        client.put(f"/api/notes/{n['id']}", json={"content": "手写内容"})
        updated = client.post(f"/api/notes/{n['id']}/append", json={"text": "划句"}).json()
        assert updated["content"] == "手写内容\n\n> 划句"

    def test_append_blank_text_400(self, client):
        n = client.post("/api/notes", json={"title": "X"}).json()
        resp = client.post(f"/api/notes/{n['id']}/append", json={"text": "   "})
        assert resp.status_code == 400
