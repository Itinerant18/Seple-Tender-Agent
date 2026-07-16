"""
Firecrawl client — converts JS-heavy tender pages to clean text.
Used when Playwright can navigate but text extraction is messy.
Free tier: 500 pages/month — use sparingly.

Written against firecrawl-py 4.x (Firecrawl().scrape returns a Document).
"""
import logging

from config.tools import firecrawl_config

logger = logging.getLogger(__name__)

TENDER_FIELDS_SCHEMA = {
    "type": "object",
    "properties": {
        "tender_reference": {"type": "string"},
        "title": {"type": "string"},
        "issuing_authority": {"type": "string"},
        "deadline": {"type": "string"},
        "emd_amount": {"type": "string"},
        "tender_value": {"type": "string"},
        "tender_fee": {"type": "string"},
        "location": {"type": "string"},
        "document_links": {"type": "array", "items": {"type": "string"}},
    },
}


class FirecrawlClient:
    def __init__(self):
        self.app = None
        if not firecrawl_config.api_key:
            logger.warning("FIRECRAWL_API_KEY not set — Firecrawl disabled")
            return
        from firecrawl import Firecrawl
        self.app = Firecrawl(api_key=firecrawl_config.api_key)

    def scrape_page(self, url: str) -> dict:
        """
        Convert a tender detail page to clean markdown + links.
        Returns dict with 'markdown' and 'links' keys.
        """
        if not self.app:
            return {"markdown": "", "links": []}
        try:
            logger.info(f"Firecrawl scraping: {url}")
            doc = self.app.scrape(url, formats=["markdown", "links"])
            return {
                "markdown": doc.markdown or "",
                "links": doc.links or [],
            }
        except Exception as e:
            logger.error(f"Firecrawl error for {url}: {e}")
            return {"markdown": "", "links": []}

    def extract_tender_fields(self, url: str) -> dict:
        """
        Use Firecrawl's extract mode to pull structured F4 fields directly.
        More accurate than manual parsing for complex pages.
        """
        if not self.app:
            return {}
        try:
            result = self.app.extract(urls=[url], schema=TENDER_FIELDS_SCHEMA)
            return getattr(result, "data", None) or {}
        except Exception as e:
            logger.error(f"Firecrawl extract error for {url}: {e}")
            return {}
