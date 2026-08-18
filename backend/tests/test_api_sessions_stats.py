# -*- coding: utf-8 -*-
"""API 覆盖（二）：sessions 三种模式闭环 + stats 四个聚合接口。

走 TestClient 真实路由 + 假 LLM + 临时库；答 2 题后校验各统计数字对得上。
"""
import json

from timeutil import local_today


def _import_questions(client, n=5, stack="python"):
    payload = json.dumps(
        [
            {
                "question": f"{stack} 题 {i}：请解释这个概念？",
                "answer": f"{stack} 题 {i} 的标准答案，内容互不相关甲乙丙丁。",
                "tech_stack": stack,
                "knowledge_point": "综合",
            }
            for i in range(n)
        ],
        ensure_ascii=False,
    )
    resp = client.post("/api/bank/import", json={"text": payload, "dedupe": False})
    assert resp.status_code == 200
    return resp.json()


def _set_score(fake_llm, total: float):
    fake_llm.score = {
        "accuracy": total, "logic": total, "naturalness": total,
        "missed_points": [], "comment": "", "annotated_answer": None,
    }


class TestSessionsApi:
    def test_memorize_full_cycle(self, client, fake_llm):
        _import_questions(client, 3)
        _set_score(fake_llm, 80)

        # 创建
        resp = client.post("/api/sessions", json={"mode": "memorize", "count": 3})
        assert resp.status_code == 200
        created = resp.json()
        sid = created["session_id"]
        assert created["state"] == "MEMORIZE_SHOW"
        assert len(created["questions"]) == 3

        # 会话状态查询
        info = client.get(f"/api/sessions/{sid}").json()
        assert info["mode"] == "memorize"
        assert info["state"] == "MEMORIZE_SHOW"
        assert info["question_count"] == 3

        # start_quiz -> current -> answer ×3
        assert client.post(f"/api/sessions/{sid}/start_quiz").json()["state"] == "MEMORIZE_QUIZ"
        current = client.get(f"/api/sessions/{sid}/current").json()
        assert current["progress"] == "1/3"
        assert "answer" not in current

        for _ in range(2):
            resp = client.post(f"/api/sessions/{sid}/answer", json={"answer": "我的作答。"})
            body = resp.json()
            assert body["finished"] is False
            assert body["score"]["total"] == 80.0
            assert "standard_answer" in body, "考核模式即时反馈应带标准答案"

        resp = client.post(f"/api/sessions/{sid}/answer", json={"answer": "我的作答。"})
        body = resp.json()
        assert body["finished"] is True
        assert body["summary"]["question_count"] == 3
        assert body["summary"]["avg_total"] == 80.0

    def test_interview_cycle_with_review(self, client, fake_llm):
        _import_questions(client, 3)
        _set_score(fake_llm, 70)

        resp = client.post("/api/sessions", json={"mode": "interview", "count": 3})
        assert resp.status_code == 200
        sid = resp.json()["session_id"]
        assert resp.json()["state"] == "INTERVIEW_ANSWER"

        # 答 1 题、跳 1 题、答 1 题
        resp = client.post(f"/api/sessions/{sid}/answer", json={"answer": "面试作答。"})
        assert "score" not in resp.json(), "面试 answer 只回执不出分"
        resp = client.post(f"/api/sessions/{sid}/skip")
        assert resp.json()["recorded"] is True
        resp = client.post(f"/api/sessions/{sid}/answer", json={"answer": "面试作答。"})
        assert resp.json()["finished"] is True

        review = client.get(f"/api/sessions/{sid}/review").json()
        assert review["question_count"] == 3
        entry = review["per_question"][0]
        assert "annotated_answer" in entry
        assert review["avg_total"] == 70.0
        assert len(review["retry_list"]) == 1  # 跳过的那题

        # 待补答队列接口
        queue = client.get("/api/sessions/retry-queue").json()
        assert queue["count"] == 1

    def test_review_mode_requires_history(self, client):
        _import_questions(client, 3)
        resp = client.post("/api/sessions", json={"mode": "review", "count": 3})
        assert resp.status_code == 400, "无历史记录时回忆模式应 400"
        assert "暂无历史记录" in resp.json()["detail"]

    def test_review_mode_after_memorize(self, client, fake_llm):
        """先完成一场记忆训练，再开回忆模式应能抽到有记录的题。"""
        _import_questions(client, 3)
        _set_score(fake_llm, 80)
        resp = client.post("/api/sessions", json={"mode": "memorize", "count": 3})
        sid = resp.json()["session_id"]
        client.post(f"/api/sessions/{sid}/start_quiz")
        for _ in range(3):
            client.post(f"/api/sessions/{sid}/answer", json={"answer": "作答。"})

        resp = client.post("/api/sessions", json={"mode": "review", "count": 2})
        assert resp.status_code == 200
        assert resp.json()["state"] == "REVIEW_SHOW"
        assert len(resp.json()["questions"]) == 2

    def test_state_errors_map_to_400(self, client, fake_llm):
        _import_questions(client, 3)
        resp = client.post("/api/sessions", json={"mode": "memorize", "count": 3})
        sid = resp.json()["session_id"]
        # 未 start_quiz 就 answer
        resp = client.post(f"/api/sessions/{sid}/answer", json={"answer": "抢答"})
        assert resp.status_code == 400
        # 未 start_quiz 就 current
        assert client.get(f"/api/sessions/{sid}/current").status_code == 400

    def test_missing_session_404(self, client):
        assert client.get("/api/sessions/9999").status_code == 404

    def test_deprecated_retry_endpoint_410(self, client):
        resp = client.post("/api/sessions/1/retry")
        assert resp.status_code == 410


class TestStatsApi:
    def _answer_two_questions(self, client, fake_llm):
        """记忆训练答 2 题（一高一低分），返回会话 id。"""
        _import_questions(client, 3)
        _set_score(fake_llm, 80)
        resp = client.post("/api/sessions", json={"mode": "memorize", "count": 3})
        sid = resp.json()["session_id"]
        client.post(f"/api/sessions/{sid}/start_quiz")
        client.post(f"/api/sessions/{sid}/answer", json={"answer": "第一题作答。"})
        _set_score(fake_llm, 40)
        resp = client.post(f"/api/sessions/{sid}/answer", json={"answer": "第二题作答。"})
        assert resp.json()["score"]["total"] == 40.0
        return sid

    def test_overview_after_two_answers(self, client, fake_llm):
        self._answer_two_questions(client, fake_llm)
        data = client.get("/api/stats/overview").json()
        assert data["total_questions"] == 3
        assert data["total_attempts"] == 2
        assert data["covered"] == 2
        assert data["avg_score"] == 60.0, f"均分应为 (80+40)/2=60，实际 {data['avg_score']}"
        stack = data["per_stack"]["python"]
        assert stack["total_questions"] == 3
        assert stack["attempts"] == 2
        assert stack["pass_rate"] == 0.5, "一及格一不及格，正确率 0.5"

    def test_daily_trend(self, client, fake_llm):
        self._answer_two_questions(client, fake_llm)
        data = client.get("/api/stats/daily", params={"days": 7}).json()
        assert data["days"] == 7
        assert len(data["items"]) == 7, "无数据的日期补零"
        today = local_today().isoformat()
        today_item = [i for i in data["items"] if i["date"] == today]
        assert today_item, "应包含今天"
        assert today_item[0]["total_count"] == 2
        assert today_item[0]["success_count"] == 1
        assert today_item[0]["fail_count"] == 1

    def test_daily_detail(self, client, fake_llm):
        self._answer_two_questions(client, fake_llm)
        data = client.get("/api/stats/daily-detail", params={"days": 30}).json()
        assert len(data["items"]) == 1, "只有今天有记录"
        day = data["items"][0]
        assert day["date"] == local_today().isoformat()
        assert len(day["records"]) == 2
        scores = sorted(r["score"] for r in day["records"])
        assert scores == [40.0, 80.0]
        assert all(r["mode"] == "记忆训练" for r in day["records"])

    def test_per_question(self, client, fake_llm):
        self._answer_two_questions(client, fake_llm)
        data = client.get("/api/stats/per-question").json()
        assert data["total"] == 3
        by_id = {i["question_id"]: i for i in data["items"]}
        done = [i for i in data["items"] if i["status"] == "done"]
        weak = [i for i in data["items"] if i["status"] == "weak"]
        todo = [i for i in data["items"] if i["status"] == "todo"]
        assert len(done) == 1 and done[0]["latest_score"] == 80.0
        assert len(weak) == 1 and weak[0]["latest_score"] == 40.0
        assert len(todo) == 1 and todo[0]["attempts"] == 0
        assert done[0]["recent_scores"][-1]["score"] == 80.0

    def test_stats_empty_db(self, client):
        overview = client.get("/api/stats/overview").json()
        assert overview["total_questions"] == 0
        assert overview["avg_score"] is None
        daily = client.get("/api/stats/daily").json()
        assert all(i["total_count"] == 0 for i in daily["items"])
        detail = client.get("/api/stats/daily-detail").json()
        assert detail["items"] == []
        per_q = client.get("/api/stats/per-question").json()
        assert per_q == {"total": 0, "items": []}


class TestSessionsLlmDegradation:
    def test_llm_down_returns_503(self, client, monkeypatch):
        """LLM 全部不可用（超时/限流/未配置 Key）：503 + 可读降级提示，不抛裸 500。"""
        from llm import llm_router
        from llm.router import LLMProviderUnavailableError

        async def _down(messages, **kwargs):
            raise LLMProviderUnavailableError("所有 Provider 调用均失败")

        monkeypatch.setattr(llm_router, "chat", _down)
        _import_questions(client, 3)
        resp = client.post("/api/sessions", json={"mode": "interview", "count": 3})
        assert resp.status_code == 503
        assert "LLM 服务暂不可用" in resp.json()["detail"]

    def test_empty_bank_returns_400_with_guidance(self, client):
        """空题库：400 + 引导文案（先有题再训练），会话不留孤儿行。"""
        resp = client.post("/api/sessions", json={"mode": "memorize", "count": 3})
        assert resp.status_code == 400
        assert "题库为空" in resp.json()["detail"]
