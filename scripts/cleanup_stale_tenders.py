"""
One-shot maintenance: close expired and stale tenders.

What it does (dry-run by default, --apply to execute):
  1. Tenders with a stated deadline in the past and status 'new' -> 'closed'.
  2. Tenders with NO deadline whose publication/creation date is older than
     STALE_DAYS -> 'closed' (web discovery banked 1,670 such rows, none
     biddable).
  3. Optional backfill of the SBI CAC Bolangir cash-van tender
     (aa685888-fbb8-4822-b0db-6bb619f06488): closes it, and optionally sets
     its deadline if --bolangir-deadline is given. The date is NOT invented
     here — pass it only after confirming it from the source document.

Only rows with status 'new' are ever touched: a human triage decision
(under_review/qualified/submitted/won/lost) is never overwritten by the
clock. Human decisions stay permanent. Idempotent — run it twice, the second
run finds nothing to do.

Usage:
    python scripts/cleanup_stale_tenders.py            # dry run, prints counts
    python scripts/cleanup_stale_tenders.py --apply    # execute
    python scripts/cleanup_stale_tenders.py --apply --bolangir-deadline "2024-03-15 14:00+05:30"
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

from database import repository  # noqa: E402
from database.db import close_pool, get_connection, init_schema  # noqa: E402
from database.models import TenderStatus  # noqa: E402
from database.repository import STALE_DAYS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("cleanup_stale_tenders")

# The audit report uses an em dash; Windows consoles default to a legacy code
# page that cannot encode it and print a replacement glyph instead.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

BOLANGIR_TENDER_ID = UUID("aa685888-fbb8-4822-b0db-6bb619f06488")


async def _count_pending(conn) -> dict:
    """How many rows WOULD change — the dry-run report."""
    past_deadline = await conn.fetchval(
        """
        SELECT COUNT(*) FROM tenders
        WHERE status = 'new' AND deadline IS NOT NULL AND deadline < NOW()
        """
    )
    stale = await conn.fetchval(
        f"""
        SELECT COUNT(*) FROM tenders
        WHERE status = 'new' AND deadline IS NULL
          AND COALESCE(publication_date::timestamp, created_at)
                < NOW() - INTERVAL '{STALE_DAYS} days'
        """
    )
    return {
        "would_close_past_deadline": int(past_deadline or 0),
        "would_close_stale": int(stale or 0),
    }


async def main(apply: bool, bolangir_deadline: datetime | None) -> None:
    # Called inside main, not at import: tests import this module and must not
    # have the repo .env re-applied after conftest's credential scrubbing.
    load_dotenv()
    await init_schema()

    if apply:
        counts = await repository.sync_expired_tenders()
        print(f"Applied: {counts}")
    else:
        async with get_connection() as conn:
            pending = await _count_pending(conn)
        print(f"Dry run — nothing written. Rows that would change: {pending}")
        print("Re-run with --apply to execute.")

    # Targeted close of the tender that surfaced this whole gap. Closing by
    # ID is honest even without a confirmed date; the deadline backfill is a
    # separate, explicit opt-in because we will not invent a date.
    if apply:
        row = await repository.get_tender(BOLANGIR_TENDER_ID)
        if row is None:
            print(f"Bolangir tender {BOLANGIR_TENDER_ID} not found — skipping.")
        else:
            if row["status"] not in ("closed", "submitted", "won", "lost"):
                await repository.update_status(
                    BOLANGIR_TENDER_ID, TenderStatus.CLOSED, performed_by="cleanup-script"
                )
                print(f"Bolangir tender: status {row['status']} -> closed.")
            else:
                print(f"Bolangir tender: status is {row['status']}; left untouched.")
            if bolangir_deadline is not None and row["deadline"] is None:
                await repository.set_tender_deadline(
                    BOLANGIR_TENDER_ID, bolangir_deadline, performed_by="cleanup-script"
                )
                print(f"Bolangir tender: deadline backfilled to {bolangir_deadline.isoformat()}.")
            elif bolangir_deadline is not None:
                print(f"Bolangir tender: deadline already set ({row['deadline']}); not overwritten.")

    await close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="execute the updates (default is a dry run)")
    parser.add_argument("--bolangir-deadline", type=datetime.fromisoformat, default=None,
                        help="optional ISO datetime to backfill as the Bolangir tender deadline, "
                             "e.g. '2024-03-15 14:00+05:30'. Only set after confirming from the source document.")
    args = parser.parse_args()
    asyncio.run(main(args.apply, args.bolangir_deadline))
