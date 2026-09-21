"""生成一个最小的「文本型」PDF，用于 PDF 阅读器端到端测试。

不依赖任何第三方库：直接手写 PDF 语法（Helvetica 字体 + 若干文本行）。
用法：  python tools/make-test-pdf.py
产物：  tests/fixtures/sample.pdf
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tests" / "fixtures" / "sample.pdf"

LINES = [
    (72, 720, "The quick brown fox jumps over the lazy dog."),
    (72, 690, "A dictionary rewards curiosity and serendipity."),
    (72, 660, "This page exists only for hovering tests."),
]


def content_stream() -> bytes:
    parts = ["BT", "/F1 14 Tf", "16 TL", "72 720 Td"]
    for i, (_, _, text) in enumerate(LINES):
        if i:
            parts.append("T*")
        parts.append("(%s) Tj" % text.replace("(", r"\(").replace(")", r"\)"))
    parts.append("ET")
    return "\n".join(parts).encode("latin-1")


def build_pdf() -> bytes:
    stream = content_stream()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"

    xref_at = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += b"%010d 00000 n \n" % off
    out += (
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objects) + 1, xref_at)
    )
    return bytes(out)


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(build_pdf())
    print("written:", OUT, OUT.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
