"""
SEPLE Tender Scheduler — long-running entrypoint for the scanner container.

Scans every day at SCAN_HOUR (7 days/week, PRD §8.4).
Digest goes out on working days only (Mon–Sat); weekend/holiday finds are
persisted in Postgres and roll into the next working-day digest (PRD §8.1).
Instant alerts fire inside run_daily_scan regardless of day.
Milestone reminders (F8) run right after each scan.
"""
import os
import asyncio
import logging
from datetime import datetime, timedelta

from dotenv import load_dotenv

from database import repository
from database.models import Tender
from scheduler.daily_scan import ScannerOrchestrator
from scheduler.milestone_tracker import MilestoneTracker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)

SCAN_HOUR = int(os.getenv("SCAN_HOUR", "6"))
SCAN_MINUTE = int(os.getenv("SCAN_MINUTE", "0"))
RUN_ON_STARTUP = os.getenv("RUN_ON_STARTUP", "true").lower() in ("true", "1", "yes")
WORKING_DAYS = {0, 1, 2, 3, 4, 5}  # Mon–Sat; company holidays roll over manually


def seconds_until_next_run() -> float:
    now = datetime.now()
    nxt = now.replace(hour=SCAN_HOUR, minute=SCAN_MINUTE, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)
    return (nxt - now).total_seconds()


async def run_cycle(*, now: datetime | None = None) -> dict:
    """Run one scan/digest/milestone cycle for workers and cron jobs."""
    orchestrator = ScannerOrchestrator()
    tracker = MilestoneTracker()
    current_time = now or datetime.now()
    scan_succeeded = False
    digest_count = 0

    try:
        await orchestrator.run_daily_scan()
        scan_succeeded = True
    except Exception:
        logger.exception("Daily scan failed")

    if current_time.weekday() in WORKING_DAYS:
        try:
            queued_rows = await repository.list_pending_digest_tenders()
            notification_ids = [
                row["digest_notification_id"] for row in queued_rows
            ]
            tenders = [
                Tender.model_validate({
                    key: value
                    for key, value in row.items()
                    if key != "digest_notification_id"
                })
                for row in queued_rows
            ]
            if tenders and await orchestrator.email.send_digest(tenders):
                await repository.mark_digest_notifications_sent(notification_ids)
                digest_count = len(tenders)
        except Exception:
            logger.exception("Digest send failed; queued tenders remain pending")

    try:
        await tracker.run_checks()
    except Exception:
        logger.exception("Milestone tracker failed")

    return {
        "scan_succeeded": scan_succeeded,
        "digest_count": digest_count,
    }


async def main():
    load_dotenv()
    await repository.init_schema()

    first_run = RUN_ON_STARTUP

    while True:
        if not first_run:
            wait = seconds_until_next_run()
            logger.info("Next scan scheduled in %.0f minutes (at %02d:%02d)", wait / 60, SCAN_HOUR, SCAN_MINUTE)
            await asyncio.sleep(wait)
        else:
            logger.info("RUN_ON_STARTUP enabled — executing initial scan immediately...")
            first_run = False

        await run_cycle()


if __name__ == "__main__":
    asyncio.run(main())
