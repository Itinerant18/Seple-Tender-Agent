"""Ingest -> extract -> patch -> close, end to end against a real PostgreSQL.

Every link has its own unit test; this pins the CHAIN, because the bug that
actually shipped lived in the seam between two links. The extractor could read
the closing date straight off the BHEL page, but the duplicate path returned
before the fetch, so that date never reached patch_missing_fields(). The row
stayed undated, the freshness filter called it fresh (created_at was yesterday),
and sync_expired_tenders() had nothing to close — a February-2024 notice sat on
the September-2026 board as a live opportunity.

Opt-in: set TENDER_E2E_DATABASE_URL to a PostgreSQL DSN allowed to CREATE
DATABASE. The test builds its own throwaway database on that server and drops
it afterwards, so the `tenders` database itself is never touched. It skips when
the variable is absent (the hermetic runner only forwards it deliberately).
"""
import asyncio
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.parse import urlsplit, urlunsplit

import pytest

pytest.importorskip("asyncpg")
# scheduler.daily_scan imports the Playwright-backed connectors at module load.
pytest.importorskip("playwright")

from database import repository  # noqa: E402
from database.db import close_pool, init_schema  # noqa: E402
from database.models import RawTender, Tender, TenderStatus  # noqa: E402
from processor import Deduplicator  # noqa: E402
from processor.extractor import FieldExtractor  # noqa: E402
from scheduler import daily_scan  # noqa: E402
from scheduler.daily_scan import ScannerOrchestrator  # noqa: E402

BHEL_URL = (
    "https://www.bhel.com/supply-fire-detection-and-suppression-system-vande-bharat"
)

# The notice's date block, verbatim. The tender-document SALE cutoff is printed
# above the bid deadline — the ordering that made first-match-wins store the
# wrong date.
BHEL_NOTICE = (
    "NIT_79772 NOTIFICATION NO. 2024_BHEL_32399_1 (SGNICVB010) "
    "PUBLISH DATE 29-01-2024 "
    "TENDER TITLE Supply of Fire Detection and Suppression system for Vande Bharat "
    "CLOSING DATE OF SALE FROM 29-02-2024 12:01:09 PM "
    "CLOSING DATE OF SUBMISSION FORM 29-02-2024 06:00:09 PM "
    "TENDER OPENING DATE 01-03-2024 01:30:09 PM"
)


def _raw() -> RawTender:
    # tender_reference left NULL on purpose: that is how the scanner first saw
    # this row (the reference is filled in later from the page), and it is what
    # makes the fingerprint the fallback title hash rather than md5(reference) —
    # the exact shape that reproduced the bug.
    return RawTender(
        title="Supply of Fire Detection and Suppression system for Vande Bharat",
        description="NIT_79772 ; TENDER TITLE, Supply of Fire Detection ...",
        source="WebSearch",
        url=BHEL_URL,
    )


def _is_past(moment: datetime) -> bool:
    return moment < (datetime.now(moment.tzinfo) if moment.tzinfo else datetime.now())


def _url_with_database(dsn: str, dbname: str) -> str:
    parts = urlsplit(dsn)
    return urlunsplit((parts.scheme, parts.netloc, "/" + dbname, parts.query, ""))


async def _run_chain() -> None:
    raw = _raw()
    fingerprint = Deduplicator.generate_fingerprint(raw)

    # 1. ingest — the row exactly as a scan first stores it: undated, 'new'.
    tender_id = await repository.upsert_tender(
        Tender(
            fingerprint=fingerprint,
            title=raw.title,
            description=raw.description,
            source_id=await repository.get_source_id(raw.source),
            source_url=raw.url,
            status=TenderStatus.NEW,
            scraped_at=datetime.now(timezone.utc),
        )
    )
    stored = await repository.get_tender(tender_id)
    assert stored["deadline"] is None
    assert stored["status"] == "new"

    # An undated row created yesterday passes the freshness filter, so it is on
    # the ACTIVE board right now — the exact shape that leaked the 2024 notice.
    active_ids = {r["id"] for r in await repository.list_tenders(limit=100)}
    assert tender_id in active_ids

    # 2. extract — the submission cutoff wins over the sale cutoff printed
    #    above it. Asserted on the raw capture, which has no timezone in it.
    assert FieldExtractor().extract_all(BHEL_NOTICE)["deadline"] == "29-02-2024 06:00"

    # 3. patch — the scanner's own duplicate path, with the page fetch stubbed.
    #    This is the seam the old code missed: it returned before this fetch.
    with patch.object(
        daily_scan,
        "scrape_page",
        side_effect=lambda url: {"markdown": BHEL_NOTICE, "engine": "plain"},
    ):
        result = await ScannerOrchestrator()._process_raw(raw)
    assert result is None  # duplicate → patched in place, not re-inserted

    async with repository.get_connection() as conn:
        rows = await conn.fetchval(
            "SELECT COUNT(*) FROM tenders WHERE fingerprint = $1", fingerprint
        )
    assert rows == 1, "the patch must not have inserted a second row"

    patched = await repository.get_tender(tender_id)
    assert patched["deadline"] is not None
    assert patched["deadline"].year == 2024  # the 2024 notice, not a 2026 guess
    assert _is_past(patched["deadline"])  # …and already expired
    assert patched["status"] == "new"  # nobody has closed it yet

    # 4. close — the next sync must find it, and must COUNT it (an UPDATE has
    #    no result rows, so reading the count from fetchval() reported 0).
    assert await repository.sync_expired_tenders() == {
        "closed_past_deadline": 1,
        "closed_stale": 0,
    }

    # 5. read path — off the active board in EVERY view (expired rows are
    #    unreachable through the list endpoint now; the old include_expired
    #    flag used to hand them back as "history"), but the detail read still
    #    carries the row, badged, so its record survives.
    final = await repository.get_tender(tender_id)
    assert final["status"] == "closed"
    assert final["is_expired"] is True

    active_ids = {r["id"] for r in await repository.list_tenders(limit=100)}
    assert tender_id not in active_ids

    closing_soon_ids = {
        r["id"] for r in await repository.list_tenders(closing_soon=True, limit=100)
    }
    assert tender_id not in closing_soon_ids


@pytest.mark.asyncio
async def test_expired_web_row_is_ingested_extracted_patched_and_closed(monkeypatch):
    admin_dsn = os.environ.get("TENDER_E2E_DATABASE_URL")
    if not admin_dsn:
        pytest.skip(
            "set TENDER_E2E_DATABASE_URL to a PostgreSQL DSN (needs CREATEDB) "
            "to run the expiry-chain E2E"
        )

    import asyncpg

    dbname = f"tender_e2e_{uuid.uuid4().hex[:12]}"
    # Never the real database — this test drops what it creates.
    assert dbname != "tenders" and not dbname.startswith("tenders")

    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        await admin.close()

    monkeypatch.setenv("DATABASE_URL", _url_with_database(admin_dsn, dbname))
    try:
        await close_pool()  # any pool bound to the previous URL must go
        assert await init_schema(), "schema.sql must apply to a fresh database"
        await _run_chain()
    finally:
        await close_pool()
        admin = await asyncpg.connect(admin_dsn)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
        finally:
            await admin.close()
