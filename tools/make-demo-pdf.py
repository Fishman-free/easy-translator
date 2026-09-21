"""生成商店截图用的演示 PDF（版面更像一份真实的英文文档）。

用法：  python tools/make-demo-pdf.py
产物：  store/demo.pdf
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "store" / "demo.pdf"

TITLE = "On the Value of a Slow Dictionary"
BODY = [
    "Reading in a foreign language is an exercise in patience. The eye",
    "moves quickly, the mind lags behind, and an unfamiliar word can halt",
    "the whole sentence. A dictionary that interrupts this rhythm costs",
    "more than it gives.",
    "",
    "The best tools of this kind are almost invisible. They wait at the",
    "edge of your attention, offer a definition when curiosity appears, and",
    "then disappear. Nothing is copied, nothing is saved, and nothing is",
    "uploaded; the reader simply keeps reading.",
    "",
    "Consider the word deliberate. Seen once, it is a small puzzle; seen",
    "three times, in three different sentences, it becomes part of your",
    "vocabulary. That slow accumulation is the whole point of practice.",
]


def content_stream() -> bytes:
    parts = ["BT", "/F1 20 Tf", "60 720 Td", "(%s) Tj" % TITLE, "ET"]
    parts.append("BT /F1 11 Tf 24 TL 60 680 Td")
    for i, line in enumerate(BODY):
        if i:
            parts.append("T*")
        if line:
            parts.append("(%s) Tj" % line.replace("(", r"\(").replace(")", r"\)"))
    parts.append("ET")
    return "\n".join(parts).encode("latin-1")


def build() -> bytes:
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
    out += b"xref\n0 %d\n" % (len(objects) + 1) + b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref_at)
    return bytes(out)


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(build())
    print("written:", OUT, OUT.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
