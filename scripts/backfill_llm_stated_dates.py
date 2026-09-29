"""
One-shot maintenance: date the undated live rows from their stored LLM restatements.

What it does (dry-run by default, --apply to execute):
  1. Finds tenders with status 'new' and a NULL deadline whose latest analysis
     restated a submission_deadline and/or publication_date
     (repository.find_undated_live_tenders).
  2. Parses each stated value through the normal FieldExtractor guards —
     "Not stated" and dateless strings parse to None and change nothing.
  3. With --apply: fills the NULL deadline and/or NULL publication date
     (never overwrites), then runs sync_expired_tenders() so rows dated into
     the past close immediately instead of lingering on the board.

Why this exists: the classifier schema has always asked the model to restate
the dates it sees, but until the ingest recovery landed those fields were
thrown away. Rows stored before that kept a NULL deadline and lived on the
board on the 30-day staleness grace — including long-closed notices the
portals surface as fresh discoveries (e.g. the Bolangir cash-van tender,
closed March 2024, surfaced September 2026). This script applies the same
recovery to the backlog: zero LLM cost, zero network, dates only ever come
from what the model already restated.

Only rows with status 'new' are ever touched: a human triage decision
(under_review/qualified/submitted/won/lost) is never overwritten by the
clock. Idempotent — run it twice, the second run finds nothing to do.

Usage:
    python scripts/backfill_llm_stated_dates.py           # dry run, prints the plan
    python scripts/backfill_llm_stated_dates.py --apply   # execute
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

from database import repository  # noqa: E402
from database.db import close_pool, init_schema  # noqa: E402

# Loaded by path, not via `processor`: importing the package runs
# processor/__init__.py, which pulls pdfplumber and the whole agent router —
# unavailable in minimal envs (and unneeded here; extractor.py itself needs
# only dateutil). tests/processor/test_date_parsing.py loads it the same way
# for the same reason.
import importlib.util as _importlib_util  # noqa: E402

_EXTRACTOR_SPEC = _importlib_util.spec_from_file_location(
    "tender_field_extractor",
    Path(__file__).resolve().parents[1] / "processor" / "extractor.py",
)
assert _EXTRACTOR_SPEC is not None and _EXTRACTOR_SPEC.loader is not None
_extractor_module = _importlib_util.module_from_spec(_EXTRACTOR_SPEC)
_EXTRACTOR_SPEC.loader.exec_module(_extractor_module)
FieldExtractor = _extractor_module.FieldExtractor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("backfill_llm_stated_dates")

# The audit report uses an em dash; Windows consoles default to a legacy code
# page that cannot encode it and print a replacement glyph instead.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def plan_row(row: dict) -> dict:
    """Decide what a backfill would do for one undated row.

    Pure function of the stored restatement — kept separate from main() so
    the contract is unit-testable without a database.
    """
    stated_deadline = row.get("stated_deadline") or ""
    stated_pub = row.get("stated_publication_date") or ""
    deadline = FieldExtractor.parse_datetime(stated_deadline)
    publication_date = FieldExtractor.parse_date(stated_pub)
    return {
        "id": row["id"],
        "title": row.get("title"),
        "stated_deadline": row.get("stated_deadline"),
        "stated_publication_date": row.get("stated_publication_date"),
        "deadline": deadline,
        "publication_date": publication_date,
        "would_date": deadline is not None or publication_date is not None,
    }


async def main(apply: bool) -> dict:
    # Called inside main, not at import: tests import this module and must not
    # have the repo .env re-applied after conftest's credential scrubbing.
    load_dotenv()
    await init_schema()

    rows = await repository.find_undated_live_tenders()
    plans = [plan_row(row) for row in rows]
    dated = [p for p in plans if p["would_date"]]
    unparseable = [p for p in plans if not p["would_date"]]

    if apply:
        n_deadlines = 0
        n_pubs = 0
        for p in dated:
            tid = UUID(str(p["id"]))
            if p["deadline"] is not None:
                if await repository.set_tender_deadline(
                    tid, p["deadline"], performed_by="backfill-script"
                ):
                    n_deadlines += 1
            if p["publication_date"] is not None:
                if await repository.set_tender_publication_date(
                    tid, p["publication_date"], performed_by="backfill-script"
                ):
                    n_pubs += 1
        # Rows dated into the past close here, within this run — not whenever
        # the next scheduled cycle happens to sync.
        counts = await repository.sync_expired_tenders()
        print(f"Applied: deadlines={n_deadlines} publication_dates={n_pubs} sync={counts}")
    else:
        print(f"Dry run — nothing written. Undated live rows with a restatement: {len(plans)}")
        for p in dated:
            print(
                f"  would date {p['id']} {p['title']!r}: "
                f"deadline={p['deadline']} publication_date={p['publication_date']}"
            )
        if unparseable:
            print(
                f"Stated but unparseable ({len(unparseable)} — left untouched, "
                "needs a source-document check):"
            )
            for p in unparseable:
                print(
                    f"  {p['id']} {p['title']!r}: "
                    f"deadline={p['stated_deadline']!r} "
                    f"publication_date={p['stated_publication_date']!r}"
                )
        print("Re-run with --apply to execute.")

    await close_pool()
    return {
        "candidates": len(plans),
        "would_date": len(dated),
        "unparseable": len(unparseable),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="execute the updates (default is a dry run)")
    args = parser.parse_args()
    asyncio.run(main(args.apply))
