"""Backfill plumbing for undated live rows + a digest that never sends dead rows.

Two halves of the same backlog problem: rows the pipeline could not date sit
on the board on the staleness grace (and in the digest queue), because the
LLM's restated dates were thrown away at ingest. repository gained
find_undated_live_tenders / set_tender_publication_date so a maintenance
script can apply the stored restatements, and list_pending_digest_tenders now
expires + filters anything the clock or a human already killed — a tender
queued while live must not go out after it dies before send day.
"""
import asyncio
import contextlib
from datetime import date, datetime
from uuid import uuid4

import pytest

from database import repository


@pytest.fixture
def fake_conn(monkeypatch):
    """Fake asyncpg connection capturing every statement."""
    seen = {"execute": [], "fetch": [], "fetchval": [], "fetchrow": []}
    rows = {"fetch": []}

    class FakeConn:
        async def execute(self, query, *params):
            seen["execute"].append((query, params))
            return rows.get("execute_result", "UPDATE 0")

        async def fetch(self, query, *params):
            seen["fetch"].append((query, params))
            return list(rows["fetch"])

        async def fetchval(self, query, *params):
            seen["fetchval"].append((query, params))
            return None

        async def fetchrow(self, query, *params):
            seen["fetchrow"].append((query, params))
            return None

    @contextlib.asynccontextmanager
    async def fake_get_connection():
        yield FakeConn()

    monkeypatch.setattr(repository, "get_connection", fake_get_connection)
    return seen, rows


def test_find_undated_live_tenders_reads_only_new_undated_rows_with_restatements(
    fake_conn,
):
    seen, rows = fake_conn
    stated = {
        "id": uuid4(),
        "title": "Cash van tender",
        "source_name": "TenderTiger",
        "stated_deadline": "2024-03-15 14:00",
        "stated_publication_date": None,
    }
    rows["fetch"] = [stated]

    found = asyncio.run(repository.find_undated_live_tenders())

    assert found == [stated]
    (query, params), = seen["fetch"]
    assert params == ()
    # only untriaged rows are eligible — a human decision is never revisited
    assert "t.status = 'new'" in query
    assert "t.deadline IS NULL" in query
    # the evidence comes from the latest stored analysis, both restated fields
    assert "tender_analysis" in query
    assert "raw_analysis->>'submission_deadline'" in query
    assert "raw_analysis->>'publication_date'" in query


def test_set_tender_publication_date_fills_only_null_and_is_audited(fake_conn):
    seen, rows = fake_conn
    rows["execute_result"] = "UPDATE 1"
    tid = uuid4()

    updated = asyncio.run(
        repository.set_tender_publication_date(tid, date(2024, 1, 29), performed_by="test")
    )

    assert updated is True
    assert len(seen["execute"]) == 2
    update_query, update_params = seen["execute"][0]
    assert "publication_date IS NULL" in update_query  # never overwrites
    assert update_params == (tid, date(2024, 1, 29))
    audit_query, audit_params = seen["execute"][1]
    assert "audit_log" in audit_query
    assert audit_params[0] == "backfill_publication_date"


def test_set_tender_publication_date_noop_without_audit(fake_conn):
    seen, rows = fake_conn
    rows["execute_result"] = "UPDATE 0"

    updated = asyncio.run(
        repository.set_tender_publication_date(uuid4(), date(2024, 1, 29))
    )

    assert updated is False
    assert len(seen["execute"]) == 1  # the UPDATE only; no audit row


def test_digest_expires_past_deadline_stale_and_terminal_rows(fake_conn):
    seen, rows = fake_conn
    rows["fetch"] = []

    asyncio.run(repository.list_pending_digest_tenders())

    updates = [q for q, _ in seen["execute"]]
    assert len(updates) == 2
    # the original past-deadline expiry keeps its message
    assert "Tender deadline has passed" in updates[0]
    assert "t.deadline IS NOT NULL" in updates[0]
    assert "t.deadline < NOW()" in updates[0]
    # the new branch kills stale undated rows and triaged-away rows
    assert "closed" in updates[1] and "disqualified" in updates[1]
    assert "COALESCE(t.publication_date::timestamp, t.created_at)" in updates[1]
    assert repository._STALE_CUTOFF_SQL in updates[1]
    for query in updates:
        assert "n.status = 'pending'" in query  # sent rows are never revisited


def test_digest_select_sends_only_live_untriaged_rows(fake_conn):
    seen, rows = fake_conn
    rows["fetch"] = []

    asyncio.run(repository.list_pending_digest_tenders())

    (query, _), = seen["fetch"]
    # the board's own freshness predicate — digest and board agree on "live"
    assert repository._ACTIVE_FRESHNESS_SQL in query
    assert "t.status NOT IN ('closed', 'lost', 'ignored', 'disqualified')" in query
    # the old NULL-deadline free pass must be gone: an undated stale row used
    # to sail through this filter straight into the email
    assert "(t.deadline IS NULL OR t.deadline >= NOW())" not in query


def test_set_tender_deadline_still_fills_only_null(fake_conn):
    # The backfill script leans on both setters; the deadline half's contract
    # (pinned in test_list_tenders_expiry) must hold here too.
    seen, rows = fake_conn
    rows["execute_result"] = "UPDATE 1"
    tid = uuid4()

    updated = asyncio.run(
        repository.set_tender_deadline(tid, datetime(2024, 3, 15, 14, 0))
    )

    assert updated is True
    update_query, update_params = seen["execute"][0]
    assert "deadline IS NULL" in update_query
    assert update_params == (tid, datetime(2024, 3, 15, 14, 0))
