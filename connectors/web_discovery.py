"""
Open-web tender discovery (PRD §5 sources 8–11).

Searches the web for tender notices on department / PSU / bank / newspaper
sites the aggregators miss, using Firecrawl's search API. Results become
RawTenders and flow through the same extract → classify → dedupe pipeline;
dedup drops anything already found via the aggregators.

This is recall-first (PRD §6.5): search is broad, the classifier filters.
"""
import os
import asyncio
import logging
from datetime import datetime

from database.models import RawTender

logger = logging.getLogger(__name__)

# Query templates crossed with the core categories. Kept tight and India-scoped
# so results are procurement notices, not marketing pages.
_QUERY_TEMPLATES = [
    "{kw} tender India government",
    "{kw} tender notice eProcurement",
    "{kw} tender PSU OR bank OR municipal corporation India",
]

# Sites that are tender listings but NOT already covered by our aggregators/Apify.
# Firecrawl search will still surface official portals too; dedup handles overlap.
_INCLUDE_HINTS = None  # None = whole web; the query keywords keep it on-topic


class WebDiscoveryConnector:
    source_name = "WebSearch"

    def __init__(self):
        self.api_key = os.getenv("FIRECRAWL_API_KEY")
        if not self.api_key:
            logger.warning("FIRECRAWL_API_KEY not set — web discovery disabled")

    async def scrape_tenders(self, keywords: list = None, days_back: int = 1) -> list[RawTender]:
        if not self.api_key:
            return []
        # a focused subset — searching all 54 keywords would blow the search quota.
        # The high-signal core categories catch the tenders worth the spend.
        core = keywords or ["CCTV surveillance", "fire alarm system",
                            "access control biometric", "fire suppression",
                            "security manpower", "public address system"]
        return await asyncio.to_thread(self._search_all, core)

    def _search_all(self, keywords: list) -> list[RawTender]:
        from firecrawl import Firecrawl
        app = Firecrawl(api_key=self.api_key)
        tenders: list[RawTender] = []
        seen = set()
        for kw in keywords:
            # one query template per keyword keeps the search-credit spend bounded
            query = _QUERY_TEMPLATES[0].format(kw=kw)
            try:
                res = app.search(query, limit=10, location="India")
                for item in _iter_web_results(res):
                    url = item.get("url")
                    title = (item.get("title") or "").strip()
                    if not url or url in seen or not title:
                        continue
                    seen.add(url)
                    tenders.append(RawTender(
                        title=title[:300],
                        description=(item.get("description") or "")[:1000] or None,
                        url=url,
                        source=self.source_name,
                        search_term=kw,
                        scraped_at=datetime.utcnow().isoformat(),
                    ))
            except Exception as e:
                logger.warning(f"web discovery search '{query}' failed: {e}")
        logger.info(f"Web discovery found {len(tenders)} candidate pages")
        return tenders

    async def close(self):
        pass


def _iter_web_results(res) -> list[dict]:
    """Normalise Firecrawl SearchData → list of {url,title,description} dicts.
    The SDK returns an object with a `.web` list of result models (or a dict)."""
    web = getattr(res, "web", None)
    if web is None and isinstance(res, dict):
        web = res.get("web") or res.get("data")
    out = []
    for r in web or []:
        if isinstance(r, dict):
            out.append({"url": r.get("url"), "title": r.get("title"),
                        "description": r.get("description")})
        else:
            out.append({"url": getattr(r, "url", None),
                        "title": getattr(r, "title", None),
                        "description": getattr(r, "description", None)})
    return out
