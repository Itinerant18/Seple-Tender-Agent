"""Tests for scripts/sync_tender247_local.py."""

import pytest

from database.models import RawTender
from scripts import ingest_client, sync_tender247_local


def _sample_tender(ref: str = "T247-1") -> RawTender:
    return RawTender(
        title="Supply of Access Control and CCTV",
        tender_reference=ref,
        source="Tender247",
        url="https://www.tender247.com/auth/tender/1/sec",
    )


@pytest.mark.asyncio
async def test_eml_mode_parses_local_file_and_uploads(monkeypatch, tmp_path):
    eml = tmp_path / "alert.html"
    eml.write_text(
        '<a href="https://www.tender247.com/auth/tender/777/tok">'
        "Supply and Commissioning of CCTV Cameras"
        "</a>",
        encoding="utf-8",
    )

    uploaded = {}

    async def _fake_upload(source, tenders, *, api_url, timeout=60):
        uploaded["source"] = source
        uploaded["refs"] = [t.tender_reference for t in tenders]
        uploaded["api_url"] = api_url
        return {"status": "accepted", "received": len(tenders)}

    monkeypatch.setattr(ingest_client, "upload_tenders", _fake_upload)

    result = await sync_tender247_local.run_sync(
        api_url="https://api.seple.in", eml_path=eml, dry_run=False
    )

    assert result == {"status": "accepted", "received": 1}
    assert uploaded == {
        "source": "Tender247",
        "refs": ["777"],
        "api_url": "https://api.seple.in",
    }


@pytest.mark.asyncio
async def test_auto_mode_falls_back_to_imap_when_browser_fails(monkeypatch):
    class _FailingBrowser:
        def __init__(self, **kwargs):
            self.closed = False

        async def scrape_tenders(self, keywords=None):
            raise RuntimeError("Cloudflare 403")

        async def close(self):
            self.closed = True

    class _FakeEmailParser:
        def __init__(self, source_name="Tender247"):
            pass

        @staticmethod
        def _imap_config():
            return {"host": "imap.example.com", "port": 993, "user": "u", "password": "p", "folder": "INBOX"}

        async def scrape_tenders(self, days_back=2):
            return [_sample_tender("T247-EMAIL-1")]

    monkeypatch.setattr(sync_tender247_local, "Tender247Connector", _FailingBrowser)
    monkeypatch.setattr(sync_tender247_local, "EmailParserConnector", _FakeEmailParser)

    result = await sync_tender247_local.run_sync(
        api_url="https://api.seple.in", mode="auto", dry_run=True
    )

    assert result == {"status": "dry_run", "scraped": 1}
