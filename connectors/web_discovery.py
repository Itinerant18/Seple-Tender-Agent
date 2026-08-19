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
import re
import time
import asyncio
import logging
from datetime import datetime
from urllib.parse import urlsplit

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


# Search returns far more index pages than notices. A page titled "62 Cctv Amc
# Tenders In India 2026" is a listing, so it has no deadline, no authority and no
# reference — it was stored anyway, and WebSearch grew to 1,670 rows with a NULL
# deadline on every single one (49% of the whole database, none of it biddable).
_LISTING_URL_MARKERS = (
    "/keyword/", "/global-keyword/", "quicksearch.aspx", "/indian-tender/",
    "tenderailist", "/bids/", "/product/", "request-for-proposal",
)

_LISTING_TITLE_RE = re.compile(
    r"^\s*\d+\s+.*\btenders?\b"          # "62 Cctv Amc Tenders In India 2026"
    r"|^\s*(?:latest|live|all|top)\b.*\btenders?\b"
    r"|^\s*search\s+tenders?\b"
    r"|^\s*tenders?\s*[-–|]"             # "Tenders - Invest India"
    r"|\btenders?\s*(?:&|and)\s*(?:rfps?|eprocurement)\b"
    r"|\btenders?\s+(?:from|in)\s+\w+\s*\d{0,4}\s*$",
    re.I,
)

# Already decided — an awarded contract is not an opportunity.
_CLOSED_MARKERS = ("awarded", "/contract/", "/result", "cancelled")


def _is_tender_page(url: str, title: str) -> bool:
    """True if this looks like one tender notice rather than a list of them.

    Aggregators are rejected wholesale by hostname. This connector exists for the
    department, PSU, bank and newspaper sites the aggregators miss (see the module
    docstring), and TenderTiger and Tender247 already have dedicated connectors —
    so their pages are redundant here as well as unparseable. Government hosts are
    exempt from the hostname rule because eprocure and state portals legitimately
    carry "tender" in the name; their index pages are caught by the path and title
    rules instead.
    """
    parts = urlsplit(url or "")
    host = (parts.hostname or "").lower()
    if not host:
        return False
    blob = f"{parts.path}?{parts.query}".lower()

    if "tender" in host and not host.endswith((".gov.in", ".nic.in")):
        return False
    if any(marker in blob for marker in _LISTING_URL_MARKERS):
        return False
    if any(marker in blob for marker in _CLOSED_MARKERS):
        return False
    return not _LISTING_TITLE_RE.search(title or "")


class WebDiscoveryConnector:
    source_name = "WebSearch"

    def __init__(self):
        self.brave_key = os.getenv("BRAVE_API_KEY")
        self.searxng_url = (os.getenv("SEARXNG_URL") or "").rstrip("/")
        if not self.brave_key and not self.searxng_url:
            logger.warning("Neither BRAVE_API_KEY nor SEARXNG_URL set — web discovery disabled")

    async def scrape_tenders(self, keywords: list = None, days_back: int = 1) -> list[RawTender]:
        if not self.brave_key and not self.searxng_url:
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
        skipped = 0
        with httpx.Client(timeout=20) as client:
            for kw in keywords:
                # one query template per keyword keeps the free-tier spend bounded
                query = _QUERY_TEMPLATES[0].format(kw=kw)
                # Union of both engines — redundancy if one is rate-limited/down.
                items = []
                if self.searxng_url:
                    items += self._search_searxng(client, query)
                if self.brave_key:
                    items += self._search_brave(client, query)
                    time.sleep(1.1)  # Brave free tier allows 1 request/second
                for item in items:
                    url = item.get("url")
                    title = (item.get("title") or "").strip()
                    if not url or url in seen or not title:
                        continue
                    seen.add(url)
                    if not _is_tender_page(url, title):
                        skipped += 1
                        continue
                    tenders.append(RawTender(
                        title=title[:300],
                        description=(item.get("description") or "")[:1000] or None,
                        url=url,
                        source=self.source_name,
                        search_term=kw,
                        scraped_at=datetime.utcnow().isoformat(),
                    ))
        # Log the drop count: a silent filter is indistinguishable from a search
        # that returned nothing, which is the failure mode this whole scan had.
        logger.info(
            "Web discovery found %d candidate notices (%d listing/aggregator "
            "pages skipped)", len(tenders), skipped,
        )
        return tenders

    def _search_brave(self, client: "httpx.Client", query: str) -> list[dict]:
        try:
            resp = client.get(
                _BRAVE_ENDPOINT,
                headers={"Accept": "application/json", "X-Subscription-Token": self.brave_key},
                params={"q": query, "count": 10, "country": "IN"},
            )
            resp.raise_for_status()
            return _iter_brave_results(resp.json())
        except Exception as e:
            logger.warning(f"Brave search '{query}' failed: {e}")
            return []

    def _search_searxng(self, client: "httpx.Client", query: str) -> list[dict]:
        try:
            resp = client.get(
                f"{self.searxng_url}/search",
                params={"q": query, "format": "json", "language": "en", "safesearch": 0},
            )
            resp.raise_for_status()
            return [
                {"url": r.get("url"), "title": r.get("title"), "description": r.get("content")}
                for r in (resp.json().get("results") or [])
                if isinstance(r, dict)
            ]
        except Exception as e:
            logger.warning(f"SearXNG search '{query}' failed: {e}")
            return []

    async def close(self):
        pass


def _iter_brave_results(payload: dict) -> list[dict]:
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
