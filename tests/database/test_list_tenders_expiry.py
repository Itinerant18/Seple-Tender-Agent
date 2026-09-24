"""list_tenders' expiry filter and the "closing soon" view behind it.

The dashboard is the ACTIVE board in EVERY view: a tender whose deadline has
passed is expired, a tender with no deadline goes stale after STALE_DAYS, and
expired rows are unreachable — there is no flag that reveals them any more.
The old include_expired switch removed the freshness filter entirely and
dumped the full history (years-old notices included) onto the page whenever
the user toggled "closed/expired"; expired tenders must never show, toggle or
not. The toggle is now closing_soon=True: live tenders close to their closing
date (the CLOSING_SOON_DAYS window), with the terminal-status filter lifted so
triaged rows that are still biddable stay visible in the urgent view.

Every row still carries a computed is_expired flag for badging and detail
views.
"""
import asyncio
import contextlib
from datetime import datetime
from uuid import uuid4

import pytest

from database import repository


@pytest.fixture
def captured(monkeypatch):
    """Run list_tenders against a fake connection and keep the SQL it built."""
    seen = {}

    class FakeConn:
        async def fetch(self, query, *params):
            seen["query"] = query
            seen["params"] = params
            return []

    @contextlib.asynccontextmanager
    async def fake_get_connection():
        yield FakeConn()

    monkeypatch.setattr(repository, "get_connection", fake_get_connection)
    return seen


@pytest.fixture
def synced(monkeypatch):
    """Run sync_expired_tenders against a fake connection, capturing its SQL.

    The fakes mirror asyncpg for real: execute() returns a command tag like
    "UPDATE 7", while fetchval() on a bare UPDATE returns None (no result
    rows). Reading the count from the wrong one reports 0 no matter how many
    rows actually changed — which is exactly what shipped once.
    """
    seen = {"queries": []}

    class FakeConn:
        async def execute(self, query, *params):
            seen["queries"].append(query)
            return "UPDATE 7"

        async def fetchval(self, query, *params):
            # None, like asyncpg on an UPDATE without RETURNING.
            seen["queries"].append(query)
            return None

        async def fetch(self, query, *params):
            # the agreement test also runs list_tenders on this connection
            return []

    @contextlib.asynccontextmanager
    async def fake_get_connection():
        yield FakeConn()

    monkeypatch.setattr(repository, "get_connection", fake_get_connection)
    return seen


def test_freshness_and_status_filter_apply_by_default(captured):
    asyncio.run(repository.list_tenders())

    query = captured["query"]
    # both freshness branches: a live deadline, or no deadline but recent
    assert "t.deadline IS NOT NULL AND t.deadline >= NOW()" in query
    assert "COALESCE(t.publication_date::timestamp, t.created_at)" in query
    assert f"INTERVAL '{repository.STALE_DAYS} days'" in query
    assert "t.status NOT IN ('closed', 'lost', 'ignored', 'disqualified')" in query
    # the old escape hatch must be gone: it kept every triaged row visible
    # forever and let NULL-deadline rows through unconditionally
    assert "t.status <> 'new'" not in query
    assert "(t.deadline IS NULL OR t.deadline >= NOW()" not in query


def test_freshness_filter_is_unconditional_no_flag_lifts_it(captured):
    # The board must never show an expired tender — in the default view or any
    # toggled one. This is the regression pin for the old include_expired
    # switch, which removed the freshness filter and flooded the page with
    # years-old notices. If a caller ever legitimately needs the raw history,
    # it gets a different query, never a flag on this one.
    asyncio.run(repository.list_tenders())
    default_query = captured["query"]

    asyncio.run(repository.list_tenders(closing_soon=True))
    closing_soon_query = captured["query"]

    for query in (default_query, closing_soon_query):
        assert repository._ACTIVE_FRESHNESS_SQL in query
        assert "t.deadline IS NOT NULL AND t.deadline >= NOW()" in query
        assert f"INTERVAL '{repository.STALE_DAYS} days'" in query

    # no historical parameter name still reaches the repository
    import inspect

    assert "include_expired" not in inspect.signature(repository.list_tenders).parameters


def test_closing_soon_narrows_to_the_window_and_lifts_the_status_filter(captured):
    asyncio.run(repository.list_tenders(closing_soon=True))

    query = captured["query"]
    assert repository._CLOSING_SOON_SQL in query
    # live rows only, inside the shared closing window
    assert f"INTERVAL '{repository.CLOSING_SOON_DAYS} days'" in query
    assert "t.deadline >= NOW()" in query
    # a triaged row closing tomorrow is still biddable and must appear
    assert "NOT IN ('closed', 'lost', 'ignored', 'disqualified')" not in query


def test_closing_soon_lower_bound_excludes_a_just_expired_row(captured):
    # The window's lower bound is what makes "expired never shows" hold inside
    # the urgent view too: the instant a deadline passes, the row leaves it.
    asyncio.run(repository.list_tenders(closing_soon=True))

    assert repository._CLOSING_SOON_SQL in captured["query"]
    sql = repository._CLOSING_SOON_SQL
    assert ">= NOW()" in sql, "lower bound must exclude deadlines already past"


def test_rows_still_carry_the_is_expired_flag(captured):
    asyncio.run(repository.list_tenders())

    assert "AS is_expired" in captured["query"]


def test_get_tender_carries_is_expired_and_leaves_no_unformatted_placeholder(monkeypatch):
    # The is_expired expression is interpolated into a plain (non-f) string
    # unless the query is built as an f-string — a regression there would send
    # the literal "{_IS_EXPIRED_SQL}" to Postgres.
    queries = []

    class FakeConn:
        async def fetchrow(self, query, *params):
            queries.append(query)
            return None

    @contextlib.asynccontextmanager
    async def fake_get_connection():
        yield FakeConn()

    monkeypatch.setattr(repository, "get_connection", fake_get_connection)
    asyncio.run(repository.get_tender(uuid4()))

    assert queries and "AS is_expired" in queries[0]
    assert "{_IS_EXPIRED_SQL}" not in queries[0]


def test_filter_composes_with_other_conditions_and_keeps_placeholders_aligned(captured):
    # The freshness clause carries no parameter, so $1/$2 must still be the
    # search text and its ILIKE twin rather than being shifted by one.
    asyncio.run(repository.list_tenders(q="fire", limit=25, offset=5))

    assert repository._ACTIVE_FRESHNESS_SQL in captured["query"]
    assert captured["params"] == ("fire", "%fire%", 25, 5)
    assert "websearch_to_tsquery('english', $1)" in captured["query"]
    assert "LIMIT $3 OFFSET $4" in captured["query"]


def test_sync_expired_tenders_closes_only_untriaged_rows(synced):
    counts = asyncio.run(repository.sync_expired_tenders())

    assert counts == {"closed_past_deadline": 7, "closed_stale": 7}
    assert len(synced["queries"]) == 2
    for query in synced["queries"]:
        # human triage decisions are permanent; only 'new' rows are eligible
        assert "status = 'new'" in query
        assert "SET status = 'closed'" in query
        assert "updated_at = NOW()" in query
    # the two statements split the deadline and staleness branches
    assert "deadline IS NOT NULL AND deadline < NOW()" in synced["queries"][0]
    assert "deadline IS NULL" in synced["queries"][1]


def test_rows_are_counted_from_the_command_tag_not_fetchval(synced):
    # asyncpg's execute() reports "UPDATE <n>"; fetchval() on the same bare
    # UPDATE returns None. Counting from the wrong one can only ever say 0.
    assert repository._rows_affected("UPDATE 7") == 7
    assert repository._rows_affected("UPDATE 0") == 0
    assert repository._rows_affected(None) == 0
    assert repository._rows_affected("") == 0


def test_filter_and_sync_agree_on_the_staleness_window(synced):
    # A mismatch would make the board hide rows sync never closes (or vice
    # versa) — both must interpolate the same STALE_DAYS constant.
    asyncio.run(repository.list_tenders())
    asyncio.run(repository.sync_expired_tenders())

    window = f"INTERVAL '{repository.STALE_DAYS} days'"
    assert window in synced["queries"][1]


def test_closing_soon_window_mirrors_the_alert_engine():
    # "Close to closing" must mean the same thing on the board's urgent view
    # and in the short-deadline instant alert, or a tender alerts as urgent and
    # then never shows in the urgent view (or vice versa).
    from notifier.alert_rules import AlertRulesEngine

    assert repository.CLOSING_SOON_DAYS == AlertRulesEngine.SHORT_DEADLINE_DAYS


def test_set_tender_deadline_fills_only_null_and_is_audited(monkeypatch):
    executed = []

    class FakeConn:
        async def execute(self, query, *params):
            executed.append((query, params))
            return "UPDATE 1"

    @contextlib.asynccontextmanager
    async def fake_get_connection():
        yield FakeConn()

    monkeypatch.setattr(repository, "get_connection", fake_get_connection)
    deadline = datetime(2024, 3, 15, 14, 0)
    updated = asyncio.run(
        repository.set_tender_deadline(uuid4(), deadline, performed_by="test")
    )

    assert updated is True
    update_query, _ = executed[0]
    assert "deadline IS NULL" in update_query  # never overwrites a real date
    audit_query, _ = executed[1]
    assert "audit_log" in audit_query
