"""list_tenders' default expiry filter.

The dashboard has no time window — it asks for the newest 200 rows — so what it
shows shrinks as scrape volume grows. Closed tenders nobody triaged are dropped
so the cap is spent on live ones, but anything the team has touched must survive
however old it is.
"""
import asyncio
import contextlib

import pytest

from database import repository

CLAUSE = "(t.deadline IS NULL OR t.deadline >= NOW() OR t.status <> 'new')"


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


def test_expired_untriaged_tenders_are_hidden_by_default(captured):
    asyncio.run(repository.list_tenders())

    assert CLAUSE in captured["query"]


def test_include_expired_drops_the_filter(captured):
    asyncio.run(repository.list_tenders(include_expired=True))

    assert CLAUSE not in captured["query"]
    assert "WHERE TRUE" in captured["query"]


def test_filter_composes_with_other_conditions_and_keeps_placeholders_aligned(captured):
    # The clause carries no parameter, so $1/$2 must still be the search text
    # and its ILIKE twin rather than being shifted by one.
    asyncio.run(repository.list_tenders(q="fire", limit=25, offset=5))

    assert CLAUSE in captured["query"]
    assert captured["params"] == ("fire", "%fire%", 25, 5)
    assert "websearch_to_tsquery('english', $1)" in captured["query"]
    assert "LIMIT $3 OFFSET $4" in captured["query"]
