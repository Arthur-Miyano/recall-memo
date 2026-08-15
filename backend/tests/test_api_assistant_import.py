# -*- coding: utf-8 -*-
"""API 覆盖（三）：assistant 对话 + 会话管理；bank/import 三条 LLM 路径。"""

# ---------------------------------------------------------------------------
# assistant
# ---------------------------------------------------------------------------

class TestAssistantApi:
    def test_chat_free_message_persisted(self, client, fake_llm):
        fake_llm.chat_reply = "你今天背了 2 题，继续保持。"
        resp = client.post("/api/assistant/chat", json={"message": "我今天背得怎么样？"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["reply"] == "你今天背了 2 题，继续保持。"
        assert body["session_id"], "应返回会话 id"
        assert body["thinking"], "应有 Agent 调用链描述"
        assert any("解析意图" in t for t in body["thinking"])

        # 落库验证：history 能查回这一问一答
        history = client.get("/api/assistant/history", params={"session_id": body["session_id"]}).json()
        roles = [m["role"] for m in history["messages"]]
        assert roles == ["user", "assistant"]
        assert history["messages"][0]["content"] == "我今天背得怎么样？"
        assert history["messages"][1]["thinking"] == body["thinking"]

    def test_chat_quick_command(self, client, fake_llm):
        resp = client.post("/api/assistant/chat", json={"quick": "today"})
        assert resp.status_code == 200
        assert resp.json()["reply"] == fake_llm.chat_reply

    def test_chat_validation_errors(self, client):
        # message 与 quick 都不给
        assert client.post("/api/assistant/chat", json={}).status_code == 400
        # 未知快捷指令
        assert client.post("/api/assistant/chat", json={"quick": "xxx"}).status_code == 400

    def test_sessions_crud(self, client, fake_llm):
        # 新建空会话
        resp = client.post("/api/assistant/sessions")
        assert resp.status_code == 200
        sess = resp.json()
        assert sess["message_count"] == 0

        # 向指定会话发两条消息
        client.post("/api/assistant/chat", json={"message": "第一条", "session_id": sess["id"]})
        client.post("/api/assistant/chat", json={"message": "第二条", "session_id": sess["id"]})

        listed = client.get("/api/assistant/sessions").json()["sessions"]
        target = [s for s in listed if s["id"] == sess["id"]][0]
        assert target["message_count"] == 4, "两问两答应为 4 条消息"
        assert target["title"] == "第一条", "首条用户消息截断为标题"

        # 指定不存在的会话
        assert client.post(
            "/api/assistant/chat", json={"message": "hi", "session_id": 9999}
        ).status_code == 404

        # 删除会话及其消息
        assert client.delete(f"/api/assistant/sessions/{sess['id']}").json()["ok"] is True
        history = client.get("/api/assistant/history", params={"session_id": sess["id"]}).json()
        assert history["messages"] == []

    def test_chat_without_session_falls_into_latest(self, client, fake_llm):
        """不带 session_id：落入最近会话；没有会话时自动新建。"""
        r1 = client.post("/api/assistant/chat", json={"message": "自动建会话"})
        sid = r1.json()["session_id"]
        r2 = client.post("/api/assistant/chat", json={"message": "继续聊"})
        assert r2.json()["session_id"] == sid, "应落入最近会话而不是新建"


# ---------------------------------------------------------------------------
# bank/import：规则解析、LLM 提取兜底、LLM 补全、相似度去重
# ---------------------------------------------------------------------------

class TestBankImportApi:
    def test_import_clean_text_no_llm_needed(self, client, fake_llm):
        """字段齐全的文本：不需要 LLM 补全（enriched 为空），直接入库。"""
        text = "什么是 GIL？\n答案：全局解释器锁。\n技术栈：python\n知识点：GIL"
        resp = client.post("/api/bank/import", json={"text": text})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["imported"]) == 1
        assert body["imported"][0]["tech_stack"] == "python"
        assert body["errors"] == []
        assert body["enriched"] == []
        assert fake_llm.calls == [], "字段齐全不应调用 LLM"

    def test_import_llm_enrich_path(self, client, fake_llm):
        """缺答案/技术栈的题走 LLM 补全，enriched 记录补了哪些字段。"""
        text = "什么是装饰器？"
        body = client.post("/api/bank/import", json={"text": text}).json()
        assert len(body["imported"]) == 1
        assert body["imported"][0]["tech_stack"] == "python", "FakeLLM 补全默认 python"
        assert body["errors"] == []
        enriched_fields = body["enriched"][0]["fields"]
        assert "answer" in enriched_fields and "tech_stack" in enriched_fields
        assert any("补全缺失字段" in c for c in fake_llm.calls)

    def test_import_llm_extract_fallback(self, client, fake_llm):
        """规则解析不出的片段走 LLM 结构化提取。"""
        fake_llm.extract_items = [
            {"stem": "LLM 整理出的题干", "answer": "整理出的答案", "tech_stack": "agent"}
        ]
        # 纯标签块（无题干）会落入 leftovers
        body = client.post("/api/bank/import", json={"text": "答案：一段没有题干的孤儿文本"}).json()
        assert len(body["imported"]) == 1
        assert body["imported"][0]["tech_stack"] == "agent"
        assert any("整理成结构化面试题" in c for c in fake_llm.calls)

    def test_import_dedupe_against_existing(self, client):
        """与库内已有题相似（>=0.85）的被 skipped。"""
        text1 = "请详细解释 Python 中 GIL 的原理以及它对多线程性能的影响\n答案：答案一。\n技术栈：python"
        client.post("/api/bank/import", json={"text": text1})

        text2 = "请详细解释 Python 中 GIL 的机制以及它对多线程性能的影响\n答案：答案二。\n技术栈：python"
        body = client.post("/api/bank/import", json={"text": text2}).json()
        assert body["imported"] == []
        assert len(body["skipped"]) == 1
        assert body["skipped"][0]["similarity"] >= 85

        # dedupe=false 时强行入库
        body = client.post("/api/bank/import", json={"text": text2, "dedupe": False}).json()
        assert len(body["imported"]) == 1

    def test_import_dedupe_within_batch(self, client):
        """批内自去重：同一批里两道相似题只入第一道。"""
        text = (
            "请详细解释 Python 中 GIL 的原理以及它对多线程性能的影响\n答案：答案一。\n技术栈：python\n"
            "---\n"
            "请详细解释 Python 中 GIL 的机制以及它对多线程性能的影响\n答案：答案二。\n技术栈：python"
        )
        body = client.post("/api/bank/import", json={"text": text}).json()
        assert len(body["imported"]) == 1
        assert len(body["skipped"]) == 1

    def test_import_threshold_boundary(self, client, monkeypatch):
        """阈值边界：相似度恰好等于阈值判重；阈值调高一分则放行。"""
        from agents import importer

        stem_a = "请详细解释 Python 中 GIL 的原理以及它对多线程性能的影响"
        stem_b = "请详细解释 Python 中 GIL 的机制以及它对多线程性能的影响"
        sim = importer.stem_similarity(stem_a, stem_b)
        assert sim > 0.5, "预检：两题干应有一定相似度"

        text1 = f"{stem_a}\n答案：答案一。\n技术栈：python"
        client.post("/api/bank/import", json={"text": text1})
        text2 = f"{stem_b}\n答案：答案二。\n技术栈：python"

        # 阈值 = sim：>= 判重 -> skipped
        monkeypatch.setattr(importer, "SIMILARITY_THRESHOLD", sim)
        body = client.post("/api/bank/import", json={"text": text2}).json()
        assert len(body["skipped"]) == 1 and not body["imported"]

        # 阈值略高于 sim：放行 -> imported
        monkeypatch.setattr(importer, "SIMILARITY_THRESHOLD", sim + 0.01)
        body = client.post("/api/bank/import", json={"text": text2}).json()
        assert len(body["imported"]) == 1 and not body["skipped"]

    def test_import_empty_text_error(self, client):
        body = client.post("/api/bank/import", json={"text": "   "}).json()
        assert body["imported"] == []
        assert body["errors"], "空输入应报 errors"

    def test_import_force_llm_extract(self, client, fake_llm):
        """force_llm_extract：跳过规则分段，整段走 LLM 提取。"""
        fake_llm.pdf_items = [{"stem": "强制提取的题", "answer": "答案", "tech_stack": "database"}]
        body = client.post(
            "/api/bank/import",
            json={"text": "什么是 GIL？\n答案：全局解释器锁。", "force_llm_extract": True},
        ).json()
        assert len(body["imported"]) == 1
        assert body["imported"][0]["tech_stack"] == "database"
        assert any("提取真正的面试题" in c for c in fake_llm.calls)
