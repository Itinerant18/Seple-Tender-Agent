"""
Unified page-scrape fallback chain: Firecrawl → context.dev → Zyte.

All three do the same job (URL → clean text); chaining them means a tender
page still gets parsed when one engine is down, rate-limited, or blocked by
anti-bot. Engines with no API key are skipped silently.

Verified against live docs 22-07-2026:
- Firecrawl:  firecrawl-py 4.x  app.scrape(url, formats=["markdown"]) → .markdown
- context.dev: GET https://api.context.dev/v1/web/scrape/markdown?url=…
               Authorization: Bearer <CONTEXT_DEV_API_KEY> → {"markdown": …}
- Zyte:        POST https://api.zyte.com/v1/extract  basic-auth (ZYTE_API, "")
               {"url": …, "browserHtml": true} → {"browserHtml": html}
"""
import os
import logging

import httpx

logger = logging.getLogger(__name__)


def _firecrawl(url: str) -> str | None:
    key = os.getenv("FIRECRAWL_API_KEY")
    if not key:
        return None
    from firecrawl import Firecrawl
    doc = Firecrawl(api_key=key).scrape(url, formats=["markdown"])
    return doc.markdown or None


def _context_dev(url: str) -> str | None:
    key = os.getenv("CONTEXT_DEV_API_KEY")
    if not key:
        return None
    r = httpx.get(
        "https://api.context.dev/v1/web/scrape/markdown",
        params={"url": url, "useMainContentOnly": "true"},
        headers={"Authorization": f"Bearer {key}"},
        timeout=90,
    )
    r.raise_for_status()
    return r.json().get("markdown") or None


def _zyte(url: str) -> str | None:
    key = os.getenv("ZYTE_API") or os.getenv("ZYTE_API_KEY")
    if not key:
        return None
    r = httpx.post(
        "https://api.zyte.com/v1/extract",
        auth=(key, ""),
        json={"url": url, "browserHtml": True},
        timeout=90,
    )
    r.raise_for_status()
    html = r.json().get("browserHtml") or ""
    if not html:
        return None
    from bs4 import BeautifulSoup
    # Zyte returns raw HTML — reduce to readable text for the classifier
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True) or None


_ENGINES = [("firecrawl", _firecrawl), ("context.dev", _context_dev), ("zyte", _zyte)]


def scrape_page(url: str) -> dict:
    """Fetch a page as clean text, trying each engine in order.

    Returns {"markdown": str, "engine": str} — empty markdown if all fail.
    """
    for name, fn in _ENGINES:
        try:
            text = fn(url)
            if text and len(text) > 100:  # tiny bodies = bot-block interstitials
                logger.info(f"scrape_chain: {name} OK for {url} ({len(text)} chars)")
                return {"markdown": text, "engine": name}
            if text is not None:
                logger.warning(f"scrape_chain: {name} returned thin content for {url}")
        except Exception as e:
            logger.warning(f"scrape_chain: {name} failed for {url}: {e}")
    logger.error(f"scrape_chain: all engines failed for {url}")
    return {"markdown": "", "engine": ""}
