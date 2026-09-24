"""Duplicate-row deadline backfill in ScannerOrchestrator._process_raw.

A web-discovered row stored before its portal's closing-date label matched
DEADLINE_PATTERN keeps a NULL deadline forever if the duplicate path skips the
page fetch — patch_missing_fields() is then handed parse(raw.deadline), which is
NULL for every web row. That is how the BHEL notice closing 29-02-2024 sat on a
2026 board as an undated row: no deadline to expire it, and a freshly-discovered
created_at that kept it inside the staleness window.

These tests pin the replacement — the fetch happens before the duplicate check,
but only for a row that would otherwise stay undated, and the parsed date
reaches patch_missing_fields().
"""
import asyncio
from datetime import datetime

import pytest

# daily_scan imports the Playwright-backed connectors at module load; skip the
# whole module where Playwright isn't installed (the CI unit-test env), while
# still running it in the scanner image where it is.
pytest.importorskip("playwright")

from database.models import RawTender  # noqa: E402
from scheduler import daily_scan  # noqa: E402


# The real BHEL notice: closing date present on the page, absent from the row.
BHEL_PAGE = """NIT_79772 NOTIFICATION NO. 2024_BHEL_32399_1 (SGNICVB010)
PUBLISH DATE 29-01-2024
TENDER TITLE Supply of Fire Detection and Suppression system for Vande Bharat
CLOSING DATE OF SALE FROM 29-02-2024 12:01:09 PM
CLOSING DATE OF SUBMISSION FORM 29-02-2024 06:00:09 PM"""


@pytest.fixture
def seen(monkeypatch):
    """Stub the repository and the page fetch; record what the dup path did."""
    record = {"patch": None, "scrape_calls": 0, "existing": {}, "markdown": BHEL_PAGE}

    async def find_by_fingerprint(fingerprint):
        return record["existing"] or None

    async def patch_missing_fields(fingerprint, deadline=None, category=None, location=None):
        record["patch"] = {"deadline": deadline, "category": category, "location": location}
        return True

    def scrape_page(url):
        record["scrape_calls"] += 1
        return {"markdown": record["markdown"], "engine": "plain"}

    monkeypatch.setattr(daily_scan.repository, "find_by_fingerprint", find_by_fingerprint)
    monkeypatch.setattr(daily_scan.repository, "patch_missing_fields", patch_missing_fields)
    monkeypatch.setattr(daily_scan, "scrape_page", scrape_page)
    return record


def _raw(**overrides) -> RawTender:
    payload = dict(
        title="Supply of Fire Detection and Suppression system for Vande Bharat",
        source="WebSearch",
        url="https://www.bhel.com/supply-fire-detection-and-suppression-system-vande-bharat",
        description="NIT_79772 ; TENDER TITLE, Supply of Fire Detection ...",
        tender_reference="2024_BHEL_32399_1",
    )
    payload.update(overrides)
    return RawTender(**payload)


@pytest.mark.asyncio
async def test_existing_undated_web_row_is_backfilled_from_the_page(seen):
    seen["existing"] = {"id": "stored", "deadline": None}

    result = await daily_scan.ScannerOrchestrator()._process_raw(_raw())

    assert result is None                    # still a duplicate; nothing new stored
    assert seen["scrape_calls"] == 1         # the dup path DOES fetch the page now
    # 06:00 is the CLOSING DATE OF SUBMISSION FORM — the bid deadline — not the
    # 12:01 sale cutoff printed above it on the same notice.
    assert seen["patch"]["deadline"] == datetime(2024, 2, 29, 6, 0)


@pytest.mark.asyncio
async def test_row_that_already_has_a_deadline_costs_no_fetch(seen):
    # Once backfilled, re-scanning must not re-fetch: a stable corpus is one
    # request per still-undated row per scan, not one per row per scan.
    seen["existing"] = {"id": "stored", "deadline": datetime(2026, 10, 1, 0, 0)}

    await daily_scan.ScannerOrchestrator()._process_raw(_raw())

    assert seen["scrape_calls"] == 0
    assert seen["patch"]["deadline"] is None  # nothing to backfill


@pytest.mark.asyncio
async def test_aggregator_duplicates_never_fetch(seen):
    # Only web rows lack a deadline of their own; TenderTiger/Tender247/GeM
    # duplicates must stay free of network I/O exactly as before.
    seen["existing"] = {"id": "stored", "deadline": None}

    await daily_scan.ScannerOrchestrator()._process_raw(
        _raw(source="TenderTiger", url="https://example.gov.in/t/1")
    )

    assert seen["scrape_calls"] == 0


@pytest.mark.asyncio
async def test_new_web_row_with_no_deadline_and_no_reference_is_still_gated(seen):
    # The gate sits after the dedupe check; hoisting the fetch above it must not
    # let an undated listing page reach the classifier and the database.
    seen["existing"] = {}
    seen["markdown"] = "Tenders index page. Nothing actionable listed here."

    orch = daily_scan.ScannerOrchestrator()
    result = await orch._process_raw(_raw(tender_reference=None))

    assert result is None
    assert orch._web_gate_drops == 1
