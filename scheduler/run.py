"""
SEPLE Tender Scheduler — long-running entrypoint for the scanner container.

Scans every day at SCAN_HOUR (7 days/week, PRD §8.4).
Digest goes out on working days only (Mon–Sat); weekend/holiday finds
roll into the next working-day digest (PRD §8.1). Instant alerts fire
inside run_daily_scan regardless of day.
Milestone reminders (F8) run right after each scan.
"""
import os
import asyncio
import logging
from datetime import datetime, timedelta

from dotenv import load_dotenv

from database import repository
from scheduler.daily_scan import ScannerOrchestrator
from scheduler.milestone_tracker import MilestoneTracker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

SCAN_HOUR = int(os.getenv("SCAN_HOUR", "6"))
SCAN_MINUTE = int(os.getenv("SCAN_MINUTE", "0"))
WORKING_DAYS = {0, 1, 2, 3, 4, 5}  # Mon–Sat; company holidays roll over manually


def seconds_until_next_run() -> float:
    now = datetime.now()
    nxt = now.replace(hour=SCAN_HOUR, minute=SCAN_MINUTE, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)
    return (nxt - now).total_seconds()


async def main():
    load_dotenv()
    await repository.init_schema()

    orchestrator = ScannerOrchestrator()
    tracker = MilestoneTracker()
    # ponytail: in-memory rollover — pending weekend tenders are lost on container
    # restart (they were still instant-alerted). Persist a digest_sent flag in DB
    # if that ever bites.
    pending_digest = []

    while True:
        wait = seconds_until_next_run()
        logger.info("Next scan in %.0f minutes", wait / 60)
        await asyncio.sleep(wait)

        try:
            pending_digest.extend(await orchestrator.run_daily_scan())
        except Exception:
            logger.exception("Daily scan failed")

        if pending_digest and datetime.now().weekday() in WORKING_DAYS:
            try:
                if await orchestrator.email.send_digest(pending_digest):
                    pending_digest = []
            except Exception:
                logger.exception("Digest send failed; will retry next run")

        try:
            await tracker.run_checks()
        except Exception:
            logger.exception("Milestone tracker failed")


if __name__ == "__main__":
    asyncio.run(main())
