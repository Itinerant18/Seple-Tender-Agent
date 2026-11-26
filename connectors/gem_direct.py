"""
GeM Portal connector — direct Solr JSON API client for bidplus.gem.gov.in.

GeM's frontend (/all-bids) is backed by an internal JSON endpoint at
POST /all-bids-data. Using the JSON endpoint directly with a session cookie and
CSRF token replaces both:
- the legacy Playwright DOM loop (~5-6 minutes of Chromium navigation across 14
  terms, prone to F5 ASM WAF challenges and 30s timeouts on ECS, while reading
  truncated card snippets and occasional fallback URLs), and
- the decommissioned CPPP mirror (eprocure.gov.in/.../gemdata, permanently 404).

Playwright is retained only as a lazy fallback if the direct HTTP endpoint is
ever challenged by WAF.
"""
import asyncio
from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, List

import httpx

from config.tools import playwright_config
from database.models import RawTender

logger = logging.getLogger(__name__)

BASE_URL = "https://bidplus.gem.gov.in"
ALL_BIDS_URL = f"{BASE_URL}/all-bids"
ALL_BIDS_DATA_URL = f"{BASE_URL}/all-bids-data"

PAGES_PER_TERM = 3
PAGE_SIZE = 10

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_API_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Origin": BASE_URL,
    "Referer": ALL_BIDS_URL,
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

# Searched against GeM directly — kept short and broad on purpose.
# config.keywords.SEARCH_KEYWORDS is far more specific ("cctv amc",
# "addressable fire alarm") and would cost ~60 requests to find less.
GEM_SEARCH_TERMS = (
    "cctv",
    "camera",
    "surveillance",
    "security",
    "fire",
    "fire alarm",
    "fire extinguisher",
    "fire fighting",
    "access control",
    "public address",
    "boom barrier",
    "metal detector",
    "biometric",
    "security manpower",
)

_CSRF_PATTERNS = (
    re.compile(r"""csrf_bd_gem_nk['"]?\s*[:=]\s*['"]([a-zA-Z0-9]{16,})['"]"""),
    re.compile(r"""name=['"]csrf_bd_gem_nk['"][^>]*value=['"]([a-zA-Z0-9]{16,})['"]"""),
)
_ITEMS_PLACEHOLDER_RE = re.compile(r"(?:^|,\s*)Items\d+(?=,|$)")

# Card innerText (Playwright fallback) is a flat labelled run:
#   Bid No.: X RA NO: Y ... Items: Z Quantity: N
#   Department Name And Address: D Start Date: ... End Date: ...
_FIELD_PATTERNS = {
    "items": re.compile(r"Items:\s*(.+?)\s+Quantity:", re.I | re.S),
    "quantity": re.compile(r"Quantity:\s*([\d,]+)", re.I),
    "authority": re.compile(r"Department Name And Address:\s*(.+?)\s+Start Date:", re.I | re.S),
    "start_date": re.compile(r"Start Date:\s*(.+?)\s+End Date:", re.I | re.S),
    "end_date": re.compile(r"End Date:\s*(.+?)$", re.I | re.S),
}

_EXTRACT_JS = """els => els.map(e => {
    const link = e.querySelector('a.bid_no_hover');
    return {
        bid: link ? link.innerText.trim() : null,
        url: link ? link.href : null,
        text: (e.innerText || '').replace(/\\s+/g, ' ').trim(),
    };
})"""


def _first(doc: dict[str, Any], key: str) -> Any:
    """Return scalar value from a Solr doc field (which may be a 1-item list)."""
    val = doc.get(key)
    if isinstance(val, list):
        return val[0] if val else None
    return val


def _extract_csrf(html: str, cookies: Any = None) -> str | None:
    """Extract the CodeIgniter CSRF token from /all-bids HTML or cookies."""
    for pattern in _CSRF_PATTERNS:
        match = pattern.search(html or "")
        if match:
            return match.group(1)
    if cookies is not None:
        cookie_val = cookies.get("csrf_gem_cookie")
        if cookie_val:
            return str(cookie_val)
    return None


def _bid_doc_url(doc: dict[str, Any]) -> str:
    """Construct the direct GeM bid/RA document URL matching portal JS logic."""
    b_id = _first(doc, "b_id") or doc.get("id")
    if not b_id:
        return ALL_BIDS_URL
    bid_type = _first(doc, "b_bid_type")
    eval_type = _first(doc, "b_eval_type") or 0
    if bid_type == 5:
        doc_lbl = "showdirectradocumentPdf"
    elif bid_type == 2:
        doc_lbl = "list-ra-schedules" if int(eval_type) > 0 else "showradocumentPdf"
    else:
        doc_lbl = "showbidDocument"
    return f"{BASE_URL}/{doc_lbl}/{b_id}"


def _clean_title(bbt_title: str | None, categories: str | None, bid_number: str) -> str:
    """Build a concise tender title without BOQ placeholder 'Items1,Items2,...' noise."""
    if bbt_title and bbt_title.strip():
        return bbt_title.strip()[:300]
    if categories:
        cleaned = _ITEMS_PLACEHOLDER_RE.sub("", categories).strip(" ,")
        if cleaned:
            return cleaned[:300]
        return categories.strip()[:300]
    return bid_number


def _doc_to_raw_tender(doc: dict[str, Any], search_term: str | None = None) -> RawTender | None:
    """Convert one GeM /all-bids-data Solr doc into a RawTender, or None if unusable."""
    b_status = _first(doc, "b_status")
    if b_status in (3, 5) or _first(doc, "b_is_inactive") == 1:
        return None

    bid_number = _first(doc, "b_bid_number")
    if not bid_number:
        return None
    bid_number = str(bid_number).strip()

    bbt_title = _first(doc, "bbt_title")
    bbt_title_str = str(bbt_title).strip() if bbt_title else None

    categories_raw = _first(doc, "bd_category_name") or _first(doc, "b_category_name")
    categories = str(categories_raw).strip() if categories_raw else None

    min_name = _first(doc, "ba_official_details_minName")
    dept_name = _first(doc, "ba_official_details_deptName")
    authority = " — ".join(
        str(part).strip() for part in (min_name, dept_name) if part and str(part).strip()
    ) or None

    quantity = _first(doc, "b_total_quantity")
    qty_part = f"Quantity: {quantity}" if quantity is not None else None

    desc_parts: list[str] = []
    for part in (bbt_title_str, categories, authority, qty_part):
        if part and part not in desc_parts:
            desc_parts.append(part)

    start_date = _first(doc, "final_start_date_sort")
    end_date = _first(doc, "final_end_date_sort")

    return RawTender(
        title=_clean_title(bbt_title_str, categories, bid_number),
        description=" | ".join(desc_parts) or None,
        tender_reference=bid_number,
        deadline=str(end_date).strip() if end_date else None,
        publication_date=str(start_date).strip() if start_date else None,
        issuing_authority=authority,
        category=categories,
        url=_bid_doc_url(doc),
        source=GeMConnector.source_name,
        search_term=search_term,
        scraped_at=datetime.now(timezone.utc).isoformat(),
    )


def _field(text: str, key: str) -> str | None:
    match = _FIELD_PATTERNS[key].search(text or "")
    return match.group(1).strip() if match else None


def _to_raw_tender(card: dict) -> RawTender | None:
    """Build a RawTender from one Playwright listing card, or None if it has no bid number."""
    bid = card.get("bid")
    text = card.get("text") or ""
    if not bid:
        return None

    items = _field(text, "items")
    authority = _field(text, "authority")
    quantity = _field(text, "quantity")

    return RawTender(
        title=(items or bid)[:300],
        description=" | ".join(
            part for part in (items, authority, f"Quantity: {quantity}" if quantity else None) if part
        ) or None,
        tender_reference=bid,
        deadline=_field(text, "end_date"),
        publication_date=_field(text, "start_date"),
        issuing_authority=authority,
        category=items,
        url=card.get("url") or ALL_BIDS_URL,
        source=GeMConnector.source_name,
        scraped_at=datetime.now(timezone.utc).isoformat(),
    )


class GeMConnector:
    source_name = "GeM"

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None

    async def _fetch_session_csrf(self, client: httpx.AsyncClient) -> str:
        """Load /all-bids to establish session cookies and extract the CSRF token."""
        resp = await client.get(ALL_BIDS_URL)
        resp.raise_for_status()
        csrf = _extract_csrf(resp.text, client.cookies)
        if not csrf:
            raise RuntimeError("GeM /all-bids did not expose csrf_bd_gem_nk token")
        return csrf

    async def _query_api_page(
        self,
        client: httpx.AsyncClient,
        csrf_token: str,
        term: str,
        page: int = 1,
    ) -> tuple[list[dict[str, Any]], int]:
        """Query one page of /all-bids-data for `term`."""
        postdata = {
            "page": page,
            "param": {"searchBid": term, "searchType": "fullText"},
            "filter": {
                "bidStatusType": "ongoing_bids",
                "byType": "all",
                "highBidValue": "",
                "byEndDate": {"from": "", "to": ""},
                "sort": "Bid-Start-Date-Latest",
            },
        }
        resp = await client.post(
            ALL_BIDS_DATA_URL,
            headers=_API_HEADERS,
            data={"payload": json.dumps(postdata), "csrf_bd_gem_nk": csrf_token},
        )
        resp.raise_for_status()
        body = resp.json()
        if body.get("code") != 200:
            raise RuntimeError(f"GeM API returned non-200 code: {body.get('code')!r}")
        resp_obj = (body.get("response") or {}).get("response") or {}
        docs = resp_obj.get("docs") or []
        num_found = int(resp_obj.get("numFound") or 0)
        return docs, num_found

    async def _scrape_via_api(
        self,
        terms: tuple[str, ...],
        max_results: int,
        pages_per_term: int = PAGES_PER_TERM,
    ) -> List[RawTender]:
        """Fetch active bids across `terms` directly from GeM's Solr JSON endpoint."""
        found: dict[str, RawTender] = {}
        attempted_terms = 0
        failed_terms = 0

        async with httpx.AsyncClient(
            timeout=30,
            headers=_BROWSER_HEADERS,
            follow_redirects=True,
        ) as client:
            csrf_token = await self._fetch_session_csrf(client)

            for term in terms:
                if len(found) >= max_results:
                    break
                attempted_terms += 1
                try:
                    for page in range(1, pages_per_term + 1):
                        if len(found) >= max_results:
                            break
                        try:
                            docs, num_found = await self._query_api_page(
                                client, csrf_token, term, page=page
                            )
                        except (httpx.HTTPStatusError, ValueError, RuntimeError) as page_err:
                            # Refresh CSRF/session once if the portal rotated tokens mid-run.
                            logger.debug("GeM API retry for '%s' p%d after: %s", term, page, page_err)
                            csrf_token = await self._fetch_session_csrf(client)
                            docs, num_found = await self._query_api_page(
                                client, csrf_token, term, page=page
                            )

                        if not docs:
                            break
                        for doc in docs:
                            tender = _doc_to_raw_tender(doc, search_term=term)
                            if tender and tender.tender_reference not in found:
                                found[tender.tender_reference] = tender
                        if page * PAGE_SIZE >= num_found:
                            break
                    logger.info("GeM API '%s': %d unique so far", term, len(found))
                except Exception as e:
                    failed_terms += 1
                    logger.warning("GeM API search '%s' failed: %s", term, e)

        if attempted_terms > 0 and failed_terms == attempted_terms:
            raise RuntimeError(f"All {attempted_terms} GeM API term queries failed")

        return list(found.values())[:max_results]

    async def _init_browser(self):
        if self.playwright:
            return
        from playwright.async_api import async_playwright

        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=playwright_config.headless,
            slow_mo=playwright_config.slow_mo,
        )
        major = self.browser.version.split(".")[0]
        context = await self.browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"
            )
        )
        self.page = await context.new_page()
        self.page.set_default_timeout(playwright_config.timeout)

    async def _scrape_via_playwright(
        self,
        terms: tuple[str, ...],
        max_results: int,
    ) -> List[RawTender]:
        """Fallback headless browser scrape when direct HTTP is WAF-challenged."""
        await self._init_browser()
        found: dict[str, RawTender] = {}

        for term in terms:
            if len(found) >= max_results:
                break
            try:
                cards = await self._search_playwright(term)
            except Exception as e:
                logger.warning("GeM Playwright search '%s' failed: %s", term, e)
                continue

            for card in cards:
                tender = _to_raw_tender(card)
                if tender and tender.tender_reference not in found:
                    found[tender.tender_reference] = tender
            logger.info("GeM Playwright '%s': %d cards, %d unique so far", term, len(cards), len(found))

        return list(found.values())[:max_results]

    async def _search_playwright(self, term: str) -> list[dict]:
        await self.page.goto(ALL_BIDS_URL, wait_until="domcontentloaded")
        await asyncio.sleep(6)
        await self.page.fill("#searchBid", term)
        await self.page.press("#searchBid", "Enter")
        await asyncio.sleep(6)

        cards = await self.page.eval_on_selector_all("div.card", _EXTRACT_JS)
        if not cards:
            try:
                await self.page.wait_for_selector("#searchBid", state="attached", timeout=5_000)
            except Exception:
                logger.warning(
                    "GeM search '%s': no cards found and search input #searchBid not present",
                    term,
                )
        return cards

    async def scrape_tenders(self, keywords: List[str] = None, max_results: int = 300) -> List[RawTender]:
        """Search GeM for each core term and return de-duplicated active bids.

        `keywords` is accepted for interface parity with the other connectors
        but ignored: GeM's own search needs broad terms, and the caller passes
        the narrow platform keyword list.
        """
        try:
            try:
                tenders = await self._scrape_via_api(GEM_SEARCH_TERMS, max_results=max_results)
            except Exception as api_err:
                logger.warning(
                    "GeM direct API failed (%s); falling back to Playwright", api_err
                )
                tenders = await self._scrape_via_playwright(GEM_SEARCH_TERMS, max_results=max_results)

            logger.info("GeM returned %d tenders", len(tenders))
            if not tenders:
                logger.info(
                    "GeM scrape completed: 0 tenders found across %d search terms.",
                    len(GEM_SEARCH_TERMS),
                )
            return tenders
        except Exception as e:
            # Raise so the failure lands on the scrape run; a silent [] hides broken scans.
            logger.error("GeM scrape failed: %s", e)
            raise

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.playwright = None
        self.browser = None
        self.page = None
