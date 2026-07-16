"""
SEPLE Daily Scan Scheduler
APScheduler-based scheduler for automated tender scraping.
"""
import os
import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)


class DailyScanScheduler:
    """Manages scheduled tender scanning across all connectors."""

    def __init__(self):
        self.scan_hour = int(os.getenv("SCAN_HOUR", "6"))     # Default: 6 AM
        self.scan_minute = int(os.getenv("SCAN_MINUTE", "0"))
        self.is_running = False

    async def run_daily_scan(self):
        """Execute a full scan across all tender sources."""
        logger.info(f"Starting daily tender scan at {datetime.utcnow().isoformat()}")
        self.is_running = True

        results = {
            "started_at": datetime.utcnow().isoformat(),
            "sources_scanned": 0,
            "tenders_found": 0,
            "tenders_new": 0,
            "errors": [],
        }

        try:
            # Import connectors
            from connectors.tender_tiger import TenderTigerConnector
            from connectors.tender247 import Tender247Connector
            from processor.extractor import TenderExtractor
            from processor.deduplicator import TenderDeduplicator

            extractor = TenderExtractor()
            deduplicator = TenderDeduplicator()
            all_tenders = []

            # Scan TenderTiger
            try:
                tiger = TenderTigerConnector()
                # TODO: Initialize Playwright browser here
                # tenders = await tiger.scrape_tenders(page)
                # all_tenders.extend(tenders)
                results["sources_scanned"] += 1
                logger.info("TenderTiger scan complete")
            except Exception as e:
                logger.error(f"TenderTiger scan failed: {e}")
                results["errors"].append({"source": "TenderTiger", "error": str(e)})

            # Scan Tender247
            try:
                t247 = Tender247Connector()
                # TODO: Initialize Playwright browser here
                # tenders = await t247.scrape_tenders(page)
                # all_tenders.extend(tenders)
                results["sources_scanned"] += 1
                logger.info("Tender247 scan complete")
            except Exception as e:
                logger.error(f"Tender247 scan failed: {e}")
                results["errors"].append({"source": "Tender247", "error": str(e)})

            # Process results
            extracted = [extractor.extract_tender_fields(t) for t in all_tenders]
            unique = deduplicator.deduplicate(extracted)

            results["tenders_found"] = len(all_tenders)
            results["tenders_new"] = len(unique)

            # TODO: Store in database
            # TODO: Trigger notifications for high-relevance tenders

            logger.info(
                f"Daily scan complete: {results['tenders_found']} found, "
                f"{results['tenders_new']} new unique tenders"
            )

        except Exception as e:
            logger.error(f"Daily scan failed: {e}")
            results["errors"].append({"source": "scheduler", "error": str(e)})

        finally:
            results["completed_at"] = datetime.utcnow().isoformat()
            self.is_running = False

        return results

    def start(self):
        """Start the scheduler (uses APScheduler if available, else simple loop)."""
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from apscheduler.triggers.cron import CronTrigger

            scheduler = AsyncIOScheduler()
            scheduler.add_job(
                self.run_daily_scan,
                CronTrigger(hour=self.scan_hour, minute=self.scan_minute),
                id="daily_tender_scan",
                name="Daily Tender Scan",
            )
            scheduler.start()
            logger.info(f"Scheduler started — daily scan at {self.scan_hour:02d}:{self.scan_minute:02d} UTC")

        except ImportError:
            logger.warning("APScheduler not installed — run scans manually or install apscheduler")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scheduler = DailyScanScheduler()
    asyncio.run(scheduler.run_daily_scan())
