"""Tests for Tender247 Cloudflare fast-fail detection and API burst reduction."""

import time
from types import SimpleNamespace

import pytest

pytest.importorskip("playwright")

from connectors.tender247 import Tender247Connector  # noqa: E402


class _FakeCloudflarePage:
    def __init__(self, *, title="Tender247", status=200, url="https://www.tender247.com/"):
        self._title = title
        self._status = status
        self.url = url
        self.login_button_queried = False
        self.search_calls = []

    async def goto(self, url, **kwargs):
        return SimpleNamespace(status=self._status)

    async def title(self):
        return self._title

    def get_by_role(self, *args, **kwargs):
        self.login_button_queried = True
        raise AssertionError("get_by_role should not be called after Cloudflare block detection")


def _make_connector(page, tmp_path) -> Tender247Connector:
    conn = Tender247Connector.__new__(Tender247Connector)
    Tender247Connector.__init__(conn)
    conn.email = "user@example.com"
    conn.password = "secret"
    conn.page = page
    conn.context = None
    conn.browser = None
    conn.session_file = tmp_path / "tender247_state.json"

    async def _no_init():
        return None

    conn._init_browser = _no_init
    return conn


@pytest.mark.asyncio
async def test_detect_cloudflare_just_a_moment(tmp_path):
    page = _FakeCloudflarePage(title="Just a moment...", status=403)
    conn = _make_connector(page, tmp_path)

    blocked = await conn._detect_cloudflare_block("homepage load")

    assert blocked is True
    assert "Cloudflare" in conn.login_failure


@pytest.mark.asyncio
async def test_detect_cloudflare_attention_required(tmp_path):
    page = _FakeCloudflarePage(title="Attention Required! | Cloudflare", status=403)
    conn = _make_connector(page, tmp_path)

    blocked = await conn._detect_cloudflare_block("homepage load")

    assert blocked is True
    assert "Cloudflare" in conn.login_failure


@pytest.mark.asyncio
async def test_detect_cloudflare_normal_page(tmp_path):
    page = _FakeCloudflarePage(title="Tender247 - Latest Tenders", status=200)
    conn = _make_connector(page, tmp_path)

    blocked = await conn._detect_cloudflare_block(
        "homepage load", response=SimpleNamespace(status=200)
    )

    assert blocked is False
    assert conn.login_failure is None


@pytest.mark.asyncio
async def test_login_fails_fast_on_cloudflare(tmp_path):
    page = _FakeCloudflarePage(title="Just a moment...", status=403)
    conn = _make_connector(page, tmp_path)

    start = time.monotonic()
    result = await conn.login()
    elapsed = time.monotonic() - start

    assert result is False
    assert elapsed < 1.0
    assert conn.login_failure is not None
    assert "Cloudflare" in conn.login_failure
    assert page.login_button_queried is False


@pytest.mark.asyncio
async def test_login_session_restore_fails_fast_on_cloudflare(tmp_path):
    page = _FakeCloudflarePage(title="Just a moment...", status=403)
    conn = _make_connector(page, tmp_path)
    conn.session_file.write_text("{}", encoding="utf-8")

    start = time.monotonic()
    result = await conn.login()
    elapsed = time.monotonic() - start

    assert result is False
    assert elapsed < 1.0
    assert "Cloudflare" in conn.login_failure


@pytest.mark.asyncio
async def test_scrape_limits_keywords_when_unfiltered_feed_is_large(monkeypatch, tmp_path):
    import connectors.tender247 as t247_mod

    sleep_delays = []

    async def _fast_sleep(delay):
        sleep_delays.append(delay)

    monkeypatch.setattr(t247_mod.asyncio, "sleep", _fast_sleep)

    page = _FakeCloudflarePage(url="https://www.tender247.com/auth/tender")
    search_terms_seen = []

    async def fake_evaluate(script, arg=None):
        if arg is None and "user_query_id" in script:
            return "335599"
        search_terms_seen.append(arg["searchText"])
        if arg["searchText"] == "":
            data = [
                {
                    "tender_id": i,
                    "security_code": f"sec{i}",
                    "requirement_workbrief": f"CCTV Tender {i}",
                    "tender_number": f"T-{i}",
                }
                for i in range(60)
            ]
        else:
            data = []
        return {"status": 200, "success": True, "total": len(data), "data": data}

    page.evaluate = fake_evaluate
    conn = _make_connector(page, tmp_path)
    conn.is_logged_in = True

    keywords = [f"kw{i}" for i in range(12)]
    tenders = await conn.scrape_tenders(keywords=keywords)

    assert len(tenders) == 60
    assert search_terms_seen == ["", "kw0", "kw1", "kw2", "kw3", "kw4"]
    assert all(2.0 <= d <= 4.0 for d in sleep_delays)
