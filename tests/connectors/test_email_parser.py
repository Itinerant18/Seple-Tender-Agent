"""Tests for connectors/email_parser.py (RFC822/HTML parsing and IMAP fetching)."""

import importlib.util
from pathlib import Path

EMAIL_PARSER_PATH = Path(__file__).resolve().parents[2] / "connectors" / "email_parser.py"
spec = importlib.util.spec_from_file_location("email_parser_test_mod", EMAIL_PARSER_PATH)
email_parser_mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(email_parser_mod)

EmailParserConnector = email_parser_mod.EmailParserConnector


def _wrap_multipart(html: str) -> bytes:
    return (
        "From: alerts@tender247.com\r\n"
        "To: team@seple.in\r\n"
        "Subject: Daily Tender247 Alert\r\n"
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/mixed; boundary="OUTER"\r\n\r\n'
        "--OUTER\r\n"
        'Content-Type: multipart/alternative; boundary="INNER"\r\n\r\n'
        "--INNER\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\n"
        "Plain summary\r\n"
        "--INNER\r\n"
        "Content-Type: text/html; charset=utf-8\r\n\r\n"
        f"{html}\r\n"
        "--INNER--\r\n"
        "--OUTER--\r\n"
    ).encode("utf-8")


def test_parses_structured_tender_blocks_across_nested_multipart():
    html = """
    <html><body>
      <table class="tender-block"><tr><td>
        <a class="tender-title" href="https://www.tender247.com/auth/tender/101/abc">CCTV Camera Supply</a>
        <span class="value">Rs. 25 Lakh</span>
        <span class="deadline">30-11-2026</span>
        <span class="authority">PWD Bhopal</span>
      </td></tr></table>
    </body></html>
    """
    parser = EmailParserConnector("Tender247")
    tenders = parser.parse_email_content(_wrap_multipart(html))

    assert len(tenders) == 1
    assert tenders[0].title == "CCTV Camera Supply"
    assert tenders[0].value == "Rs. 25 Lakh"
    assert tenders[0].deadline == "30-11-2026"
    assert tenders[0].issuing_authority == "PWD Bhopal"
    assert tenders[0].url == "https://www.tender247.com/auth/tender/101/abc"


def test_parses_generic_tender247_digest_table_rows_and_deduplicates_links():
    html = """
    <html><body>
      <table>
        <tr>
          <td>
            <a href="https://www.tender247.com/auth/tender/987654/xyz123">
              Installation of IP Surveillance CCTV and Fire Alarm System
            </a>
            | Tender ID: T247-987654
            | Organization: Municipal Corporation Pune
            | Estimated Value: INR 45,00,000
            | Closing Date: 12-12-2026 17:00
            | Location: Pune, Maharashtra
            <a href="https://www.tender247.com/auth/tender/987654/xyz123">View Details</a>
          </td>
        </tr>
        <tr>
          <td>
            <a href="https://www.tender247.com/unsubscribe?token=123">Unsubscribe</a>
          </td>
        </tr>
      </table>
    </body></html>
    """
    parser = EmailParserConnector("Tender247")
    tenders = parser.parse_email_content(_wrap_multipart(html))

    assert len(tenders) == 1
    t = tenders[0]
    assert t.tender_reference == "T247-987654"
    assert "CCTV" in t.title
    assert t.issuing_authority == "Municipal Corporation Pune"
    assert t.value == "INR 45,00,000"
    assert "12-12-2026 17:00" in t.deadline
    assert t.location == "Pune, Maharashtra"
    assert t.source == "Tender247"


def test_imap_config_derives_imap_host_from_smtp_server(monkeypatch):
    monkeypatch.delenv("IMAP_SERVER", raising=False)
    monkeypatch.delenv("IMAP_USER", raising=False)
    monkeypatch.delenv("IMAP_PASS", raising=False)
    monkeypatch.setenv("SMTP_SERVER", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_USER", "bot@example.com")
    monkeypatch.setenv("SMTP_PASS", "app-pass")

    cfg = EmailParserConnector._imap_config()
    assert cfg == {
        "host": "imap.gmail.com",
        "port": 993,
        "user": "bot@example.com",
        "password": "app-pass",
        "folder": "INBOX",
    }


def test_fetch_from_imap_reads_peek_and_deduplicates(monkeypatch):
    monkeypatch.setenv("IMAP_SERVER", "imap.example.com")
    monkeypatch.setenv("IMAP_USER", "bot@example.com")
    monkeypatch.setenv("IMAP_PASS", "secret")

    raw_msg = _wrap_multipart(
        '<a href="https://www.tender247.com/auth/tender/555/sec">Biometric Access Control Tender</a>'
    )

    class _FakeIMAP:
        def __init__(self, host, port, timeout=None):
            self.selected_readonly = False

        def login(self, user, pwd):
            return ("OK", [b"Logged in"])

        def select(self, folder, readonly=False):
            self.selected_readonly = readonly
            return ("OK", [b"1"])

        def search(self, charset, *criteria):
            return ("OK", [b"10 11"])

        def fetch(self, eid, parts):
            assert parts == "(BODY.PEEK[])"
            return ("OK", [(b"1 (BODY[] {100})", raw_msg)])

        def logout(self):
            return ("BYE", [])

    monkeypatch.setattr(email_parser_mod.imaplib, "IMAP4_SSL", _FakeIMAP)

    parser = EmailParserConnector("Tender247")
    tenders = parser.fetch_from_imap(days_back=1)

    assert len(tenders) == 1
    assert tenders[0].tender_reference == "555"
