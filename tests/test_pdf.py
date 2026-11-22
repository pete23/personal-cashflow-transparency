import shutil

import pytest

from cashflow import pdf
from cashflow.pdf import pdf_to_text

# Synthetic statement: description column on the left, amounts right-aligned in
# two columns, positioned independently as they are in real bank PDFs.
FONT_SIZE = 10
CHAR_WIDTH = FONT_SIZE * 0.6  # Courier is monospaced at 600/1000 em
ROWS = [
    ("Date      Details", "Paid out", "Paid in"),
    ("01 Jan 26 COFFEE SHOP", "2.55", ""),
    ("02 Jan 26 SALARY", "", "1,234.56"),
    ("03 Jan 26 RENT", "1,000.00", ""),
]
OUT_RIGHT, IN_RIGHT = 350, 450


def write_pdf(path, items):
    """Write a one-page PDF placing each (x, y, text) in Courier."""
    stream = "".join(f"BT /F1 {FONT_SIZE} Tf {x} {y} Td ({text}) Tj ET\n" for x, y, text in items).encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 400] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    path.write_bytes(bytes(out))


@pytest.fixture
def statement(tmp_path):
    items = []
    for i, (details, paid_out, paid_in) in enumerate(ROWS):
        y = 350 - i * 20
        items.append((50, y, details))
        for text, right in ((paid_out, OUT_RIGHT), (paid_in, IN_RIGHT)):
            if text:
                items.append((right - len(text) * CHAR_WIDTH, y, text))
    path = tmp_path / "statement.pdf"
    write_pdf(path, items)
    return path


def right_edge(line, token):
    return line.index(token) + len(token)


def assert_columns_preserved(text):
    """Each amount ends within a couple of characters of its own column header's right edge.

    Extractors place text by where it starts, so right-aligned amounts of different
    widths can drift by a character; real statements' columns are far wider apart.
    """
    lines = {row[0].split()[-1]: line for row in ROWS for line in text.splitlines() if row[0].split()[-1] in line}
    out_edge = right_edge(lines["Details"], "Paid out")
    in_edge = right_edge(lines["Details"], "Paid in")
    assert in_edge - out_edge > 4
    for key, amount, edge in (("SHOP", "2.55", out_edge), ("RENT", "1,000.00", out_edge), ("SALARY", "1,234.56", in_edge)):
        assert abs(right_edge(lines[key], amount) - edge) <= 2, (amount, lines[key])


def test_pdf_to_text_preserves_columns(statement):
    assert_columns_preserved(pdf_to_text(statement))


@pytest.mark.skipif(shutil.which("gs") is None, reason="Ghostscript not installed")
def test_falls_back_to_ghostscript_when_pdfplumber_fails(statement, monkeypatch):
    def broken(path):
        raise ValueError("boom")

    monkeypatch.setattr(pdf, "_pdfplumber_text", broken)
    assert_columns_preserved(pdf_to_text(statement))


def test_reports_missing_ghostscript(statement, monkeypatch):
    monkeypatch.setattr(pdf, "_pdfplumber_text", lambda path: "")
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="Ghostscript"):
        pdf_to_text(statement)
