"""Tests for GeMConnector SCRAPER_PROXY wiring and unreachable-portal error reporting."""

import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

GEM_DIRECT_PATH = Path(__file__).resolve().parents[2] / "connectors" / "gem_direct.py"
spec = importlib.util.spec_from_file_location("gem_direct_proxy_test", GEM_DIRECT_PATH)
gem_direct_module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gem_direct_module)

GeMConnector = gem_direct_module.GeMConnector


def test_proxy_launch_args_none_when_no_env(monkeypatch):
    monkeypatch.delenv("SCRAPER_PROXY", raising=False)
    assert GeMConnector._proxy_launch_args() is None


def test_proxy_launch_args_splits_credentials(monkeypatch):
    monkeypatch.setenv("SCRAPER_PROXY", "http://user:pass@host.example:8080")
    assert GeMConnector._proxy_launch_args() == {
        "server": "http://host.example:8080",
        "username": "user",
        "password": "pass",
    }


def test_proxy_launch_args_no_credentials(monkeypatch):
    monkeypatch.setenv("SCRAPER_PROXY", "http://host.example:8080")
    assert GeMConnector._proxy_launch_args() == {"server": "http://host.example:8080"}


@pytest.mark.asyncio
async def test_scrape_via_api_uses_proxy_env(monkeypatch):
    proxy_url = "http://indian_user:secret@gate.proxy.example:7000"
    monkeypatch.setenv("SCRAPER_PROXY", proxy_url)
    captured_kwargs = {}

    class _FakeResponse:
        def __init__(self, *, text="", json_data=None):
            self.text = text
            self._json = json_data or {}

        def raise_for_status(self):
            return None

        def json(self):
            return self._json

    class _FakeAsyncClient:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)
            self.cookies = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url):
            return _FakeResponse(
                text="<script>'csrf_bd_gem_nk': '252f909c57f2830d492918f83272dde9'</script>"
            )

        async def post(self, url, **kwargs):
            return _FakeResponse(
                json_data={"code": 200, "response": {"response": {"docs": [], "numFound": 0}}}
            )

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    connector = GeMConnector()
    tenders = await connector._scrape_via_api(("cctv",), max_results=10, pages_per_term=1)

    assert tenders == []
    assert captured_kwargs.get("proxy") == proxy_url


@pytest.mark.asyncio
async def test_all_terms_fail_raises(monkeypatch):
    connector = GeMConnector()
    monkeypatch.setattr(
        connector, "_scrape_via_api", AsyncMock(side_effect=RuntimeError("ERR_CONNECTION_REFUSED"))
    )
    monkeypatch.setattr(connector, "_scrape_via_playwright", AsyncMock(return_value=[]))

    with pytest.raises(RuntimeError, match="GeM unreachable"):
        await connector.scrape_tenders(max_results=10)


@pytest.mark.asyncio
async def test_playwright_all_terms_fail_raises(monkeypatch):
    connector = GeMConnector()
    monkeypatch.setattr(connector, "_init_browser", AsyncMock())
    monkeypatch.setattr(
        connector,
        "_search_playwright",
        AsyncMock(side_effect=RuntimeError("net::ERR_CONNECTION_REFUSED")),
    )

    with pytest.raises(RuntimeError, match="All 2 GeM Playwright term queries failed"):
        await connector._scrape_via_playwright(("cctv", "fire"), max_results=10)
