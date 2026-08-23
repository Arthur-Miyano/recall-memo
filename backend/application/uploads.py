# -*- coding: utf-8 -*-
"""统一上传策略（修复方案 §5.1）：所有上传入口复用本模块，API 不再自行 await file.read()。

职责：
- 分块读取上传内容，按累计大小计，超过上限立即终止（不读完整个文件）；
- 扩展名白名单（.pdf/.md/.txt/.json/.db）；MIME 只作辅助，最终以文件签名为准；
- 明确拒绝压缩格式（zip/gzip/7z/rar 签名），不接受压缩包；
- 数据库上传的 SQLite magic 校验。

校验失败统一抛 UploadRejectedError（携带稳定 code 与对外消息，不含内部细节），
由 main.py 的全局异常处理器映射为 4xx + {error: {code, message}, request_id}。
"""
import os
from typing import Optional

from fastapi import UploadFile

from config import settings

# 扩展名白名单（§5.1）：.db 仅数据库合并导入入口使用
ALLOWED_EXTS = {".pdf", ".md", ".txt", ".json", ".db"}
# 题库文档上传允许的扩展名
DOCUMENT_EXTS = {".pdf", ".md", ".txt", ".json"}

# 压缩格式签名：当前功能不接受压缩包，命中即拒绝（无需解析压缩炸弹）
_ARCHIVE_SIGNATURES = (
    (b"PK\x03\x04", "ZIP"),
    (b"PK\x05\x06", "ZIP"),
    (b"\x1f\x8b", "gzip"),
    (b"7z\xbc\xaf\x27\x1c", "7z"),
    (b"Rar!\x1a\x07", "RAR"),
)

SQLITE_MAGIC = b"SQLite format 3"
_PDF_MAGIC = b"%PDF-"

# 分块读取的块大小（测试可 monkeypatch 调小以验证"超限不读完整个文件"）
_CHUNK = 1024 * 1024


class UploadRejectedError(ValueError):
    """上传未通过策略校验：稳定 code + 对外消息 + HTTP 状态码（均为 4xx）。"""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def check_extension(filename: str, allowed: set[str] = ALLOWED_EXTS) -> str:
    """扩展名白名单校验，返回小写扩展名；不在白名单抛 UNSUPPORTED_FILE_TYPE。"""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in allowed:
        raise UploadRejectedError(
            "UNSUPPORTED_FILE_TYPE",
            f"不支持的文件类型 {ext or '（无扩展名）'}，仅支持 {' / '.join(sorted(allowed))}",
        )
    return ext


def reject_archive(raw: bytes) -> None:
    """按文件签名拒绝压缩格式（zip/gzip/7z/rar），与扩展名无关。"""
    for magic, label in _ARCHIVE_SIGNATURES:
        if raw.startswith(magic):
            raise UploadRejectedError(
                "ARCHIVE_NOT_SUPPORTED",
                f"不支持压缩包（检测到 {label} 格式），请解压后上传原始文件",
            )


async def read_upload(file: UploadFile, max_bytes: Optional[int] = None) -> bytes:
    """分块读取上传内容：按块累计大小，超过上限立即抛 FILE_TOO_LARGE，不再继续读。"""
    limit = settings.upload_max_file_bytes if max_bytes is None else max_bytes
    parts: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise UploadRejectedError(
                "FILE_TOO_LARGE",
                f"文件超过大小上限（{limit // 1024 // 1024} MiB）",
                status=413,
            )
        parts.append(chunk)
    return b"".join(parts)


async def read_upload_batch(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    """批量读取：单批文件数、单文件大小、累计总大小均受限，任一超限整批拒绝。"""
    if len(files) > settings.upload_max_files:
        raise UploadRejectedError(
            "TOO_MANY_FILES",
            f"单批最多上传 {settings.upload_max_files} 个文件（本次 {len(files)} 个）",
        )
    sources: list[tuple[str, bytes]] = []
    total = 0
    for f in files:
        raw = await read_upload(f)
        total += len(raw)
        if total > settings.upload_max_total_bytes:
            raise UploadRejectedError(
                "UPLOAD_TOTAL_TOO_LARGE",
                f"本批上传总大小超过上限（{settings.upload_max_total_bytes // 1024 // 1024} MiB）",
                status=413,
            )
        if raw:
            sources.append((f.filename or "未命名文件", raw))
    return sources


def validate_document_upload(filename: str, raw: bytes) -> str:
    """题库文档上传校验：扩展名白名单 + 压缩签名 + PDF 签名（以签名/解析为准，MIME 仅辅助）。

    通过则返回扩展名；文本类内容以实际 UTF-8 解码为准（在 decode_source_text）。
    """
    ext = check_extension(filename, DOCUMENT_EXTS)
    reject_archive(raw)
    if ext == ".pdf" and not raw.startswith(_PDF_MAGIC):
        raise UploadRejectedError("INVALID_DOCUMENT", "文件内容与扩展名不符（缺少 PDF 文件签名）")
    return ext


def validate_db_upload(filename: str, raw: bytes) -> None:
    """数据库上传校验：.db 扩展名 + 压缩签名 + SQLite magic。"""
    check_extension(filename, {".db"})
    reject_archive(raw)
    if len(raw) < len(SQLITE_MAGIC) or not raw.startswith(SQLITE_MAGIC):
        raise UploadRejectedError(
            "INVALID_DATABASE",
            "文件不是 SQLite 数据库（请使用本工具导出的 .db 备份文件）",
        )


def check_text_length(text: str) -> None:
    """提取文本长度上限（粘贴文本与文件解码文本同口径）。"""
    if len(text) > settings.extract_max_chars:
        raise UploadRejectedError(
            "TEXT_TOO_LARGE",
            f"文本超过上限（{settings.extract_max_chars} 字符），请拆分后分批导入",
            status=413,
        )
