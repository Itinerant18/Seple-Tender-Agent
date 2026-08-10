"""
GeM Portal connector via Apify pre-built actor.
GeM has no public API — Apify maintains the scraper.
Cost: ~$0.01 per run — very cheap for daily use.

Mirrors CPPPConnector's interface (async scrape_tenders -> list[RawTender]) so
the daily-scan orchestrator can drive it like every other source.
"""
import asyncio
import logging
from datetime import datetime

from apify_client import ApifyClient
from config.tools import apify_config
from database.models import RawTender

logger = logging.getLogger(__name__)


class GeMConnector:
    source_name = "GeM"

    def __init__(self):
        if not apify_config.api_token:
            logger.warning("APIFY_API_TOKEN not set — GeM connector disabled")
            self.client = None
        else:
            self.client = ApifyClient(apify_config.api_token)

    async def scrape_tenders(self, keywords: list = None, max_results: int = 100) -> list[RawTender]:
        if not self.client:
            return []
        return await asyncio.to_thread(self._run_actor, keywords or [], max_results)

    def _run_actor(self, keywords: list, max_results: int) -> list[RawTender]:
        try:
            logger.info(f"Searching GeM via Apify for: {keywords}")
            # Actor has no keyword search (input is maxTenders/category/ministry),
            # so fetch a page of recent bids and keyword-filter here.
            run = self.client.actor(apify_config.actors["gem_portal"]).call(
                run_input={"maxTenders": max_results}
            )
            if run is None or getattr(run, "status", None) != "SUCCEEDED":
                logger.error(f"Apify GeM run failed: {getattr(run, 'status', 'no run')}")
                return []

            items = list(self.client.dataset(run.default_dataset_id).iterate_items())
            if keywords:
                kw = [k.lower() for k in keywords]
                # ponytail: title/category substring match — recall-first, the
                # classifier does the real filtering downstream.
                items = [
                    it for it in items
                    if any(k in f"{it.get('title','')} {it.get('itemCategory','')}".lower() for k in kw)
                ]

            tenders = [
                RawTender(
                    title=it.get("title") or "Unknown",
                    tender_reference=it.get("bidNumber") or it.get("bid_number") or it.get("tender_id"),
                    value=it.get("estimated_value") or it.get("value"),
                    deadline=it.get("endDate") or it.get("bid_end_date"),
                    publication_date=it.get("startDate") or it.get("published_date"),
                    issuing_authority=it.get("ministry") or it.get("department") or it.get("organization"),
                    location=it.get("location"),
                    category=it.get("itemCategory") or it.get("category"),
                    url=it.get("bidUrl") or it.get("url") or it.get("document_download_url"),
                    source=self.source_name,
                    scraped_at=datetime.utcnow().isoformat(),
                )
                for it in items
            ]
            logger.info(f"GeM returned {len(tenders)} tenders")
            return tenders
        except Exception as e:
            logger.error(f"Apify GeM error: {e}")
            return []

    async def close(self):
        pass
