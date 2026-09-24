"""Scrape chain: local PDF extraction.

Government notices are mostly PDFs; _plain_http used to reject binary content
types outright, and the chain fell through to paid engines that 401/403'd — so
PDF-backed rows arrived with no text, no deadline, and were judged on title
alone. pdfplumber ships in the scanner image (requirements.custom.txt), so the
extraction is local and free.
"""
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("httpx")  # module-level import of scrape_chain

# Load the module directly: importing `connectors` runs connectors/__init__.py,
# which pulls in every connector (including playwright-backed ones).
SCRAPE_CHAIN_PATH = Path(__file__).resolve().parents[2] / "connectors" / "scrape_chain.py"
spec = importlib.util.spec_from_file_location("scrape_chain_module", SCRAPE_CHAIN_PATH)
scrape_chain = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(scrape_chain)

pytest.importorskip("pdfplumber")  # scanner image dep; absent in slim CI → skip


def _minimal_pdf(text: str) -> bytes:
    """Hand-rolled single-page PDF with computed xref offsets — no extra deps."""
    stream = f"BT /F1 12 Tf 40 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
         b"/Resources << /Font << /F1 5 0 R >> >> >>"),
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF").encode()
    return bytes(out)


class _FakePdfResponse:
    def __init__(self, content: bytes, content_type: str = "application/pdf"):
        self.content = content
        self.headers = {"content-type": content_type}

    @staticmethod
    def raise_for_status():
        return None


def test_pdf_text_is_extracted_locally():
    text = scrape_chain._pdf_text(
        _minimal_pdf("Last date of submission: 15.03.2024"),
        "https://example.gov.in/notice.pdf",
    )

    assert text is not None
    assert "15.03.2024" in text


def test_plain_http_routes_pdf_content_type_to_extraction(monkeypatch):
    pdf = _minimal_pdf("Bid Submission End Date : 25-08-2026 15:00")
    monkeypatch.setattr(
        scrape_chain.httpx, "get", lambda *a, **k: _FakePdfResponse(pdf)
    )

    text = scrape_chain._plain_http("https://example.gov.in/files/notice.pdf")

    assert text is not None
    assert "25-08-2026" in text


def test_pdf_url_suffix_routes_even_without_a_pdf_content_type(monkeypatch):
    # Many .nic.in / .gov.in servers serve PDFs as octet-stream.
    pdf = _minimal_pdf("Closing Date: 30-Aug-2026")
    monkeypatch.setattr(
        scrape_chain.httpx,
        "get",
        lambda *a, **k: _FakePdfResponse(pdf, content_type="application/octet-stream"),
    )

    text = scrape_chain._plain_http("https://example.gov.in/tender.PDF?x=1")

    assert text is not None
    assert "30-Aug-2026" in text


def test_garbage_bytes_yield_none_not_a_crash():
    # The rung must fall through to the paid engines, never raise.
    assert scrape_chain._pdf_text(b"not a pdf", "https://x/y.pdf") is None


def test_textless_pdf_extracts_nothing_and_returns_none():
    # A scanned/image-only PDF yields no text layer → None → fall through,
    # same as any other unreadable page.
    assert scrape_chain._pdf_text(
        _minimal_pdf(""), "https://x/scan.pdf"
    ) is None


def test_non_pdf_binary_content_type_still_falls_through(monkeypatch):
    monkeypatch.setattr(
        scrape_chain.httpx,
        "get",
        lambda *a, **k: _FakePdfResponse(b"PK\x03\x04", content_type="application/zip"),
    )

    assert scrape_chain._plain_http("https://x/y.bin") is None
