# -*- coding: utf-8 -*-
"""E2E 用户旅程（修复方案 §7.3 第 6 条）：

导入题目 → 记忆训练 → 答错 → 待补答队列 → 再训练（补答优先、答对出队）→ 查看统计。
全程走 TestClient 真实路由 + 假 LLM + 临时库，逐步断言每步状态。
（记忆训练题量仅支持 3/5/7，两轮会话均取 3 题。）
"""
import json

from agents.base import SCORE_PASS_THRESHOLD


def _set_score(fake_llm, total: float):
    fake_llm.score = {
        "accuracy": total, "logic": total, "naturalness": total,
        "missed_points": [], "comment": "", "annotated_answer": None,
    }


def test_journey_import_train_fail_retry_stats(client, fake_llm):
    # ---------- 1. 导入题目 ----------
    payload = json.dumps(
        [
            {
                "question": f"旅程题 {i}：请解释这个概念？",
                "answer": f"旅程题 {i} 的标准答案，内容互不相关甲乙丙丁。",
                "tech_stack": "python",
                "knowledge_point": "综合",
            }
            for i in range(3)
        ],
        ensure_ascii=False,
    )
    resp = client.post("/api/bank/import", json={"text": payload, "dedupe": False})
    assert resp.status_code == 200
    assert len(resp.json()["imported"]) == 3

    # ---------- 2. 记忆训练：创建会话 -> 开始考核 ----------
    resp = client.post("/api/sessions", json={"mode": "memorize", "count": 3})
    assert resp.status_code == 200
    created = resp.json()
    sid = created["session_id"]
    assert created["state"] == "MEMORIZE_SHOW"
    assert len(created["questions"]) == 3
    assert all(q["retry"] is False for q in created["questions"]), "首轮训练无补答题"

    assert client.post(f"/api/sessions/{sid}/start_quiz").json()["state"] == "MEMORIZE_QUIZ"
    current = client.get(f"/api/sessions/{sid}/current").json()
    assert current["progress"] == "1/3"
    assert "answer" not in current

    # ---------- 3. 答错第 1 题（不及格 -> 入待补答队列） ----------
    _set_score(fake_llm, SCORE_PASS_THRESHOLD - 1)
    resp = client.post(f"/api/sessions/{sid}/answer", json={"answer": "答错了。"})
    body = resp.json()
    assert body["finished"] is False
    assert body["score"]["total"] < SCORE_PASS_THRESHOLD

    queue = client.get("/api/sessions/retry-queue").json()
    assert queue["count"] == 1
    retry_qid = queue["items"][0]["question_id"]
    assert queue["items"][0]["source"] == "memorize"

    # ---------- 4. 答对后 2 题，首轮结束 ----------
    _set_score(fake_llm, 80)
    for _ in range(2):
        resp = client.post(f"/api/sessions/{sid}/answer", json={"answer": "答对了。"})
    assert resp.json()["finished"] is True
    assert client.get("/api/sessions/retry-queue").json()["count"] == 1, "答错的题仍在队列"

    # ---------- 5. 再训练：补答题优先抽取并带红标 ----------
    resp = client.post("/api/sessions", json={"mode": "memorize", "count": 3})
    created2 = resp.json()
    sid2 = created2["session_id"]
    assert created2["questions"][0]["question_id"] == retry_qid, "待补答队列的题应优先重背"
    assert created2["questions"][0]["retry"] is True

    client.post(f"/api/sessions/{sid2}/start_quiz")

    # 补答：答对 -> 出队（补答机会已消耗，无论及格与否都不再入队）。
    # start_quiz 打乱答题顺序，逐题作答并在补答题答对后立即断言出队。
    seen_retry = False
    for i in range(3):
        cur = client.get(f"/api/sessions/{sid2}/current").json()
        resp = client.post(f"/api/sessions/{sid2}/answer", json={"answer": "作答。"})
        assert resp.json()["score"]["total"] >= SCORE_PASS_THRESHOLD
        if cur["question_id"] == retry_qid:
            seen_retry = True
            assert client.get("/api/sessions/retry-queue").json()["count"] == 0, "补答及格后应立即出队"
    assert seen_retry, "第二轮应包含补答题"
    assert resp.json()["finished"] is True

    # ---------- 6. 查看统计：6 次作答、3 题全覆盖、正确率 5/6 ----------
    overview = client.get("/api/stats/overview").json()
    assert overview["total_questions"] == 3
    assert overview["total_attempts"] == 6
    assert overview["covered"] == 3
    assert overview["per_stack"]["python"]["pass_rate"] == round(5 / 6, 4)

    daily = client.get("/api/stats/daily", params={"days": 7}).json()
    today = [i for i in daily["items"] if i["total_count"] > 0]
    assert len(today) == 1 and today[0]["total_count"] == 6, "今日应聚合 6 次作答"
    assert today[0]["success_count"] == 5 and today[0]["fail_count"] == 1
