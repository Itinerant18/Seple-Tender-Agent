"""
Open-web tender discovery (PRD §5 sources 8–11).

Searches the web for tender notices on department / PSU / bank / newspaper
sites the aggregators miss, using the Brave Search API. Results become
RawTenders and flow through the same extract → classify → dedupe pipeline;
dedup drops anything already found via the aggregators. Full page text is
pulled later by the scrape chain (Zyte / context.dev) — this step only
discovers URLs.

This is recall-first (PRD §6.5): search is broad, the classifier filters.

Brave Search API: free tier ~2,000 queries/month, 1 request/second. Get a key
at https://brave.com/search/api/ and set BRAVE_API_KEY.
"""
import os
import time
import asyncio
import logging
from datetime import datetime

import httpx

from database.models import RawTender

logger = logging.getLogger(__name__)

_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

# Query templates crossed with the core categories. Kept tight and India-scoped
# so results are procurement notices, not marketing pages.
_QUERY_TEMPLATES = [
    "{kw} tender India government",
    "{kw} tender notice eProcurement",
    "{kw} tender PSU OR bank OR municipal corporation India",
]


class WebDiscoveryConnector:
    source_name = "WebSearch"

    def __init__(self):
        self.api_key = os.getenv("BRAVE_API_KEY")
        if not self.api_key:
            logger.warning("BRAVE_API_KEY not set — web discovery disabled")

    async def scrape_tenders(self, keywords: list = None, days_back: int = 1) -> list[RawTender]:
        if not self.api_key:
            return []
        # A focused subset — searching all 54 keywords would blow the free-tier
        # quota. The high-signal core categories catch the tenders worth it.
        core = keywords or ["CCTV surveillance", "fire alarm system",
                            "access control biometric", "fire suppression",
                            "security manpower", "public address system"]
        return await asyncio.to_thread(self._search_all, core)

    def _search_all(self, keywords: list) -> list[RawTender]:
        tenders: list[RawTender] = []
        seen = set()
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
        }
        with httpx.Client(timeout=20) as client:
            for kw in keywords:
                # one query template per keyword keeps the free-tier spend bounded
                query = _QUERY_TEMPLATES[0].format(kw=kw)
                try:
                    resp = client.get(
                        _BRAVE_ENDPOINT,
                        headers=headers,
                        params={"q": query, "count": 10, "country": "IN"},
                    )
                    resp.raise_for_status()
                    for item in _iter_web_results(resp.json()):
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
                # Brave free tier allows 1 request/second.
                time.sleep(1.1)
        logger.info(f"Web discovery found {len(tenders)} candidate pages")
        return tenders

    async def close(self):
        pass


def _iter_web_results(payload: dict) -> list[dict]:
    """Normalise a Brave web-search response → [{url,title,description}].

    Brave returns {"web": {"results": [{"url","title","description"}, ...]}}.
    Descriptions may contain <strong> highlight tags — left as-is; the
    classifier tolerates minor markup.
    """
    results = ((payload or {}).get("web") or {}).get("results") or []
    return [
        {"url": r.get("url"), "title": r.get("title"), "description": r.get("description")}
        for r in results
        if isinstance(r, dict)
    ]
