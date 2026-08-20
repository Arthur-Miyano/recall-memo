# -*- coding: utf-8 -*-
"""文档解析 adapter：上传文件 → 纯文本。

.pdf 用 pypdf 逐页提取；.md/.txt/.json 按 UTF-8 解码。
解析失败统一抛 HTTPException 400（调用方即 HTTP 层，直接透传给客户端）。
"""
import io
import os

from fastapi import HTTPException

# 按文本读取的扩展名；.pdf 走 pypdf 提取
TEXT_EXTS = {".md", ".txt", ".json"}


def extract_pdf_text(raw: bytes) -> str:
    """pypdf 提取 PDF 全文（逐页拼接）。失败/无文本抛 HTTPException 400。"""
    from pypdf import PdfReader  # 延迟导入：PDF 是可选路径，不影响文本导入
    try:
        reader = PdfReader(io.BytesIO(raw))
        pages = [(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:  # 损坏/加密/非 PDF 内容等统一归为无法解析
        raise HTTPException(status_code=400, detail=f"PDF 解析失败：{exc}")
    text = "\n\n".join(p for p in pages if p.strip())
    if not text.strip():
        raise HTTPException(status_code=400, detail="PDF 中未提取到文本（可能是扫描件或图片型 PDF）")
    return text


def decode_source_text(filename: str, raw: bytes) -> tuple[str, bool]:
    """按扩展名提取文本：.pdf 走 pypdf（需强制 LLM 提取），.md/.txt/.json 直接解码。

    返回 (文本, 是否强制 LLM 提取)：PDF 提取出的文本没有「答案：」标签行，
    规则分段会把正文段落当成题干，故 .pdf 一律强制走 LLM 结构化提取真问题。
    """
    ext = os.path.splitext(filename or "")[1].lower()
    if ext == ".pdf":
        return extract_pdf_text(raw), True
    if ext in TEXT_EXTS:
        try:
            return raw.decode("utf-8"), False
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail=f"{filename}：文本解码失败（请使用 UTF-8 编码）")
    raise HTTPException(
        status_code=400,
        detail=f"{filename}：不支持的文件类型 {ext or '（无扩展名）'}，仅支持 .pdf / .md / .txt / .json",
    )
