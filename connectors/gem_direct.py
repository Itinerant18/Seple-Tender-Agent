"""
GeM Portal connector via Apify pre-built actor.
GeM has no public API — Apify maintains the scraper.
Cost: ~$0.01 per run — very cheap for daily use.
"""
import logging
from apify_client import ApifyClient
from config.tools import apify_config

logger = logging.getLogger(__name__)

class GeMConnector:
    def __init__(self):
        if not apify_config.api_token:
            logger.warning("APIFY_API_TOKEN not set — GeM connector disabled")
            self.client = None
        else:
            self.client = ApifyClient(apify_config.api_token)

    def search_tenders(self, keywords: list, max_results: int = 100) -> list:
        """
        Search GeM portal for tenders matching keywords.
        Uses Apify's pre-built GeM scraper actor.
        """
        if not self.client:
            return []
        try:
            logger.info(f"Searching GeM via Apify for: {keywords}")
            # Actor input schema is maxTenders/category/ministry — it has no
            # keyword search, so fetch a page of recent bids and filter here.
            run = self.client.actor(
                apify_config.actors["gem_portal"]
            ).call(
                run_input={"maxTenders": max_results}
            )
            if run is None:
                logger.error("Apify GeM run did not complete")
                return []
            items = list(
                self.client.dataset(run.default_dataset_id).iterate_items()
            )
            if keywords:
                kw = [k.lower() for k in keywords]
                # ponytail: title/category substring match — recall-over-precision
                # filtering happens later in the classifier anyway
                items = [
                    it for it in items
                    if any(k in f"{it.get('title','')} {it.get('itemCategory','')}".lower() for k in kw)
                ]
            logger.info(f"GeM returned {len(items)} tenders after keyword filter")
            return items
        except Exception as e:
            logger.error(f"Apify GeM error: {e}")
            return []
