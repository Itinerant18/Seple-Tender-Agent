"""Orchestration contract for scripts/cleanup_stale_tenders.py.

The heavy lifting lives in repository.sync_expired_tenders (covered in
tests/database); this pins the script's own behavior: dry-run writes nothing,
--apply closes but never overwrites human triage, and the Bolangir deadline
backfill only happens when explicitly asked with a flag.
"""
import asyncio
import contextlib
import importlib.util
import types
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

pytest.importorskip("dotenv")

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "cleanup_stale_tenders.py"
spec = importlib.util.spec_from_file_location("cleanup_stale_tenders", SCRIPT_PATH)
script = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(script)


@pytest.fixture
def calls(monkeypatch):
    """Stub every side effect the script can have; record what it attempted."""
    record = {
        "sync": 0,
        "init_schema": 0,
        "close_pool": 0,
        "status": [],      # (tender_id, status, performed_by)
        "deadline": [],    # (tender_id, deadline)
        "fetched": [],
        "load_dotenv": 0,
    }
    tender = {"value": None}

    async def sync_expired_tenders():
        record["sync"] += 1
        return {"closed_past_deadline": 3, "closed_stale": 4}

    async def init_schema():
        record["init_schema"] += 1
        return True

    async def close_pool():
        record["close_pool"] += 1

    async def get_tender(tender_id):
        record["fetched"].append(tender_id)
        return tender["value"]

    async def update_status(tender_id, status, performed_by="system"):
        record["status"].append((tender_id, status, performed_by))

    async def set_tender_deadline(tender_id, deadline, performed_by="system"):
        record["deadline"].append((tender_id, deadline))
        return True

    def load_dotenv():
        # must NOT re-apply the repo .env over conftest's credential scrubbing
        record["load_dotenv"] += 1

    class _DryConn:
        async def fetchval(self, query, *params):
            record["dry_fetchval"] = record.get("dry_fetchval", 0) + 1
            return 11

    def get_connection():
        @contextlib.asynccontextmanager
        async def _ctx():
            yield _DryConn()

        return _ctx()

    monkeypatch.setattr(script, "load_dotenv", load_dotenv)
    monkeypatch.setattr(script, "init_schema", init_schema)
    monkeypatch.setattr(script, "close_pool", close_pool)
    monkeypatch.setattr(script, "get_connection", get_connection)
    monkeypatch.setattr(script, "repository", types.SimpleNamespace(
        sync_expired_tenders=sync_expired_tenders,
        get_tender=get_tender,
        update_status=update_status,
        set_tender_deadline=set_tender_deadline,
    ))
    record["tender"] = tender
    return record


def test_apply_runs_sync_closes_bolangir_and_closes_pools(calls, capsys):
    calls["tender"]["value"] = {"id": None, "status": "new", "deadline": None}

    asyncio.run(script.main(True, None))
    out = capsys.readouterr().out

    assert calls["load_dotenv"] == 1  # called inside main(), never at import
    assert calls["sync"] == 1
    assert "Applied: {'closed_past_deadline': 3, 'closed_stale': 4}" in out
    assert calls["fetched"] == [script.BOLANGIR_TENDER_ID]
    tid, status, performed_by = calls["status"][0]
    assert tid == script.BOLANGIR_TENDER_ID
    assert status.value == "closed"
    assert performed_by == "cleanup-script"
    # no flag given → the deadline is never invented
    assert calls["deadline"] == []
    assert calls["close_pool"] == 1


def test_dry_run_writes_nothing(calls, capsys):
    asyncio.run(script.main(False, None))
    out = capsys.readouterr().out

    assert calls["sync"] == 0
    assert calls["status"] == []
    assert calls["deadline"] == []
    assert calls["fetched"] == []
    assert "Dry run" in out
    assert "would_close_stale" in out
    assert calls["close_pool"] == 1


def test_human_triaged_status_is_never_overwritten(calls):
    for status in ("submitted", "won", "lost", "closed"):
        calls["tender"]["value"] = {"id": None, "status": status, "deadline": None}
        asyncio.run(script.main(True, None))
        assert calls["status"] == [], status


def test_untriaged_bolangir_row_is_closed(calls):
    calls["tender"]["value"] = {"id": None, "status": "new", "deadline": None}

    asyncio.run(script.main(True, None))

    assert len(calls["status"]) == 1


def test_deadline_backfill_only_when_flag_given(calls):
    deadline = datetime.fromisoformat("2024-03-15 14:00+05:30")
    calls["tender"]["value"] = {"id": None, "status": "new", "deadline": None}

    asyncio.run(script.main(True, deadline))

    assert calls["deadline"] == [(script.BOLANGIR_TENDER_ID, deadline)]


def test_existing_deadline_is_never_overwritten_by_the_flag(calls):
    deadline = datetime.fromisoformat("2024-03-15 14:00+05:30")
    calls["tender"]["value"] = {
        "id": None,
        "status": "new",
        "deadline": "2026-01-01 10:00+00:00",
    }

    asyncio.run(script.main(True, deadline))

    assert calls["deadline"] == []


def test_missing_bolangir_row_is_reported_not_fatal(calls, capsys):
    calls["tender"]["value"] = None

    asyncio.run(script.main(True, None))

    out = capsys.readouterr().out
    assert "not found" in out
    assert calls["status"] == []
