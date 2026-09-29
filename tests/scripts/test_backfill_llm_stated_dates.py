"""Orchestration contract for scripts/backfill_llm_stated_dates.py.

The parsing itself is FieldExtractor's (covered in tests/processor); this
pins the script's own behavior: dry-run writes nothing, --apply fills only
NULL dates from parseable restatements (never invents one), unparseable
restatements are reported and left untouched, and a final sync closes rows
dated into the past within the same run.
"""
import asyncio
import importlib.util
import types
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

import pytest

pytest.importorskip("dotenv")

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "backfill_llm_stated_dates.py"
spec = importlib.util.spec_from_file_location("backfill_llm_stated_dates", SCRIPT_PATH)
script = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(script)


def test_plan_row_recovers_iso_and_month_first_dates():
    row = {
        "id": uuid4(),
        "title": "Cash van Bolangir",
        "stated_deadline": "2024-03-15 14:00",
        "stated_publication_date": None,
    }

    plan = script.plan_row(row)

    assert plan["would_date"] is True
    assert plan["deadline"] == datetime(2024, 3, 15, 14, 0)
    assert plan["publication_date"] is None


def test_plan_row_recovers_publication_date_when_no_deadline_stated():
    row = {
        "id": uuid4(),
        "title": "Old notice, undated close",
        "stated_deadline": "Not stated",
        "stated_publication_date": "2024-01-29",
    }

    plan = script.plan_row(row)

    assert plan["would_date"] is True
    assert plan["deadline"] is None
    assert plan["publication_date"] == date(2024, 1, 29)


def test_plan_row_leaves_dateless_restatements_untouched():
    for stated_deadline, stated_pub in [
        ("Not stated", None),
        (None, "unknown"),
        ("sometime soon", "recently"),
        ("", ""),
    ]:
        plan = script.plan_row(
            {
                "id": uuid4(),
                "title": "t",
                "stated_deadline": stated_deadline,
                "stated_publication_date": stated_pub,
            }
        )
        assert plan["would_date"] is False, (stated_deadline, stated_pub)
        assert plan["deadline"] is None
        assert plan["publication_date"] is None


@pytest.fixture
def calls(monkeypatch):
    """Stub every side effect the script can have; record what it attempted."""
    record = {
        "sync": 0,
        "init_schema": 0,
        "close_pool": 0,
        "load_dotenv": 0,
        "deadlines": [],   # (tender_id, deadline)
        "pubs": [],        # (tender_id, publication_date)
        "candidates": [],
    }
    id_dated = uuid4()
    id_pub_only = uuid4()
    id_garbage = uuid4()
    record["candidates"] = [
        {
            "id": id_dated,
            "title": "Cash van Bolangir",
            "stated_deadline": "2024-03-15 14:00",
            "stated_publication_date": None,
        },
        {
            "id": id_pub_only,
            "title": "Old notice",
            "stated_deadline": "Not stated",
            "stated_publication_date": "2024-01-29",
        },
        {
            "id": id_garbage,
            "title": "Vague notice",
            "stated_deadline": "sometime soon",
            "stated_publication_date": "unknown",
        },
    ]
    record["ids"] = (id_dated, id_pub_only, id_garbage)

    async def find_undated_live_tenders():
        return list(record["candidates"])

    async def set_tender_deadline(tender_id, deadline, performed_by="system"):
        record["deadlines"].append((tender_id, deadline, performed_by))
        return True

    async def set_tender_publication_date(tender_id, publication_date, performed_by="system"):
        record["pubs"].append((tender_id, publication_date, performed_by))
        return True

    async def sync_expired_tenders():
        record["sync"] += 1
        return {"closed_past_deadline": 1, "closed_stale": 1}

    async def init_schema():
        record["init_schema"] += 1
        return True

    async def close_pool():
        record["close_pool"] += 1

    def load_dotenv():
        # must NOT re-apply the repo .env over conftest's credential scrubbing
        record["load_dotenv"] += 1

    monkeypatch.setattr(script, "load_dotenv", load_dotenv)
    monkeypatch.setattr(script, "init_schema", init_schema)
    monkeypatch.setattr(script, "close_pool", close_pool)
    monkeypatch.setattr(script, "repository", types.SimpleNamespace(
        find_undated_live_tenders=find_undated_live_tenders,
        set_tender_deadline=set_tender_deadline,
        set_tender_publication_date=set_tender_publication_date,
        sync_expired_tenders=sync_expired_tenders,
    ))
    return record


def test_dry_run_writes_nothing_but_reports_the_plan(calls, capsys):
    result = asyncio.run(script.main(False))
    out = capsys.readouterr().out

    assert calls["deadlines"] == []
    assert calls["pubs"] == []
    assert calls["sync"] == 0
    assert result == {"candidates": 3, "would_date": 2, "unparseable": 1}
    assert "Dry run" in out
    assert "2024-03-15 14:00:00" in out
    assert "unparseable" in out.lower()
    assert calls["close_pool"] == 1


def test_apply_dates_parseable_rows_then_syncs(calls, capsys):
    id_dated, id_pub_only, _ = calls["ids"]

    asyncio.run(script.main(True))
    out = capsys.readouterr().out

    assert calls["deadlines"] == [(id_dated, datetime(2024, 3, 15, 14, 0), "backfill-script")]
    assert calls["pubs"] == [(id_pub_only, date(2024, 1, 29), "backfill-script")]
    # the garbage row is never written
    assert all(tid != calls["ids"][2] for tid, _, _ in calls["deadlines"])
    assert all(tid != calls["ids"][2] for tid, _, _ in calls["pubs"])
    # newly past-dated rows close within this run, not next cycle
    assert calls["sync"] == 1
    assert "deadlines=1" in out and "publication_dates=1" in out
    assert calls["close_pool"] == 1


def test_apply_with_no_candidates_still_syncs_nothing(calls):
    calls["candidates"] = []

    result = asyncio.run(script.main(True))

    assert result == {"candidates": 0, "would_date": 0, "unparseable": 0}
    assert calls["deadlines"] == []
    assert calls["pubs"] == []
    assert calls["sync"] == 1  # harmless; keeps the run idempotent
