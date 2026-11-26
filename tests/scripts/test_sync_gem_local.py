"""Tests for scripts/sync_gem_local.py."""

import pytest

from database.models import RawTender
from scripts import ingest_client, sync_gem_local


def _sample_tender() -> RawTender:
    return RawTender(
        title="Supply and Installation of CCTV System",
        tender_reference="GEM/2026/B/9999999",
        deadline="2026-12-05T14:00:00Z",
        source="GeM",
        url="https://bidplus.gem.gov.in/showbidDocument/9999999",
    )


class _FakeGeMConnector:
    source_name = "GeM"

    def __init__(self):
        self.closed = False

    async def scrape_tenders(self, max_results: int = 300):
        return [_sample_tender()]

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_dry_run_skips_upload_without_token(monkeypatch):
    monkeypatch.delenv("TENDER_INGEST_TOKEN", raising=False)
    fake = _FakeGeMConnector()
    monkeypatch.setattr(sync_gem_local, "GeMConnector", lambda: fake)

    result = await sync_gem_local.run_sync(
        api_url="https://api.seple.in", max_results=50, dry_run=True
    )

    assert result == {"status": "dry_run", "scraped": 1}
    assert fake.closed is True


@pytest.mark.asyncio
async def test_sync_requires_ingest_token(monkeypatch):
    monkeypatch.delenv("TENDER_INGEST_TOKEN", raising=False)
    fake = _FakeGeMConnector()
    monkeypatch.setattr(sync_gem_local, "GeMConnector", lambda: fake)

    with pytest.raises(RuntimeError, match="TENDER_INGEST_TOKEN"):
        await sync_gem_local.run_sync(
            api_url="https://api.seple.in", max_results=50, dry_run=False
        )
    assert fake.closed is True


@pytest.mark.asyncio
async def test_sync_posts_serialized_tenders_with_bearer_token(monkeypatch):
    monkeypatch.setenv("TENDER_INGEST_TOKEN", "my-secret-token")
    fake = _FakeGeMConnector()
    monkeypatch.setattr(sync_gem_local, "GeMConnector", lambda: fake)
    posted = {}

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "accepted", "run_id": "abc", "source": "GeM", "received": 1}

    class _FakeAsyncClient:
        def __init__(self, **kwargs):
            posted["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, *, json=None, headers=None):
            posted["url"] = url
            posted["json"] = json
            posted["headers"] = headers
            return _FakeResponse()

    monkeypatch.setattr(ingest_client.httpx, "AsyncClient", _FakeAsyncClient)

    result = await sync_gem_local.run_sync(
        api_url="https://api.seple.in/", max_results=50, dry_run=False
    )

    assert result["status"] == "accepted"
    assert posted["url"] == "https://api.seple.in/api/tenders/ingest"
    assert posted["headers"] == {"Authorization": "Bearer my-secret-token"}
    assert posted["json"]["source"] == "GeM"
    assert len(posted["json"]["tenders"]) == 1
    assert posted["json"]["tenders"][0]["tender_reference"] == "GEM/2026/B/9999999"
