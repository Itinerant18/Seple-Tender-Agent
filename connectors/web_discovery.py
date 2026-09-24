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
_CLOSED_MARKERS = ("awarded", "/contract/", "slafds", "/result", "cancelled")

# NIC eProcurement ("nicgep") portals — mptenders.gov.in, and any other state
# running the same Tapestry app (eprocure.<state>.gov.in shapes aside, the
# /nicgep/app path is the fingerprint). Three reasons these cannot be scraped
# usefully:
#   1. The per-tender view (FrontEndViewTender&sp=<opaque session handle>)
#      renders shell content with no tender data and no deadline, and the
#      handle expires — verified live 24-09-2026.
#   2. The only data-bearing pages are table listings (Active Tenders, Tenders
#      in Archive) whose many rows' closing dates get mis-attributed to a
#      single stored row.
#   3. The archive listing is captcha-gated, so it cannot be read at all.
# These portals also produce the worst failure class in the pipeline: SERP
# titles for archived MP tenders read like live notices ("Tenders Archived"),
# carry no year-bearing path for the archival filter, and their static title
# ("eProcurement System Government of Madhya Pradesh") matches nothing — so
# expired tenders sailed through discovery, stored undated or with a borrowed
# closing date. Aggregators (TenderTiger/Tender247) already carry MP tenders
# with real deadlines, so nothing biddable is lost by dropping the portal here.
_NICGEP_HOST_MARKERS = ("nicgep",)

# The portal's page names — matched in the query string alongside the host
# check so a different host serving the same app is still caught.
_NICGEP_PAGE_MARKERS = (
    "page=frontendtendersinarchive",
    "page=frontendlatestactivetenders",
    "page=frontendtenderview",
    "page=frontendviewtender",
    "page=frontendadvancedsearchresult",
    "page=webtenderstatuslists",
    "tenders in archive",
)

# Archival URLs. Government sites keep tender PDFs forever under year-bearing
# paths (/files_2024/, /2024/, tenders2024.pdf), and search engines happily
# surface them years later — this is where pre-2026 notices came from. Only
# matches URL paths and titles, never body text: a live notice may legitimately
# quote last year's figures. Matches 2010-2029 so the current year is captured
# too and the comparison below decides freshness — hardcoding the cutoff year
# here would silently stop matching next January.
_STALE_YEAR_RE = re.compile(
    r"(?:files[_-]?|tenders?[_-]?|/|\b)(20(?:1\d|2[0-9]))\b(?!\d)", re.I
)


def _current_procurement_year() -> int:
    """Indian procurement crosses the fiscal year: a notice published in Jan
    belongs to the year before its April–March cycle. Before ~April, treat the
    PREVIOUS year as still-current so live Jan–Mar notices aren't dropped."""
    today = datetime.now()
    return today.year if today.month >= 4 else today.year - 1


def _is_nicgep_portal(url: str, title: str) -> bool:
    """True for NIC eProcurement portal pages (mptenders.gov.in et al).

    The /nicgep/ app path is the fingerprint — every page of the portal,
    including the bare /nicgep/app root, lives under it. The Tapestry page
    names are checked too for hosts that proxy the app without carrying the
    marker. The SERP title is also checked because the archive page's indexed
    title is exactly "Tenders Archived" — the shape that surfaced expired MP
    tenders as if they were live notices.
    """
    parts = urlsplit(url or "")
    host = (parts.hostname or "").lower()
    path = (parts.path or "").lower()
    if "nicgep" in host or path.startswith("/nicgep") or "/nicgep/" in path:
        return True
    blob = f"{parts.path}?{parts.query}".lower()
    if any(marker in blob for marker in _NICGEP_PAGE_MARKERS):
        return True
    return (host.endswith((".gov.in", ".nic.in"))
            and "tenders in archive" in (title or "").lower())


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
    if _is_nicgep_portal(url, title):
        return False
    if any(marker in blob for marker in _LISTING_URL_MARKERS):
        return False
    if any(marker in blob for marker in _CLOSED_MARKERS):
        return False
    if _has_stale_year(parts.path or "", title or ""):
        return False
    return not _LISTING_TITLE_RE.search(title or "")


def _has_stale_year(url_path: str, title: str) -> bool:
    """True when the URL path carries only past years.

    A year-bearing directory path on a government file server is a strong
    archival signal, and a title that quotes the CURRENT year means the notice
    is live regardless of where it is stored — so the title can veto the drop.
    A title-only year never drops anything on its own: titles quote old years
    for all sorts of reasons, and the deadline gate in daily_scan is the right
    judge for those.
    """
    current = _current_procurement_year()
    path_years = {int(m.group(1)) for m in _STALE_YEAR_RE.finditer(url_path or "")}
    if not path_years or any(y >= current for y in path_years):
        return False
    title_years = {int(m.group(1)) for m in _STALE_YEAR_RE.finditer(title or "")}
    return not any(y >= current for y in title_years)


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
                # one query template per keyword keeps the free-tier spend bounded.
                # Anchored to the current procurement year so engines prioritise
                # live notices over the archival PDFs that otherwise dominate.
                query = (f"{_QUERY_TEMPLATES[0].format(kw=kw)} "
                         f"{_current_procurement_year()}")
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
