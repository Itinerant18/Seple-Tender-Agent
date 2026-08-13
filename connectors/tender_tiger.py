"""
SEPLE Tender Connectors — TenderTiger
Scraper for tendertiger.com using Playwright.

Live findings (22-07-2026):
- Login: /User/Account?login, input[name='Email'], input[name='Password'], #btnlogin.
- Post-login home is /Dashboard/Dashboard, which hosts the AI/keyword search UI.
- Search box: #txt_searchadvanceSearch; the site's own JS navigates to
  /AIListing/AIListing?searchtext=<query>-tenders. Navigating that URL directly
  (without going through the UI) returns an IIS 403.
- The WAF also 403-blocks the login page after several fresh logins in a short
  window — so we persist storage_state and reuse the session instead of
  logging in on every run.
"""
import os
import logging
import asyncio
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from playwright.async_api import async_playwright, Page, BrowserContext
from database.models import RawTender, TenderDocument
from config.tools import playwright_config
from .base import BaseConnector

logger = logging.getLogger(__name__)


class TenderTigerConnector(BaseConnector):
    def __init__(self):
        super().__init__(source_name="TenderTiger", base_url="https://www.tendertiger.com")
        self.email = os.getenv("TENDER_TIGER_EMAIL")
        self.password = os.getenv("TENDER_TIGER_PASSWORD")
        self.playwright = None
        self.browser = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.session_file = Path(playwright_config.session_dir) / "tendertiger_state.json"

    async def _init_browser(self):
        if self.playwright:
            return
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=playwright_config.headless,
            slow_mo=playwright_config.slow_mo,
        )
        # UA must match the real engine version — a mismatched UA is what gets
        # sessions flagged. Build it from the running Chromium's major version.
        major = self.browser.version.split(".")[0]
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{major}.0.0.0 Safari/537.36"
        )
        storage = str(self.session_file) if self.session_file.exists() else None
        self.context = await self.browser.new_context(user_agent=ua, storage_state=storage)
        self.page = await self.context.new_page()
        self.page.set_default_timeout(playwright_config.timeout)

    async def _goto(self, url: str):
        # "load" never fires reliably here (ad/tracker requests hang); DOM is enough
        await self.page.goto(url, wait_until="domcontentloaded")

    def _is_waf_blocked_sync(self, content: str) -> bool:
        return "403 - Forbidden" in content or "Access is denied" in content

    async def _waf_blocked(self) -> bool:
        try:
            content = await self.page.content()
        except Exception:
            return False
        if self._is_waf_blocked_sync(content):
            logger.error(
                "TenderTiger WAF returned 403 — backing off. Do NOT retry "
                "immediately; the block clears after a cooldown. Session reuse "
                "(storage_state) avoids this by not re-logging-in every run."
            )
            return True
        return False

    @staticmethod
    def _is_logged_in_url(url: str) -> bool:
        """Logged-in pages live under /Dashboard.

        Checking only that the URL isn't /User/Account is not proof of a
        session: an expired session redirects to the public homepage, which
        passed that test and made login() report success while every later
        search timed out on a search box that only exists logged in.
        """
        return "/Dashboard" in (url or "")

    async def login(self) -> bool:
        """Authenticate with TenderTiger, reusing a persisted session when possible."""
        if not self.email or not self.password:
            logger.error("TenderTiger credentials not found in environment")
            return False

        try:
            await self._init_browser()

            # 1. Try the persisted session first — avoids fresh logins that trip the WAF
            if self.session_file.exists():
                await self._goto(f"{self.base_url}/Dashboard/Dashboard")
                if self._is_logged_in_url(self.page.url) and not await self._waf_blocked():
                    self.is_logged_in = True
                    logger.info("TenderTiger session restored from storage_state")
                    return True
                logger.info("Persisted TenderTiger session expired — logging in fresh")

            # 2. Fresh login
            await self._goto(f"{self.base_url}/User/Account?login")
            if await self._waf_blocked():
                return False
            await self.page.fill("input[name='Email']", self.email)
            await self.page.fill("input[name='Password']", self.password)
            await self.page.click("#btnlogin")
            try:
                await self.page.wait_for_url("**/Dashboard/**", timeout=20000)
            except Exception:
                pass  # URL check below decides

            if self._is_logged_in_url(self.page.url):
                self.is_logged_in = True
                self.session_file.parent.mkdir(parents=True, exist_ok=True)
                await self.context.storage_state(path=str(self.session_file))
                logger.info("Successfully logged into TenderTiger (session persisted)")
                return True
            logger.error("Failed to login to TenderTiger. Check credentials.")
            return False

        except Exception as e:
            logger.error(f"Error during TenderTiger login: {e}")
            return False

    async def scrape_tenders(self, keywords: List[str] = None, days_back: int = 1) -> List[RawTender]:
        """Search TenderTiger through the dashboard UI (deep-linking the listing URL is WAF-blocked)."""
        if not self.is_logged_in and not await self.login():
            # Raise rather than return []: daily_scan isolates each source and
            # records the reason on its scrape run, so a blocked login shows up
            # as a failure instead of looking like "no matching tenders".
            raise RuntimeError("TenderTiger login failed — check credentials or the WAF")

        tenders = []
        failures: List[str] = []
        for keyword in (keywords or ["security"]):
            try:
                logger.info(f"TenderTiger search: '{keyword}'")
                await self._goto(f"{self.base_url}/Dashboard/Dashboard")
                # The search "box" is a placeholder div; clicking it reveals the
                # real input (#txt_searchadvanceSearch, hidden until then).
                await self.page.locator("div.main-search-new:visible").first.click()
                box = self.page.locator("#txt_searchadvanceSearch:visible").first
                await box.fill(keyword)
                await box.press("Enter")
                # site navigates to /TenderAI/TenderAIList?searchtext=<kw>-tenders
                await self.page.wait_for_selector("li.tender-listing", timeout=45000)
                if await self._waf_blocked():
                    raise RuntimeError(f"TenderTiger WAF blocked the search for '{keyword}'")
                tenders.extend(await self._extract_rows(keyword))
                await asyncio.sleep(2)  # respectful delay between searches
            except Exception as e:
                # One keyword failing is tolerable; every keyword failing means
                # the source is down, not that nothing matched.
                logger.error(f"TenderTiger search '{keyword}' failed: {e}")
                failures.append(str(e))
        if failures and not tenders:
            raise RuntimeError(f"TenderTiger returned nothing; first error: {failures[0]}")
        logger.info(f"Scraped {len(tenders)} raw tenders from TenderTiger")
        return tenders

    async def _extract_rows(self, keyword: str) -> List[RawTender]:
        """Parse li.tender-listing rows (structure verified live 22-07-2026)."""
        raw = await self.page.eval_on_selector_all(
            "li.tender-listing",
            """els => els.map(li => {
                const txt = (el) => el ? el.innerText.trim() : null;
                const out = {
                    tid: null, authority: txt(li.querySelector('a.org-name')),
                    location: txt(li.querySelector('b.tender-listing-serial')),
                    brief: txt(li.querySelector('.tenderbrif')),
                    url: li.querySelector("a[href*='TenderDetail']")?.href || null,
                    worth: null, emd: null, due: null,
                };
                const chk = li.querySelector('input.form-check-input');
                if (chk) out.tid = chk.getAttribute('name');
                // labeled fields: span.sub_title 'Worth :' / 'EMD :' / 'Due Date :'
                // followed by the value element (a.twm-job-title or b.value)
                let key = null;
                for (const el of li.querySelectorAll('span.sub_title, a.twm-job-title, b.value')) {
                    if (el.matches('span.sub_title')) {
                        const t = el.innerText.trim().toLowerCase();
                        key = t.startsWith('worth') ? 'worth'
                            : t.startsWith('emd') ? 'emd'
                            : t.startsWith('due') ? 'due' : null;
                    } else if (key && !out[key]) {
                        out[key] = el.innerText.trim();
                        key = null;
                    }
                }
                return out;
            })""",
        )
        rows: List[RawTender] = []
        seen = set()
        for r in raw:
            tid = r.get("tid")
            brief = (r.get("brief") or "").strip()
            if not brief or tid in seen:
                continue  # grid+list views duplicate rows — dedupe on TID
            seen.add(tid)
            rows.append(RawTender(
                title=brief[:300],
                description=brief,
                tender_reference=tid,
                value=r.get("worth"),
                deadline=r.get("due"),
                issuing_authority=r.get("authority"),
                location=r.get("location"),
                url=r.get("url"),
                source=self.source_name,
                search_term=keyword,
                scraped_at=datetime.utcnow().isoformat(),
            ))
        logger.info(f"  extracted {len(rows)} rows for '{keyword}'")
        return rows

    async def download_documents(self, tender_id: str, tender_url: str) -> List[TenderDocument]:
        """Download documents for a specific tender from TenderTiger."""
        docs = []
        if not self.is_logged_in and not await self.login():
            return docs
        try:
            await self._goto(tender_url)
            if await self._waf_blocked():
                return docs
            import uuid
            # TODO(probe): detail-page document selectors pending live capture
            links = await self.page.eval_on_selector_all(
                "a[href$='.pdf'], a[href*='Download']",
                "els => els.map(e => ({href: e.href, text: (e.innerText || '').trim()}))",
            )
            for link in links:
                docs.append(TenderDocument(
                    tender_id=uuid.UUID(tender_id) if isinstance(tender_id, str) else tender_id,
                    filename=(link.get("text") or "document").strip()[:200],
                    file_url=link.get("href"),
                ))
            return docs
        except Exception as e:
            logger.error(f"Error downloading documents from TenderTiger: {e}")
            return docs

    async def close(self):
        """Clean up Playwright resources."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.playwright = None
        self.browser = None
        logger.info("TenderTiger connector closed")
