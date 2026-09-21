"""Behavior tests for the Tender247 login hardening.

Covers the 21-09-2026 outage: a month-old expired storage_state left the
hydrated SPA in a state where the "Log in" click never landed, the click used
the 30s page default with no retry, and the source failed for the day with a
message that read as a credentials verdict.

These tests exercise login() for real (real method flow) against fake pages,
so they fail if the flow is wired wrong — not if the portal's markup changes.
"""

import pytest

pytest.importorskip("playwright")

from connectors.tender247 import Tender247Connector  # noqa: E402


class _FakeContext:
    """Records clear_cookies()/storage_state() so tests can assert both."""

    def __init__(self):
        self.cookies_cleared = 0
        self.storage_state_paths = []

    async def clear_cookies(self):
        self.cookies_cleared += 1

    async def storage_state(self, path=None):
        self.storage_state_paths.append(path)


class _FakeLocator:
    def __init__(self, *, fail_first_n=0):
        self.fail_first_n = fail_first_n
        self.clicks = 0

    @property
    def first(self):
        # The connector chains `.first` on role locators; the fake is already
        # the single element, so self is the right answer.
        return self

    async def wait_for(self, state=None, timeout=None):
        return None

    async def click(self, timeout=None):
        self.clicks += 1
        if self.clicks <= self.fail_first_n:
            raise TimeoutError(f"click {self.clicks} timed out")


class _FakeEmailBox:
    async def wait_for(self, state=None, timeout=None):
        return None

    async def fill(self, value):
        return None


class _FakePage:
    """Minimal page double: goto() walks a scripted URL list, get_by_role()
    hands out scripted locators, wait_for_url() simulates a successful redirect.
    Optional localStorage values script the feed-readiness poll."""

    def __init__(self, urls_after_goto=None, *, login_clicks_fail=False,
                 fail_click_once=False, local_storage=None):
        self._urls_after_goto = list(urls_after_goto or [])
        self.url = "about:blank"
        self.evaluated = []
        self.filled = []
        self._login_clicks_fail = login_clicks_fail
        self._fail_click_once = fail_click_once
        self._local_storage = dict(local_storage or {})

    async def goto(self, url, **kwargs):
        if self._urls_after_goto:
            self.url = self._urls_after_goto.pop(0)
        else:
            self.url = url
        return None

    def get_by_role(self, role, name=None, exact=False):
        if name == "Log in":
            # Scripted: optionally fail the first click only (transient), or
            # fail every click (persistent outage).
            fail_first_n = 10**9 if self._login_clicks_fail else (1 if self._fail_click_once else 0)
            return _FakeLocator(fail_first_n=fail_first_n)
        if name == "SUBMIT":
            return _FakeLocator()
        raise AssertionError(f"unexpected get_by_role(role={role!r}, name={name!r})")

    def locator(self, selector):
        return _FakeEmailBox()

    async def fill(self, selector, value):
        self.filled.append((selector, value))

    async def evaluate(self, script):
        self.evaluated.append(script)
        # Feed-readiness poll reads localStorage via a getter script.
        if "user_query_id" in script:
            return self._local_storage.get("user_query_id")
        return None

    async def wait_for_url(self, pattern, timeout=None):
        self.url = "https://www.tender247.com/auth/tender"


def _connector(page: _FakePage, context: _FakeContext, tmp_path) -> Tender247Connector:
    conn = Tender247Connector.__new__(Tender247Connector)
    Tender247Connector.__init__(conn)
    conn.email = "user@example.com"
    conn.password = "secret"
    conn.page = page
    conn.context = context
    conn.browser = None
    conn.session_file = tmp_path / "tender247_state.json"

    async def _no_init():
        return None

    conn._init_browser = _no_init
    return conn


@pytest.mark.asyncio
async def test_session_restore_success_returns_without_clearing_state(tmp_path):
    """A live persisted session must NOT have its cookies/localStorage wiped —
    only the expired path may clear state."""
    context = _FakeContext()
    page = _FakePage(urls_after_goto=["https://www.tender247.com/auth/tender"])
    conn = _connector(page, context, tmp_path)
    conn.session_file.write_text("{}", encoding="utf-8")  # restore path is taken

    result = await conn.login()

    assert result is True
    assert conn.is_logged_in is True
    assert context.cookies_cleared == 0
    assert page.evaluated == []


@pytest.mark.asyncio
async def test_expired_session_clears_state_before_fresh_login(tmp_path):
    """Session restore fails → cookies + localStorage are wiped before the
    fresh-login attempt (the 21-09-2026 outage root cause)."""
    context = _FakeContext()
    page = _FakePage(urls_after_goto=[
        "https://www.tender247.com/",  # /auth/tender redirect while expired
        "https://www.tender247.com/",  # homepage for the fresh login
    ], login_clicks_fail=True)  # fresh login can't complete on the fake page
    conn = _connector(page, context, tmp_path)
    conn.session_file.write_text("{}", encoding="utf-8")

    result = await conn.login()

    assert result is False
    assert context.cookies_cleared == 1
    assert any("localStorage.clear" in script for script in page.evaluated)


@pytest.mark.asyncio
async def test_transient_click_failure_is_retried(tmp_path):
    """One swallowed click (SPA re-render) must not fail the source: the retry
    lands, the flow completes, and the session is persisted."""
    context = _FakeContext()
    page = _FakePage(fail_click_once=True)
    conn = _connector(page, context, tmp_path)

    result = await conn.login()

    assert result is True
    assert conn.is_logged_in is True
    assert context.storage_state_paths == [str(conn.session_file)]


@pytest.mark.asyncio
async def test_persistent_click_failure_records_precise_reason(tmp_path):
    """A click that never lands must reach scrape_runs as the precise cause —
    never as a generic 'check credentials' verdict."""
    context = _FakeContext()
    page = _FakePage(login_clicks_fail=True)
    conn = _connector(page, context, tmp_path)

    result = await conn.login()

    assert result is False
    assert "click failed after retry" in conn.login_failure
    assert "TimeoutError" in conn.login_failure

    # scrape_tenders surfaces the precise login_failure on the scrape run.
    msg = None
    try:
        await conn.scrape_tenders()
    except RuntimeError as e:
        msg = str(e)
    assert msg is not None
    assert conn.login_failure in msg
    assert "check credentials" not in msg


@pytest.mark.asyncio
async def test_missing_credentials_fail_fast(tmp_path):
    conn = Tender247Connector.__new__(Tender247Connector)
    Tender247Connector.__init__(conn)
    conn.email = None
    conn.password = None

    result = await conn.login()

    assert result is False


@pytest.mark.asyncio
async def test_scrape_waits_for_feed_ready_and_raises_when_it_never_arrives(tmp_path):
    """A fresh login without 'user_query_id' must NOT silently return an empty
    feed — scrape_tenders polls for it and fails loudly when it never shows up."""
    context = _FakeContext()
    page = _FakePage(local_storage={})  # 'user_query_id' never appears
    conn = _connector(page, context, tmp_path)
    conn.is_logged_in = True
    conn.page.url = "https://www.tender247.com/auth/tender"

    with pytest.raises(RuntimeError, match="feed not ready"):
        await conn.scrape_tenders()


@pytest.mark.asyncio
async def test_scrape_proceeds_once_feed_is_ready(tmp_path):
    """With 'user_query_id' present, the readiness poll passes and the search
    loop runs (empty here because the fake evaluate returns no rows)."""
    context = _FakeContext()
    page = _FakePage(local_storage={"user_query_id": "335599"})
    conn = _connector(page, context, tmp_path)
    conn.is_logged_in = True
    conn.page.url = "https://www.tender247.com/auth/tender"

    async def fake_search(arg):
        return {"status": 200, "success": True, "total": 0, "data": []}

    async def fake_evaluate(script, arg=None):
        if "user_query_id" in script:
            return page._local_storage.get("user_query_id")
        return await fake_search(arg)

    page.evaluate = fake_evaluate

    tenders = await conn.scrape_tenders()

    assert tenders == []  # ran the loop without the readiness error
