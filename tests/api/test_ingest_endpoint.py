"""Tests for POST /api/tenders/ingest authentication and background batch processing."""

import uuid
from unittest.mock import AsyncMock

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("playwright")

BackgroundTasks = fastapi.BackgroundTasks
HTTPException = fastapi.HTTPException

from api import main  # noqa: E402
from database.models import RawTender  # noqa: E402


def _raw(ref: str = "GEM/2026/B/1") -> RawTender:
    return RawTender(
        title=f"CCTV Tender {ref}",
        tender_reference=ref,
        source="GeM",
        url="https://bidplus.gem.gov.in/showbidDocument/1",
    )


@pytest.mark.asyncio
async def test_ingest_requires_configured_token(monkeypatch):
    monkeypatch.delenv("TENDER_INGEST_TOKEN", raising=False)
    payload = main.TenderIngestRequest(source="GeM", tenders=[_raw()])

    with pytest.raises(HTTPException) as exc_info:
        await main.ingest_tenders(payload, BackgroundTasks(), authorization="Bearer secret")

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_ingest_rejects_missing_or_wrong_bearer_token(monkeypatch):
    monkeypatch.setenv("TENDER_INGEST_TOKEN", "correct-token")
    payload = main.TenderIngestRequest(source="GeM", tenders=[_raw()])

    with pytest.raises(HTTPException) as missing_exc:
        await main.ingest_tenders(payload, BackgroundTasks(), authorization=None)
    assert missing_exc.value.status_code == 401

    with pytest.raises(HTTPException) as wrong_exc:
        await main.ingest_tenders(payload, BackgroundTasks(), authorization="Bearer wrong")
    assert wrong_exc.value.status_code == 403


@pytest.mark.asyncio
async def test_ingest_accepts_valid_batch_and_queues_background_task(monkeypatch):
    monkeypatch.setenv("TENDER_INGEST_TOKEN", "correct-token")
    run_id = uuid.uuid4()
    monkeypatch.setattr(main.repository, "start_scrape_run", AsyncMock(return_value=run_id))

    bg = BackgroundTasks()
    payload = main.TenderIngestRequest(source="GeM", tenders=[_raw("GEM/1"), _raw("GEM/2")])
    result = await main.ingest_tenders(payload, bg, authorization="Bearer correct-token")

    assert result == {
        "status": "accepted",
        "run_id": str(run_id),
        "source": "GeM",
        "received": 2,
    }
    assert len(bg.tasks) == 1
    assert bg.tasks[0].func is main._ingest_batch


@pytest.mark.asyncio
async def test_ingest_batch_processes_rows_and_isolates_row_errors(monkeypatch):
    run_id = uuid.uuid4()
    sync_mock = AsyncMock()
    complete_mock = AsyncMock()
    monkeypatch.setattr(main.repository, "sync_expired_tenders", sync_mock)
    monkeypatch.setattr(main.repository, "complete_scrape_run", complete_mock)

    process_calls = []

    class _FakeOrchestrator:
        async def _process_raw(self, raw):
            process_calls.append(raw.tender_reference)
            if raw.tender_reference == "BAD":
                raise RuntimeError("corrupt row")
            return object()

    monkeypatch.setattr(main, "ScannerOrchestrator", _FakeOrchestrator)

    await main._ingest_batch(run_id, "GeM", [_raw("BAD"), _raw("GOOD")])

    assert process_calls == ["BAD", "GOOD"]
    assert sync_mock.await_count == 2
    complete_mock.assert_awaited_once_with(
        run_id,
        tenders_found=2,
        tenders_new=1,
        duplicates_skipped=1,
        status="completed",
    )


@pytest.mark.asyncio
async def test_ingest_batch_empty_marks_success_no_results(monkeypatch):
    run_id = uuid.uuid4()
    monkeypatch.setattr(main.repository, "sync_expired_tenders", AsyncMock())
    complete_mock = AsyncMock()
    monkeypatch.setattr(main.repository, "complete_scrape_run", complete_mock)
    monkeypatch.setattr(main, "ScannerOrchestrator", lambda: None)

    await main._ingest_batch(run_id, "GeM", [])

    complete_mock.assert_awaited_once_with(
        run_id,
        tenders_found=0,
        tenders_new=0,
        duplicates_skipped=0,
        status="success_no_results",
    )
