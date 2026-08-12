"""
CPPP / eProcure connector via Apify pre-built actor.
Actor covers CPPP plus IOCL, state and defence portals — no login needed.
Verified live 22-07-2026: actor jungle_synthesizer/india-eprocure-tender-scraper,
input {maxItems, portals, keywords}, output fields as mapped below.
"""
import asyncio
import logging
from datetime import datetime

from apify_client import ApifyClient
from config.tools import apify_config
from database.models import RawTender

logger = logging.getLogger(__name__)


class CPPPConnector:
    source_name = "CPPP"

    def __init__(self):
        if not apify_config.api_token:
            logger.warning("APIFY_API_TOKEN not set — CPPP connector disabled")
            self.client = None
        else:
            self.client = ApifyClient(apify_config.api_token)

    async def scrape_tenders(self, keywords: list = None, max_results: int = 200) -> list[RawTender]:
        """Fetch CPPP tenders matching keywords. Actor supports keyword search natively."""
        if not self.client:
            return []
        # apify_client is sync; keep the pipeline's async interface
        return await asyncio.to_thread(self._run_actor, keywords or [], max_results)

    def _run_actor(self, keywords: list, max_results: int) -> list[RawTender]:
        try:
            logger.info(f"Searching CPPP via Apify for: {keywords}")
            run = self.client.actor(apify_config.actors["cppp_portal"]).call(
                run_input={
                    "maxItems": max_results,
                    "portals": ["CPPP"],
                    "keywords": keywords,
                }
            )
            if run is None or getattr(run, "status", None) != "SUCCEEDED":
                logger.error(f"Apify CPPP run failed: {getattr(run, 'status', 'no run')}")
                return []
            tenders = []
            for it in self.client.dataset(run.default_dataset_id).iterate_items():
                tenders.append(RawTender(
                    title=it.get("title", "Unknown"),
                    tender_reference=it.get("tender_id"),
                    value=it.get("estimated_value"),
                    deadline=it.get("bid_submission_end"),
                    publication_date=it.get("published_date"),
                    issuing_authority=it.get("organization"),
                    location=it.get("location"),
                    category=it.get("product_category") or it.get("tender_category"),
                    url=it.get("document_download_url"),
                    source=self.source_name,
                    scraped_at=datetime.utcnow().isoformat(),
                ))
            logger.info(f"CPPP returned {len(tenders)} tenders")
            return tenders
        except Exception as e:
            # Raise, don't swallow: daily_scan wraps each source separately and
            # records the reason on the scrape run. Returning [] here made an
            # exhausted Apify quota look identical to "no matching tenders".
            logger.error(f"Apify CPPP error: {e}")
            raise

    async def close(self):
        pass
