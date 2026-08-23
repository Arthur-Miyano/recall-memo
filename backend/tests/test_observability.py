# -*- coding: utf-8 -*-
"""可观测性覆盖（修复方案 §11）：操作日志、request_id 贯通、日志脱敏、评分带 provider/model。

- 删除/迁移/助理动作落 operation_logs（操作类型、目标、时间、request_id）；
- request_id 贯通：操作日志与 LLM 调用日志的 request_id == 响应头 X-Request-ID；
- 脱敏：评分/导入流程的日志不含用户回答原文、API Key、完整 Prompt；
- 评分响应带实际 provider/model 字段。
"""
import json
import logging

import pytest
from sqlmodel import select

from models import OperationLog


def _logs(db, action: str) -> list[OperationLog]:
    return db.exec(
        select(OperationLog).where(OperationLog.action == action).order_by(OperationLog.id)
    ).all()


class TestOperationLogs:
    def test_delete_question_logged(self, client, seed_questions, db):
        q = seed_questions(1)[0]
        resp = client.delete(f"/api/bank/questions/{q.id}")
        assert resp.status_code == 200
        logs = _logs(db, "delete_question")
        assert len(logs) == 1
        log = logs[0]
        assert log.target == str(q.id)
        assert log.request_id == resp.headers["x-request-id"]
        assert log.created_at is not None

    def test_migrate_questions_logged(self, client, seed_questions, db):
        qs = seed_questions(3)
        ids = [q.id for q in qs]
        resp = client.post("/api/bank/questions/migrate",
                           json={"question_ids": ids, "to_stack": "go"})
        assert resp.status_code == 200
        logs = _logs(db, "migrate_questions")
        assert len(logs) == 1
        log = logs[0]
        assert log.target == "go"
        assert log.detail["question_ids"] == ids
        assert log.detail["moved"] == 3
        assert log.request_id == resp.headers["x-request-id"]
        assert log.created_at is not None

    def test_edit_question_logged(self, client, seed_questions, db):
        q = seed_questions(1)[0]
        resp = client.patch(f"/api/bank/questions/{q.id}", json={"difficulty": "hard"})
        assert resp.status_code == 200
        logs = _logs(db, "edit_question")
        assert len(logs) == 1
        # detail 只记字段名，不记新值（脱敏）
        assert logs[0].detail == {"fields": ["difficulty"]}
        assert logs[0].request_id == resp.headers["x-request-id"]

    def test_assistant_action_logged(self, client, fake_llm, db):
        fake_llm.chat_reply = (
            "好的，可以删掉这道题。\n"
            "```action\n"
            '{"type":"delete_questions","question_ids":[1],"summary":"删除第 1 题"}\n'
            "```"
        )
        resp = client.post("/api/assistant/chat", json={"message": "删掉第 1 题"})
        assert resp.status_code == 200
        assert resp.json()["action"]["type"] == "delete_questions"
        logs = _logs(db, "assistant_action_proposed")
        assert len(logs) == 1
        log = logs[0]
        assert log.target == "delete_questions"
        assert log.detail["question_ids"] == [1]
        assert log.request_id == resp.headers["x-request-id"]
        assert log.created_at is not None

    def test_assistant_plain_chat_not_logged(self, client, db):
        resp = client.post("/api/assistant/chat", json={"message": "今天背得怎么样"})
        assert resp.status_code == 200
        assert resp.json()["action"] is None
        assert _logs(db, "assistant_action_proposed") == []


class _FakeClient:
    """伪 Provider 客户端：可用、async chat 回固定文本。"""

    name = "fakeprov"
    model = "fake-model-1"
    available = True

    async def chat(self, messages, **kwargs):
        return "（假回复）"


class TestRequestIdPropagation:
    @pytest.mark.asyncio
    async def test_llm_success_log_carries_request_id(self, monkeypatch, caplog):
        from infrastructure.requestctx import request_id_var
        from llm import llm_router

        monkeypatch.setattr(llm_router, "_clients", {"fakeprov": _FakeClient()})
        token = request_id_var.set("test-rid-123")
        try:
            with caplog.at_level(logging.INFO, logger="llm.router"):
                provider, _ = await llm_router.chat(
                    [{"role": "user", "content": "hi"}], provider="fakeprov",
                )
        finally:
            request_id_var.reset(token)
        assert provider == "fakeprov"
        success = [r for r in caplog.records if "LLM 调用成功" in r.getMessage()]
        assert len(success) == 1
        msg = success[0].getMessage()
        assert "fakeprov" in msg and "fake-model-1" in msg and "test-rid-123" in msg

    def test_operation_log_request_id_matches_response_header(self, client, seed_questions, db):
        """端到端贯通：API 触发的操作日志 request_id == 响应头 X-Request-ID。"""
        q = seed_questions(1)[0]
        resp = client.delete(f"/api/bank/questions/{q.id}")
        log = _logs(db, "delete_question")[0]
        assert log.request_id == resp.headers["x-request-id"]


class TestLogMasking:
    def test_scoring_logs_free_of_answer_and_key(self, client, fake_llm, seed_questions, caplog):
        """走一遍真实评分流程，日志不得含用户回答原文 / API Key / 完整 Prompt。"""
        secret_answer = "我的独门作答全文甲乙丙丁戊己庚辛"
        seed_questions(3)
        created = client.post("/api/sessions", json={"mode": "memorize", "count": 3}).json()
        sid = created["session_id"]
        client.post(f"/api/sessions/{sid}/start_quiz")
        with caplog.at_level(logging.DEBUG):
            resp = client.post(f"/api/sessions/{sid}/answer", json={"answer": secret_answer})
        assert resp.status_code == 200
        assert secret_answer not in caplog.text
        assert "sk-" not in caplog.text
        assert "【用户回答】" not in caplog.text

    def test_import_logs_free_of_document(self, client, caplog):
        doc = "机密导入文档全文子丑寅卯辰巳午未 " * 5
        payload = json.dumps([{
            "question": "导入测试题：概念是什么？",
            "answer": "导入测试题的标准答案。",
            "tech_stack": "python",
            "knowledge_point": "综合",
        }], ensure_ascii=False)
        with caplog.at_level(logging.DEBUG):
            resp = client.post("/api/bank/import",
                               json={"text": payload + doc, "dedupe": False})
        # 文本不是纯 JSON 数组时会走规则/LLM 解析，只关心日志脱敏
        assert resp.status_code == 200
        assert "机密导入文档全文" not in caplog.text


class TestScoreProviderModel:
    def test_answer_score_carries_provider_model(self, client, seed_questions):
        seed_questions(3)
        created = client.post("/api/sessions", json={"mode": "memorize", "count": 3}).json()
        sid = created["session_id"]
        client.post(f"/api/sessions/{sid}/start_quiz")
        resp = client.post(f"/api/sessions/{sid}/answer", json={"answer": "作答。"})
        assert resp.status_code == 200
        score = resp.json()["score"]
        assert score["provider"] == "fake"  # FakeLLM 报告的 Provider 名
        assert "model" in score             # 假 LLM 无对应客户端，为 None
