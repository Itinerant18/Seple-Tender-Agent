"""LLM-stated date recovery in ScannerOrchestrator._process_raw.

The classifier schema (skills/tender-intelligence/SKILL.md) asks the model to
restate the submission deadline and publication date it sees, but the response
parser used to throw those two fields away. A row the portal field and the
regex both missed therefore kept a NULL deadline, and the 30-day staleness
grace presented an ancient notice as a live Strong Fit — the Bolangir
cash-van tender (closed March 2024, surfaced September 2026).

These tests pin the replacement: an otherwise-undated row adopts the LLM's
stated dates (parsed through the same guards), so the existing is_stale check
closes an expired row at ingest. Rules pinned here:

- portal/regex dates win — the LLM only fills gaps, never overwrites;
- "Not stated" (or any dateless text) changes nothing;
- a stated FUTURE date keeps the row live — recovery must not close what the
  clock says is open.
"""
import uuid
from datetime import datetime

import pytest

# daily_scan imports the Playwright-backed connectors at module load; skip the
# whole module where Playwright isn't installed (the CI unit-test env), while
# still running it in the scanner image where it is.
pytest.importorskip("playwright")

from database.models import (  # noqa: E402
    ConfidenceLevel,
    FitLabel,
    RawTender,
    TenderAnalysis,
    TenderStatus,
)
from scheduler import daily_scan  # noqa: E402
from scheduler.daily_scan import ScannerOrchestrator  # noqa: E402


CASH_VAN_TITLE = (
    "(Technical Bid) TENDER FOR HIRING OF CASH VANS INCLUDING DRIVER "
    "ON MONTHLY RENTAL BASIS FOR USE AT CAC UNDER RBO-V, BOLANGIR"
)


class _FakeClassifier:
    """Stand-in for TenderClassifier returning a fixed LLM restatement."""

    def __init__(self, stated: dict):
        self._stated = dict(stated)

    async def classify(self, raw, document_text=None):
        return TenderAnalysis(
            fit_classification=FitLabel.STRONG_FIT,
            confidence=ConfidenceLevel.HIGH,
            matched_keywords=["cash van"],
            matching_rationale="Strong scope match for cash-in-transit services.",
            raw_analysis=dict(self._stated),
            analysis_model="test-stub",
        )


@pytest.fixture
def stored(monkeypatch):
    """Stub the repository; record what the new-row path persisted."""
    record = {"upserted": None, "digest_queued": [], "tender_id": uuid.uuid4()}

    async def find_by_fingerprint(fingerprint):
        return None  # every row under test is new

    async def get_source_id(name):
        return uuid.uuid4()

    async def upsert_tender(tender):
        record["upserted"] = tender
        return record["tender_id"]

    async def save_analysis(analysis):
        return uuid.uuid4()

    async def queue_digest_tender(tender_id):
        record["digest_queued"].append(tender_id)

    monkeypatch.setattr(daily_scan.repository, "find_by_fingerprint", find_by_fingerprint)
    monkeypatch.setattr(daily_scan.repository, "get_source_id", get_source_id)
    monkeypatch.setattr(daily_scan.repository, "upsert_tender", upsert_tender)
    monkeypatch.setattr(daily_scan.repository, "save_analysis", save_analysis)
    monkeypatch.setattr(daily_scan.repository, "queue_digest_tender", queue_digest_tender)
    return record


def _raw(**overrides) -> RawTender:
    # TenderTiger rows carry no fetchable page of their own (the detail view
    # needs the portal session), so the portal's due field is all the pipeline
    # has until the LLM restates what it can — the exact shape that leaked
    # the Bolangir row.
    payload = dict(
        title=CASH_VAN_TITLE,
        description=CASH_VAN_TITLE,
        tender_reference="TT/CASHVAN/2024/118",
        issuing_authority="Central Warehousing Corporation",
        location="Bolangir, Odisha",
        url="https://www.tendertiger.com/TenderDetail.aspx?t=118",
        source="TenderTiger",
        search_term="cash in transit",
    )
    payload.update(overrides)
    return RawTender(**payload)


@pytest.mark.asyncio
async def test_llm_stated_past_deadline_closes_the_row_at_ingest(stored, monkeypatch):
    orch = ScannerOrchestrator()
    orch.classifier = _FakeClassifier({"submission_deadline": "2024-03-15 14:00"})

    result = await orch._process_raw(_raw())

    assert result is not None
    assert result.deadline == datetime(2024, 3, 15, 14, 0)
    assert result.status == TenderStatus.CLOSED
    assert stored["upserted"].deadline == datetime(2024, 3, 15, 14, 0)
    assert stored["upserted"].status == TenderStatus.CLOSED
    # An expired Strong Fit must never reach the digest queue.
    assert stored["digest_queued"] == []


@pytest.mark.asyncio
async def test_llm_not_stated_leaves_the_row_undated_and_live(stored):
    orch = ScannerOrchestrator()
    orch.classifier = _FakeClassifier({"submission_deadline": "Not stated"})

    result = await orch._process_raw(_raw())

    assert result is not None
    assert result.deadline is None
    assert result.status == TenderStatus.NEW
    assert stored["digest_queued"] == [stored["tender_id"]]


@pytest.mark.asyncio
async def test_portal_deadline_wins_over_the_llm_restatement(stored):
    # The LLM only fills gaps: a date the portal stated (and the parser
    # accepted) is never overwritten by what the model restated.
    orch = ScannerOrchestrator()
    orch.classifier = _FakeClassifier({"submission_deadline": "2024-03-15 14:00"})

    result = await orch._process_raw(_raw(deadline="25-12-2028"))

    assert result.deadline == datetime(2028, 12, 25)
    assert result.status == TenderStatus.NEW
    assert stored["digest_queued"] == [stored["tender_id"]]


@pytest.mark.asyncio
async def test_llm_stated_publication_date_anchors_staleness(stored):
    # No closing date anywhere, but the model restates a 2024 publication
    # date — the no-deadline staleness anchor then closes the row.
    orch = ScannerOrchestrator()
    orch.classifier = _FakeClassifier(
        {"submission_deadline": "Not stated", "publication_date": "2024-01-29"}
    )

    result = await orch._process_raw(_raw())

    assert result is not None
    assert result.deadline is None
    assert result.publication_date is not None
    assert result.publication_date.year == 2024
    assert result.status == TenderStatus.CLOSED
    assert stored["digest_queued"] == []


@pytest.mark.asyncio
async def test_llm_stated_future_deadline_keeps_the_row_live(stored):
    # Recovery must not close what the clock says is open: a stated future
    # date is persisted for the board but the row stays triageable.
    orch = ScannerOrchestrator()
    orch.classifier = _FakeClassifier({"submission_deadline": "2028-03-15"})

    result = await orch._process_raw(_raw())

    assert result.deadline == datetime(2028, 3, 15)
    assert result.status == TenderStatus.NEW
    assert stored["digest_queued"] == [stored["tender_id"]]
