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

    def test_chat_without_action_block_returns_null(self, client, fake_llm):
        """普通回复：action 为 null。"""
        body = client.post("/api/assistant/chat", json={"message": "总结下"}).json()
        assert body["action"] is None
        assert body["reply"] == fake_llm.chat_reply


# ---------------------------------------------------------------------------
# assistant 动作提议协议（```action 围栏块解析与校验）
# ---------------------------------------------------------------------------

def _action_reply(payload: dict, prefix: str = "好的，已理解。") -> str:
    import json as _json
    return f"{prefix}\n```action\n{_json.dumps(payload, ensure_ascii=False)}\n```"


class TestAssistantActionBlock:
    def test_delete_action_parsed(self, client, fake_llm, seed_questions):
        """合法 delete_questions：action 字段正确，reply 里动作块已剥掉，落库的回复也不含块。"""
        seed_questions(2)
        fake_llm.chat_reply = _action_reply(
            {"type": "delete_questions", "question_ids": [1, 2], "summary": "删除 2 道题"}
        )
        body = client.post("/api/assistant/chat", json={"message": "把这两道题删掉"}).json()
        assert body["reply"] == "好的，已理解。"
        assert body["action"] == {
            "type": "delete_questions", "question_ids": [1, 2], "summary": "删除 2 道题",
        }
        assert any("动作提议" in t for t in body["thinking"])
        history = client.get("/api/assistant/history", params={"session_id": body["session_id"]}).json()
        assert "```action" not in history["messages"][1]["content"], "落库回复不应含动作块"

    def test_edit_action_parsed(self, client, fake_llm, seed_questions):
        """合法 edit_question：恰好 1 题 + changes。"""
        seed_questions(1)
        fake_llm.chat_reply = _action_reply(
            {"type": "edit_question", "question_ids": [1],
             "changes": {"stem": "新题干", "difficulty": "hard"}, "summary": "修改题干和难度"}
        )
        body = client.post("/api/assistant/chat", json={"message": "改掉第 1 题"}).json()
        action = body["action"]
        assert action["type"] == "edit_question"
        assert action["changes"] == {"stem": "新题干", "difficulty": "hard"}

    def test_migrate_action_parsed(self, client, fake_llm, seed_questions):
        """合法 migrate_questions：ids + to_stack。"""
        seed_questions(3)
        fake_llm.chat_reply = _action_reply(
            {"type": "migrate_questions", "question_ids": [1, 2, 3],
             "to_stack": "database", "summary": "迁移 3 道题到 database"}
        )
        body = client.post("/api/assistant/chat", json={"message": "迁移到数据库分组"}).json()
        assert body["action"]["type"] == "migrate_questions"
        assert body["action"]["to_stack"] == "database"
        assert body["action"]["question_ids"] == [1, 2, 3]

    def test_bad_json_block_discarded(self, client, fake_llm):
        """动作块 JSON 损坏：action 为 null，回复照常（块被剥掉）。"""
        fake_llm.chat_reply = "好的。\n```action\n{这 不是 JSON\n```"
        resp = client.post("/api/assistant/chat", json={"message": "删题"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["action"] is None
        assert body["reply"] == "好的。"

    def test_unknown_type_discarded(self, client, fake_llm):
        fake_llm.chat_reply = _action_reply({"type": "drop_bank", "question_ids": [1]})
        body = client.post("/api/assistant/chat", json={"message": "删库"}).json()
        assert body["action"] is None
        assert body["reply"] == "好的，已理解。"

    def test_edit_without_changes_discarded(self, client, fake_llm):
        fake_llm.chat_reply = _action_reply({"type": "edit_question", "question_ids": [1]})
        body = client.post("/api/assistant/chat", json={"message": "改题"}).json()
        assert body["action"] is None

    def test_edit_with_illegal_change_key_discarded(self, client, fake_llm):
        fake_llm.chat_reply = _action_reply(
            {"type": "edit_question", "question_ids": [1], "changes": {"id": 99}}
        )
        body = client.post("/api/assistant/chat", json={"message": "改题"}).json()
        assert body["action"] is None

    def test_edit_multiple_ids_discarded(self, client, fake_llm):
        """edit_question 一次只能改一道题。"""
        fake_llm.chat_reply = _action_reply(
            {"type": "edit_question", "question_ids": [1, 2], "changes": {"stem": "x"}}
        )
        body = client.post("/api/assistant/chat", json={"message": "改题"}).json()
        assert body["action"] is None

    def test_too_many_ids_discarded(self, client, fake_llm):
        fake_llm.chat_reply = _action_reply(
            {"type": "delete_questions", "question_ids": list(range(1, 52))}
        )
        body = client.post("/api/assistant/chat", json={"message": "全删了"}).json()
        assert body["action"] is None

    def test_bad_ids_discarded(self, client, fake_llm):
        """ids 为空 / 含非整数（字符串、bool）→ 丢弃。"""
        for ids in ([], ["1"], [True]):
            fake_llm.chat_reply = _action_reply({"type": "delete_questions", "question_ids": ids})
            body = client.post("/api/assistant/chat", json={"message": "删题"}).json()
            assert body["action"] is None, f"ids={ids} 应被拒绝"

    def test_migrate_without_to_stack_discarded(self, client, fake_llm):
        fake_llm.chat_reply = _action_reply(
            {"type": "migrate_questions", "question_ids": [1]}
        )
        body = client.post("/api/assistant/chat", json={"message": "迁移"}).json()
        assert body["action"] is None


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

    def test_import_unlabeled_doc_auto_falls_back_to_llm_extract(self, client, fake_llm):
        """无标签文档（整篇八股文）：规则分段产出大面积缺答案条目时，
        自动改走 LLM 提取真问题，而不是把每个段落当题去补全。"""
        # 12 个无标签段落（模拟 md 文档按空行切开后的样子），全部缺答案
        doc = "\n\n".join(f"## 第 {i} 节\n这是一段没有答案标签的叙述性正文 {i}。" for i in range(12))
        fake_llm.pdf_items = [{"stem": "文档里真正的面试题？", "answer": "真答案", "tech_stack": "python"}]
        body = client.post("/api/bank/import", json={"text": doc}).json()
        assert any("提取真正的面试题" in c for c in fake_llm.calls), "应自动改走 LLM 提取路径"
        assert len(body["imported"]) == 1
        assert body["imported"][0]["title"].startswith("文档里真正的面试题")

    def test_import_labeled_text_stays_on_rule_path(self, client, fake_llm):
        """带「答案：」标签的手写格式：仍走规则解析 + 补全，不触发 LLM 提取路径。"""
        topics = ["闭包", "装饰器", "生成器", "迭代器", "元类", "垃圾回收",
                  "多线程", "多进程", "协程", "上下文管理器", "描述符", "反射"]
        text = "\n\n".join(f"什么是{t}？\n答案：{t}的标准答案。\n技术栈：python" for t in topics)
        body = client.post("/api/bank/import", json={"text": text}).json()
        assert not any("提取真正的面试题" in c for c in fake_llm.calls)
        assert len(body["imported"]) == 12

    def test_import_enrich_batches(self, client, fake_llm):
        """AI 补全分批：25 题缺技术栈分类时，补全接口应被调用 2 次（每批 20 题）。
        （缺答案走自动改判路径，故这里用「有答案、缺分类」触发补全）"""
        topics = ["闭包", "装饰器", "生成器", "迭代器", "元类", "垃圾回收", "多线程", "多进程",
                  "协程", "上下文管理器", "描述符", "反射", "序列化", "哈希表", "红黑树", "事务",
                  "索引", "锁机制", "视图", "触发器", "存储过程", "范式", "分库分表", "读写分离", "缓存"]
        text = "\n\n".join(f"什么是{t}？\n答案：{t}的标准答案，覆盖核心考点。" for t in topics)
        body = client.post("/api/bank/import", json={"text": text}).json()
        enrich_calls = [c for c in fake_llm.calls if "补全缺失字段" in c]
        assert len(enrich_calls) == 2
        assert len(body["imported"]) == 25


# bank/import-jobs：后台录入任务（多文件 + 进度轮询 + latest 重挂）
class TestImportJobs:
    def _wait_done(self, client, job_id: str, rounds: int = 100) -> dict:
        """轮询任务直到结束（后台协程在 TestClient portal 的事件循环里持续推进）。"""
        import time
        for _ in range(rounds):
            j = client.get(f"/api/bank/import-jobs/{job_id}").json()
            if j["status"] != "running":
                return j
            time.sleep(0.05)
        raise AssertionError(f"任务 {job_id} 长时间未结束：{j}")

    def test_job_text_runs_to_done(self, client):
        """粘贴文本创建任务：202 接受 → 轮询到 done → 结果含入库题 → latest 可重挂。"""
        resp = client.post(
            "/api/bank/import-jobs",
            data={"text": "什么是闭包？\n答案：函数携带定义时的自由变量。\n技术栈：python", "dedupe": "true"},
        )
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        j = self._wait_done(client, job_id)
        assert j["status"] == "done"
        assert j["result"]["totals"]["imported"] == 1
        assert j["result"]["files"][0]["file"] == "粘贴文本"

        latest = client.get("/api/bank/import-jobs/latest").json()["job"]
        assert latest["id"] == job_id
        assert latest["status"] == "done"

    def test_job_multi_files(self, client):
        """多文件一次提交：两个 .txt 各自走管线，结果按文件分组。"""
        files = [
            ("files", ("a.txt", "什么是迭代器？\n答案：实现 __iter__/__next__ 的对象。\n技术栈：python".encode("utf-8"), "text/plain")),
            ("files", ("b.txt", "什么是索引？\n答案：加速查询的数据结构。\n技术栈：database".encode("utf-8"), "text/plain")),
        ]
        resp = client.post("/api/bank/import-jobs", files=files, data={"dedupe": "true"})
        assert resp.status_code == 202
        j = self._wait_done(client, resp.json()["job_id"])
        assert j["status"] == "done"
        assert j["result"]["totals"]["imported"] == 2
        assert {f["file"] for f in j["result"]["files"]} == {"a.txt", "b.txt"}

    def test_job_empty_rejected(self, client):
        """既无文件也无文本：400。"""
        resp = client.post("/api/bank/import-jobs", data={"dedupe": "true"})
        assert resp.status_code == 400

    def test_job_not_found(self, client):
        assert client.get("/api/bank/import-jobs/nope").status_code == 404

    def test_job_bad_file_recorded_not_fatal(self, client):
        """单个文件类型不支持：记为该文件的错误，不拖垮其他文件。"""
        files = [
            ("files", ("bad.exe", b"\x00\x01", "application/octet-stream")),
            ("files", ("ok.txt", "什么是生成器？\n答案：yield 返回的迭代器。\n技术栈：python".encode("utf-8"), "text/plain")),
        ]
        resp = client.post("/api/bank/import-jobs", files=files, data={"dedupe": "true"})
        assert resp.status_code == 202
        j = self._wait_done(client, resp.json()["job_id"])
        assert j["status"] == "done"
        assert j["result"]["totals"]["imported"] == 1
        assert j["result"]["file_errors"][0]["file"] == "bad.exe"
