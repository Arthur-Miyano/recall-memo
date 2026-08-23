# -*- coding: utf-8 -*-
"""统一上传策略与导入资源限制（修复方案 §5.1）覆盖：

- read_upload 分块读取：超限立即终止，不读完整个文件；
- 扩展名白名单 / 压缩格式签名拒绝 / PDF 签名 / SQLite magic；
- API 入口：单文件超限、单批文件数超限、总大小超限、PDF 页数超限、粘贴文本超限；
- ImportBudget：LLM 请求数 / Token 预算 / 总运行时间上限；
- 错误响应一律为稳定结构 {error: {code, message}, request_id}。
"""
import io
from pathlib import Path

import pytest
from fastapi import UploadFile

from application import uploads
from application.importer import ImportBudget, ImportBudgetExceededError
from application.uploads import UploadRejectedError
from config import settings

FIXTURE_PDF = (Path(__file__).parent / "fixtures" / "sample.pdf").read_bytes()


def _upload_file(name: str, data: bytes) -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=name)


# ---------------------------------------------------------------------------
# read_upload：分块累计，超限立即终止
# ---------------------------------------------------------------------------

class TestReadUpload:
    async def test_small_file_read_fully(self, monkeypatch):
        monkeypatch.setattr(settings, "upload_max_file_bytes", 1024)
        f = _upload_file("a.txt", b"hello")
        assert await uploads.read_upload(f) == b"hello"

    async def test_oversized_stops_without_reading_whole_file(self, monkeypatch):
        """超限立即终止：流位置停在 上限+一个块 以内，绝不读完整个文件。"""
        monkeypatch.setattr(settings, "upload_max_file_bytes", 1024)
        monkeypatch.setattr(uploads, "_CHUNK", 256)
        data = b"x" * 5000
        f = _upload_file("big.txt", data)
        with pytest.raises(UploadRejectedError) as exc_info:
            await uploads.read_upload(f)
        assert exc_info.value.code == "FILE_TOO_LARGE"
        assert exc_info.value.status == 413
        position = f.file.tell()
        assert position < len(data), "超限后不应读完整个文件"
        assert position <= 1024 + 256, "最多只多读一个块"

    async def test_exactly_at_limit_allowed(self, monkeypatch):
        monkeypatch.setattr(settings, "upload_max_file_bytes", 100)
        assert await uploads.read_upload(_upload_file("a.txt", b"x" * 100)) == b"x" * 100


# ---------------------------------------------------------------------------
# 扩展名白名单 / 压缩签名 / 文件签名
# ---------------------------------------------------------------------------

class TestValidateUpload:
    def test_document_extensions_whitelist(self):
        assert uploads.validate_document_upload("a.md", b"text") == ".md"
        assert uploads.validate_document_upload("a.txt", b"text") == ".txt"
        assert uploads.validate_document_upload("a.json", b"[]") == ".json"
        assert uploads.validate_document_upload("a.pdf", b"%PDF-1.4 ...") == ".pdf"

    def test_non_whitelisted_extension_rejected(self):
        with pytest.raises(UploadRejectedError) as exc_info:
            uploads.validate_document_upload("evil.exe", b"\x00\x01")
        assert exc_info.value.code == "UNSUPPORTED_FILE_TYPE"
        with pytest.raises(UploadRejectedError):
            uploads.validate_document_upload("noext", b"text")
        # .db 不属于题库文档白名单
        with pytest.raises(UploadRejectedError):
            uploads.validate_document_upload("bagu.db", b"SQLite format 3")

    @pytest.mark.parametrize("magic", [b"PK\x03\x04", b"PK\x05\x06", b"\x1f\x8b", b"7z\xbc\xaf\x27\x1c", b"Rar!\x1a\x07"])
    def test_archive_signatures_rejected_regardless_of_extension(self, magic):
        """压缩格式以文件签名为准：改名 .md/.txt 一样拒绝。"""
        with pytest.raises(UploadRejectedError) as exc_info:
            uploads.validate_document_upload("notes.md", magic + b"payload")
        assert exc_info.value.code == "ARCHIVE_NOT_SUPPORTED"

    def test_pdf_requires_signature(self):
        """MIME/扩展名只作辅助：.pdf 缺文件签名按内容与扩展名不符拒绝。"""
        with pytest.raises(UploadRejectedError) as exc_info:
            uploads.validate_document_upload("fake.pdf", b"not a pdf at all")
        assert exc_info.value.code == "INVALID_DOCUMENT"

    def test_db_upload_magic_check(self):
        uploads.validate_db_upload("bagu.db", b"SQLite format 3\x00" + b"\x00" * 100)
        with pytest.raises(UploadRejectedError) as exc_info:
            uploads.validate_db_upload("bagu.db", b"definitely not sqlite")
        assert exc_info.value.code == "INVALID_DATABASE"
        with pytest.raises(UploadRejectedError):
            uploads.validate_db_upload("dump.txt", b"SQLite format 3\x00")


# ---------------------------------------------------------------------------
# ImportBudget：LLM 请求数 / Token 预算 / 总运行时间
# ---------------------------------------------------------------------------

class TestImportBudget:
    def test_llm_call_count_limit(self, monkeypatch):
        monkeypatch.setattr(settings, "import_max_llm_calls", 2)
        budget = ImportBudget()
        budget.before_call([{"role": "user", "content": "一"}])
        budget.before_call([{"role": "user", "content": "二"}])
        with pytest.raises(ImportBudgetExceededError, match="请求数"):
            budget.before_call([{"role": "user", "content": "三"}])

    def test_token_budget_limit(self, monkeypatch):
        monkeypatch.setattr(settings, "import_max_token_budget", 10)
        budget = ImportBudget()
        with pytest.raises(ImportBudgetExceededError, match="Token"):
            budget.before_call([{"role": "user", "content": "x" * 11}])

    def test_time_limit(self, monkeypatch):
        monkeypatch.setattr(settings, "import_max_seconds", 0.0)
        budget = ImportBudget()
        with pytest.raises(ImportBudgetExceededError, match="运行时间"):
            budget.check_time()

    def test_counts_accumulate(self, monkeypatch):
        monkeypatch.setattr(settings, "import_max_llm_calls", 100)
        budget = ImportBudget()
        budget.before_call([{"role": "user", "content": "abcd"}])
        budget.before_call([{"role": "user", "content": "ef"}])
        assert budget.calls == 2
        assert budget.tokens == 6


# ---------------------------------------------------------------------------
# API 入口：稳定 4xx 错误结构
# ---------------------------------------------------------------------------

class TestUploadApiLimits:
    def test_file_too_large(self, client, monkeypatch):
        monkeypatch.setattr(settings, "upload_max_file_bytes", 8)
        resp = client.post(
            "/api/bank/import-file",
            files={"file": ("notes.txt", b"x" * 100, "text/plain")},
        )
        assert resp.status_code == 413
        body = resp.json()
        assert body["error"]["code"] == "FILE_TOO_LARGE"
        assert body["request_id"]
        assert resp.headers["x-request-id"] == body["request_id"]

    def test_batch_too_many_files(self, client, monkeypatch):
        monkeypatch.setattr(settings, "upload_max_files", 2)
        files = [("files", (f"n{i}.txt", b"text", "text/plain")) for i in range(3)]
        resp = client.post("/api/bank/import-jobs", files=files)
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "TOO_MANY_FILES"

    def test_batch_total_too_large(self, client, monkeypatch):
        monkeypatch.setattr(settings, "upload_max_file_bytes", 100)
        monkeypatch.setattr(settings, "upload_max_total_bytes", 150)
        files = [("files", (f"n{i}.txt", b"x" * 100, "text/plain")) for i in range(2)]
        resp = client.post("/api/bank/import-jobs", files=files)
        assert resp.status_code == 413
        assert resp.json()["error"]["code"] == "UPLOAD_TOTAL_TOO_LARGE"

    def test_archive_rejected_via_api(self, client):
        resp = client.post(
            "/api/bank/import-file",
            files={"file": ("notes.txt", b"PK\x03\x04" + b"\x00" * 50, "text/plain")},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "ARCHIVE_NOT_SUPPORTED"

    def test_pdf_page_limit(self, client, monkeypatch):
        monkeypatch.setattr(settings, "pdf_max_pages", 0)
        resp = client.post(
            "/api/bank/import-file",
            files={"file": ("sample.pdf", FIXTURE_PDF, "application/pdf")},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "PDF_TOO_MANY_PAGES"

    def test_pasted_text_too_large(self, client, monkeypatch):
        monkeypatch.setattr(settings, "extract_max_chars", 10)
        resp = client.post("/api/bank/import", json={"text": "什么是闭包？" * 10})
        assert resp.status_code == 413
        assert resp.json()["error"]["code"] == "TEXT_TOO_LARGE"
    def test_batch_rejected_file_becomes_file_error(self, client, fake_llm):
        """批任务中单个文件被策略拒绝（压缩包改名 .md）：记 file_errors，任务不拖垮。"""
        import time

        files = [
            ("files", ("pack.md", b"PK\x03\x04" + b"\x00" * 20, "text/markdown")),
            ("files", ("ok.txt", "什么是闭包？\n答案：携带自由变量的函数。\n技术栈：python".encode("utf-8"), "text/plain")),
        ]
        resp = client.post("/api/bank/import-jobs", files=files)
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]
        for _ in range(100):
            j = client.get(f"/api/bank/import-jobs/{job_id}").json()
            if j["status"] != "running":
                break
            time.sleep(0.05)
        assert j["status"] == "done"
        assert j["result"]["totals"]["imported"] == 1
        assert j["result"]["file_errors"][0]["file"] == "pack.md"
        assert "压缩包" in j["result"]["file_errors"][0]["reason"]


class TestImportBudgetApi:
    def test_llm_call_budget_stops_extract(self, client, fake_llm, monkeypatch):
        """预算闸门先于 LLM 调用：一次都不应真正调用，结果里给出明确错误条目。"""
        monkeypatch.setattr(settings, "import_max_llm_calls", 0)
        resp = client.post(
            "/api/bank/import",
            json={"text": "什么是闭包？\n\n什么是装饰器？", "force_llm_extract": True},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert fake_llm.calls == [], "预算耗尽后不应发起真实 LLM 调用"
        assert any("资源上限" in e["reason"] for e in body["errors"])

    def test_max_questions_default_cap(self, client, fake_llm, monkeypatch):
        """不传 max_questions 时按 import_max_questions 兜底截断。"""
        monkeypatch.setattr(settings, "import_max_questions", 1)
        text = "什么是闭包？\n答案：函数。\n\n什么是装饰器？\n答案：语法糖。"
        resp = client.post("/api/bank/import", json={"text": text})
        assert resp.status_code == 200
        assert len(resp.json()["imported"]) == 1
