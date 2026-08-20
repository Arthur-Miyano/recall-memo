# -*- coding: utf-8 -*-
"""生成 sample.pdf 的一次性脚本（产物已随仓库提交，测试直接读取，无需重新运行）。

sample.pdf 是手工构造的最小合法 PDF：一页、内置 Helvetica、两行 ASCII 文本。
手工拼而不用 reportlab，是为了不引入测试之外的依赖。需要重新生成时：

    python tests/fixtures/make_sample_pdf.py
"""
from pathlib import Path

LINES = [
    "What is the GIL in CPython?",
    "Answer: The Global Interpreter Lock serializes bytecode execution.",
]


def build_pdf(lines: list[str]) -> bytes:
    ops = ["BT", "/F1 12 Tf", "72 740 Td"]
    for i, line in enumerate(lines):
        if i:
            ops.append("0 -20 Td")
        ops.append(f"({line}) Tj")
    ops.append("ET")
    stream = "\n".join(ops).encode("ascii")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
    xref_pos = len(out)
    n = len(objects) + 1
    out += f"xref\n0 {n}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("ascii")
    out += f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    return bytes(out)


if __name__ == "__main__":
    dest = Path(__file__).with_name("sample.pdf")
    dest.write_bytes(build_pdf(LINES))
    print(f"written {dest} ({dest.stat().st_size} bytes)")
