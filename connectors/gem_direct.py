"""
GeM Portal connector — direct Playwright scrape of bidplus.gem.gov.in.

Replaces the Apify actor (verified live 11-08-2026). The actor had no keyword
input, so it could only return the newest N bids and hope something relevant
was among them; the portal's own "Enter Keyword" box searches the whole live
bid corpus, which is what the tenders team compares against. Direct scraping
also removes the Apify quota as a failure mode — when that quota ran out the
connector returned an empty list, which the UI showed as "no tenders".

The listing card carries bid number, items, quantity, department and both
dates. Item text is truncated by the portal ("Portable Fire Extinguishers
(V..."), so titles are short; the detail page would be one extra fetch per bid
and is not worth it for classification.
"""
import asyncio
import base64
import logging
import re
from datetime import datetime
from typing import List

from playwright.async_api import async_playwright

from config.tools import playwright_config
from database.models import RawTender

logger = logging.getLogger(__name__)

BASE_URL = "https://bidplus.gem.gov.in"
ALL_BIDS_URL = f"{BASE_URL}/all-bids"

# Searched against GeM directly, one page load each — kept short and broad on
# purpose. config.keywords.SEARCH_KEYWORDS is far more specific ("cctv amc",
# "addressable fire alarm") and would cost ~60 page loads to find less.
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

# Card innerText is a flat labelled run:
#   Bid No.: X RA NO: Y ... Items: Z Quantity: N
#   Department Name And Address: D Start Date: ... End Date: ...
_FIELD_PATTERNS = {
    "items": re.compile(r"Items:\s*(.+?)\s+Quantity:", re.I | re.S),
    "quantity": re.compile(r"Quantity:\s*([\d,]+)", re.I),
    "authority": re.compile(r"Department Name And Address:\s*(.+?)\s+Start Date:", re.I | re.S),
    "start_date": re.compile(r"Start Date:\s*(.+?)\s+End Date:", re.I | re.S),
    "end_date": re.compile(r"End Date:\s*(.+?)$", re.I | re.S),
}

# CPPP mirrors the whole GeM bid corpus at this URL, 10 rows/page and no
# captcha — only its keyword search is captcha-gated. The bidplus search
# above returns just the first page per term, so this lifts that ceiling.
# Same bids, so dedup by bid number.
MIRROR_URL = "https://eprocure.gov.in/cppp/latestactivetendersnew/gemdata"


def _mirror_page_url(page: int) -> str:
    """URL for 1-based mirror page `page`.

    Pagination goes through a base64 of the real ?page=N URL. A bare
    ?page=N is accepted and silently ignored: every request then returns
    page 1's ten rows, so 40 pages yielded 10 unique rows (verified
    19-08-2026, which is why GeM found only 3 tenders that night).
    """
    if page <= 1:
        return MIRROR_URL
    token = base64.b64encode(f"{MIRROR_URL}?page={page}".encode()).decode()
    return f"{MIRROR_URL}?url={token}"

# Broader than GEM_SEARCH_TERMS: mirror rows are filtered locally, not by the
# portal, so recall matters more than query cost.
MIRROR_TOKENS = tuple(GEM_SEARCH_TERMS) + (
    "alarm", "extinguisher", "surveillance", "guard", "manpower", "fighting",
    "nvr", "dvr", "intrusion", "hydrant", "sprinkler", "suppression",
    "turnstile", "rfid", "baggage", "smoke", "bms",
)

_EXTRACT_JS = """els => els.map(e => {
    const link = e.querySelector('a.bid_no_hover');
    return {
        bid: link ? link.innerText.trim() : null,
        url: link ? link.href : null,
        text: (e.innerText || '').replace(/\\s+/g, ' ').trim(),
    };
})"""


def _field(text: str, key: str) -> str | None:
    match = _FIELD_PATTERNS[key].search(text or "")
    return match.group(1).strip() if match else None


def _to_raw_tender(card: dict) -> RawTender | None:
    """Build a RawTender from one listing card, or None if it has no bid number."""
    bid = card.get("bid")
    text = card.get("text") or ""
    if not bid:
        return None

    items = _field(text, "items")
    authority = _field(text, "authority")
    quantity = _field(text, "quantity")

    return RawTender(
        title=(items or bid)[:300],
        # Items text is the only scope GeM exposes on the listing; pass the
        # surrounding detail through so the classifier sees more than a title.
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
        scraped_at=datetime.utcnow().isoformat(),
    )


def _mirror_row_to_tender(cells: list[str], url: str | None) -> RawTender | None:
    """Build a RawTender from one CPPP mirror row, or None if it isn't a bid.

    Columns: Sl.No | Bid Start | Bid End | Bid Number/Quantity | Product
    Category | Organisation | Department.
    """
    if len(cells) < 7 or "GEM/" not in cells[3]:
        return None
    # Match the product column only. Organisation and department names carry
    # our tokens too — "Border Security Force" made every tyre, battery and
    # tractor bid they float a match, which is what put "Graphite Fine
    # Powder" in a dashboard search for "security".
    if not any(token in cells[4].lower() for token in MIRROR_TOKENS):
        return None

    bid = cells[3].rsplit("/", 1)[0] if cells[3].count("/") > 3 else cells[3]
    authority = " — ".join(part for part in (cells[5], cells[6]) if part)
    return RawTender(
        title=(cells[4] or bid)[:300],
        description=" | ".join(part for part in (cells[4], cells[5], cells[6]) if part) or None,
        tender_reference=bid,
        deadline=cells[2] or None,
        publication_date=cells[1] or None,
        issuing_authority=authority or None,
        category=cells[4] or None,
        url=url or MIRROR_URL,
        source=GeMConnector.source_name,
        scraped_at=datetime.utcnow().isoformat(),
    )


def _scrape_mirror(pages: int) -> List[RawTender]:
    """Page the CPPP GeM mirror over plain HTTP — no browser, no captcha."""
    import httpx
    from bs4 import BeautifulSoup

    out: List[RawTender] = []
    with httpx.Client(timeout=45, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=True) as client:
        for page in range(1, pages + 1):
            try:
                resp = client.get(_mirror_page_url(page))
                resp.raise_for_status()
            except Exception as e:
                logger.warning("GeM mirror page %d failed: %s", page, e)
                continue
            for tr in BeautifulSoup(resp.text, "html.parser").select("tr"):
                tds = tr.select("td")
                link = tr.select_one("a[href]")
                tender = _mirror_row_to_tender(
                    [td.get_text(" ", strip=True) for td in tds],
                    link.get("href") if link else None,
                )
                if tender:
                    out.append(tender)
    return out


class GeMConnector:
    source_name = "GeM"

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None

    async def _init_browser(self):
        if self.playwright:
            return
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

    async def scrape_tenders(self, keywords: List[str] = None, max_results: int = 300) -> List[RawTender]:
        """Search GeM for each core term and return de-duplicated bids.

        `keywords` is accepted for interface parity with the other connectors
        but ignored: GeM's own search needs broad terms, and the caller passes
        the narrow platform keyword list.
        """
        try:
            await self._init_browser()
            found: dict[str, RawTender] = {}

            for term in GEM_SEARCH_TERMS:
                if len(found) >= max_results:
                    break
                try:
                    cards = await self._search(term)
                except Exception as e:
                    logger.warning("GeM search '%s' failed: %s", term, e)
                    continue

                for card in cards:
                    tender = _to_raw_tender(card)
                    if tender and tender.tender_reference not in found:
                        found[tender.tender_reference] = tender
                logger.info("GeM '%s': %d cards, %d unique so far", term, len(cards), len(found))

            # Top up from the CPPP mirror, which reaches past the first page
            # the portal search returns. ponytail: 40 pages (~400 rows) keeps
            # the run short; raise it if daily coverage proves thin.
            for tender in await asyncio.to_thread(_scrape_mirror, 40):
                found.setdefault(tender.tender_reference, tender)

            tenders = list(found.values())[:max_results]
            logger.info("GeM returned %d tenders", len(tenders))
            return tenders
        except Exception as e:
            # Raise so the failure lands on the scrape run; a silent [] is what
            # made the exhausted Apify quota look like "no GeM tenders".
            logger.error("GeM scrape failed: %s", e)
            raise

    async def _search(self, term: str) -> list[dict]:
        # ponytail: first page only — GeM paginates at 10 cards, so this reads
        # the 10 most recent bids per term (~90 unique across the term list).
        # Follow the pagination links if daily coverage proves too thin.
        await self.page.goto(ALL_BIDS_URL, wait_until="domcontentloaded")
        await asyncio.sleep(6)  # listing renders after hydration
        await self.page.fill("#searchBid", term)
        await self.page.press("#searchBid", "Enter")
        await asyncio.sleep(6)  # results replace the list in place, URL is unchanged
        return await self.page.eval_on_selector_all("div.card", _EXTRACT_JS)

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.playwright = None
        self.browser = None
        self.page = None
