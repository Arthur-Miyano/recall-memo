# -*- coding: utf-8 -*-
"""文件上传录入的真实链路测试（/api/bank/import-file 与 import-jobs 的文件分支）：

- 用 tests/fixtures/sample.pdf（真实 PDF，pypdf 可提取文本）走完
  extract_pdf_text → 强制 LLM 提取 → 入库全链路；
- 回归：PDF 解析必须经 asyncio.to_thread 放工作线程（否则大 PDF 会阻塞事件循环，
  该问题曾因测试只断言最终结果而漏网）。
"""
import asyncio
from pathlib import Path

from infrastructure import documents

FIXTURE_PDF = (Path(__file__).parent / "fixtures" / "sample.pdf").read_bytes()


class TestImportFile:
    def test_pdf_real_parse_and_import(self, client, fake_llm):
        """真实 PDF 上传：pypdf 提取文本 → 强制走 LLM 提取真问题 → 入库。"""
        fake_llm.pdf_items = [
            {"stem": "What is the GIL in CPython?", "answer": "全局解释器锁。", "tech_stack": "python"}
        ]
        resp = client.post(
            "/api/bank/import-file",
            files={"file": ("sample.pdf", FIXTURE_PDF, "application/pdf")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["imported"]) == 1
        assert body["imported"][0]["tech_stack"] == "python"
        assert any("提取真正的面试题" in c for c in fake_llm.calls), "PDF 必须强制走 LLM 提取路径"

    def test_pdf_parsing_offloaded_to_worker_thread(self, client, fake_llm, monkeypatch):
        """回归：/import-file 的 PDF 解析必须经 asyncio.to_thread（工作线程）。

        只断言最终结果挡不住阻塞回归（同步执行测试也全绿），这里直接监视
        to_thread 的调用对象，确认 decode_source_text 被放进工作线程。
        """
        calls = []
        real_to_thread = asyncio.to_thread

        async def spy(func, *args, **kwargs):
            calls.append(func)
            return await real_to_thread(func, *args, **kwargs)

        monkeypatch.setattr(asyncio, "to_thread", spy)
        fake_llm.pdf_items = [{"stem": "Q?", "answer": "A.", "tech_stack": "python"}]
        resp = client.post(
            "/api/bank/import-file",
            files={"file": ("sample.pdf", FIXTURE_PDF, "application/pdf")},
        )
        assert resp.status_code == 200
        assert documents.decode_source_text in calls, "PDF/文本解析必须放工作线程执行"

    def test_txt_upload(self, client):
        resp = client.post(
            "/api/bank/import-file",
            files={"file": ("notes.txt", "什么是闭包？\n答案：携带自由变量的函数。\n技术栈：python".encode("utf-8"), "text/plain")},
        )
        assert resp.status_code == 200
        assert len(resp.json()["imported"]) == 1

    def test_unsupported_ext_rejected(self, client):
        resp = client.post(
            "/api/bank/import-file",
            files={"file": ("evil.exe", b"\x00\x01", "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert "不支持的文件类型" in resp.json()["detail"]

    def test_empty_file_rejected(self, client):
        resp = client.post(
            "/api/bank/import-file",
            files={"file": ("empty.txt", b"", "text/plain")},
        )
        assert resp.status_code == 400

    def test_corrupt_pdf_rejected(self, client):
        resp = client.post(
            "/api/bank/import-file",
            files={"file": ("broken.pdf", b"%PDF-1.4 garbage", "application/pdf")},
        )
        assert resp.status_code == 400
        assert "PDF 解析失败" in resp.json()["detail"] or "未提取到文本" in resp.json()["detail"]


class TestImportJobsPdf:
    def _wait_done(self, client, job_id: str, rounds: int = 100) -> dict:
        import time
        for _ in range(rounds):
            j = client.get(f"/api/bank/import-jobs/{job_id}").json()
            if j["status"] != "running":
                return j
            time.sleep(0.05)
        raise AssertionError(f"任务 {job_id} 长时间未结束：{j}")

    def test_job_with_real_pdf(self, client, fake_llm):
        """后台任务的 PDF 分支：真实 PDF 走 decode_source_text → 强制 LLM 提取 → 入库。"""
        fake_llm.pdf_items = [
            {"stem": "What is the GIL in CPython?", "answer": "全局解释器锁。", "tech_stack": "python"}
        ]
        files = [("files", ("sample.pdf", FIXTURE_PDF, "application/pdf"))]
        resp = client.post("/api/bank/import-jobs", files=files, data={"dedupe": "true"})
        assert resp.status_code == 202

        j = self._wait_done(client, resp.json()["job_id"])
        assert j["status"] == "done"
        assert j["result"]["totals"]["imported"] == 1
        assert j["result"]["file_errors"] == []
        assert j["result"]["files"][0]["file"] == "sample.pdf"
        assert any("提取真正的面试题" in c for c in fake_llm.calls)
