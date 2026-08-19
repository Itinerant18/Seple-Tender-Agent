"""
SEPLE Tender Connectors — Tender247
Next.js SPA + JSON API gateway (verified live 22-07-2026).

Flow:
- Login is a modal on the homepage ("Sign Up/Log In" button →
  input[name='emailId'] + input[type='password'] → SUBMIT). Success lands on
  /auth/tender. Session (cookies + localStorage incl. JWT) is persisted via
  storage_state and reused across runs.
- Search does NOT need DOM scraping: POST
  /apigateway/T247Tender/mail/api/tender/auth/search-tender with
  Authorization: Bearer <localStorage.userData.token>. The subscription feed is
  scoped by user_email_service_query_id (localStorage 'user_query_id' — the
  copy inside userData is 0, do not use it) and mail_date (userData.mail_date).
- Detail URL: /auth/tender/{tender_id}/{security_code}?tesd={submission_enddate}
"""
import os
import logging
import asyncio
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote, urlsplit, urlunsplit
from datetime import datetime
from playwright.async_api import async_playwright, Page, BrowserContext
from database.models import RawTender, TenderDocument
from config.tools import playwright_config
from .base import BaseConnector

logger = logging.getLogger(__name__)

# full payload the API expects — missing keys cause a 400
_SEARCH_JS = """async (arg) => {
    const ud = JSON.parse(localStorage.getItem('userData') || '{}');
    const qid = Number(localStorage.getItem('user_query_id')) || 0;
    const payload = {tab_id:1, tender_id:0, tender_number:'', search_text:arg.searchText,
        refine_search_text:'', tender_value_operator:0, tender_value_from:0, tender_value_to:0,
        publication_date_from:'', publication_date_to:'', closing_date_from:'', closing_date_to:'',
        search_by_location:false, statezone_ids:'', city_ids:'', state_ids:'', organization_ids:'',
        organization_name:'', sort_by:1, sort_type:2, page_no:1, record_per_page:arg.perPage,
        keyword_id:'', mfa:'', nameof_website:'', tender_typeid:0, is_tender_doc_uploaded:false,
        user_id: ud.user_id, user_email_service_query_id: qid, mail_date: ud.mail_date,
        exact_search:false, exact_search_text:false, search_by_split_word:false,
        product_id:'', organization_type_id:'', sub_industry_id:'', search_by:0,
        guest_user_id:0, quantity:'', quantity_operator:0, msme_exemption:0,
        startup_exemption:0, gem:0, tab_status:0, is_ai_summary:false, boq:0,
        is_grace:false, surety_bond:false, limited_tender:false, corrigendum_type:0};
    const r = await fetch('/apigateway/T247Tender/mail/api/tender/auth/search-tender', {
        method:'POST',
        headers:{'Content-Type':'application/json','Authorization':'Bearer '+ud.token},
        body: JSON.stringify(payload)});
    const d = await r.json();
    return {status:r.status, success:d.Success, total:d.TotalRecord, data:d.Data || []};
}"""


class Tender247Connector(BaseConnector):
    def __init__(self):
        super().__init__(source_name="Tender247", base_url="https://www.tender247.com")
        self.email = os.getenv("TENDER247_EMAIL")
        self.password = os.getenv("TENDER247_PASSWORD")
        self.playwright = None
        self.browser = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.session_file = Path(playwright_config.session_dir) / "tender247_state.json"

    @staticmethod
    def _proxy_server() -> Optional[str]:
        """Proxy for the browser, or None to connect directly.

        tender247.com drops packets from cloud egress IPs: from AWS every
        goto() times out, while the same URL returns 200 from an office
        connection.

        Off by default, including on AWS. Zyte proxy mode was tried
        (13-08-2026): pages load, but the login modal never opens — Zyte
        rotates the exit IP between requests, so the SPA's follow-up calls
        arrive from a different address and the DOM is torn down. Making that
        work needs sticky sessions, and it costs credits per run either way.
        Set SCRAPER_PROXY only with a proxy that holds one IP for a session.
        """
        return os.getenv("SCRAPER_PROXY")

    @classmethod
    def _proxy_launch_args(cls) -> Optional[dict]:
        """Playwright proxy config, credentials split out of the URL.

        Chromium ignores user:pass embedded in a proxy URL — the proxy then
        answers 407 and every navigation hangs until it times out. Playwright
        wants them as separate username/password fields.
        """
        url = cls._proxy_server()
        if not url:
            return None
        parsed = urlsplit(url)
        server = urlunsplit((parsed.scheme, parsed.hostname or "", "", "", ""))
        if parsed.port:
            server = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
        config = {"server": server}
        if parsed.username:
            config["username"] = unquote(parsed.username)
            config["password"] = unquote(parsed.password or "")
        return config

    async def _init_browser(self):
        if self.playwright:
            return
        self.playwright = await async_playwright().start()
        proxy = self._proxy_launch_args()
        if proxy:
            logger.info("Tender247 browser using proxy egress (%s)", proxy["server"])
        self.browser = await self.playwright.chromium.launch(
            headless=playwright_config.headless,
            slow_mo=playwright_config.slow_mo,
            proxy=proxy,
        )
        major = self.browser.version.split(".")[0]
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{major}.0.0.0 Safari/537.36"
        )
        storage = str(self.session_file) if self.session_file.exists() else None
        # Zyte terminates TLS with its own CA, so certificate checks fail
        # through the proxy; and a proxied page load is far slower than a
        # direct one, which blew the default 30s navigation timeout.
        self.context = await self.browser.new_context(
            user_agent=ua,
            storage_state=storage,
            ignore_https_errors=bool(proxy),
        )
        self.page = await self.context.new_page()
        timeout = 120_000 if proxy else playwright_config.timeout
        self.page.set_default_timeout(timeout)
        self.page.set_default_navigation_timeout(timeout)

    async def login(self) -> bool:
        """Authenticate with Tender247, reusing the persisted session when possible."""
        if not self.email or not self.password:
            logger.error("Tender247 credentials not found in environment")
            return False
        try:
            await self._init_browser()

            # 1. Try persisted session
            if self.session_file.exists():
                await self.page.goto(f"{self.base_url}/auth/tender", wait_until="domcontentloaded")
                await asyncio.sleep(6)  # SPA hydration
                if "/auth/" in self.page.url:
                    self.is_logged_in = True
                    logger.info("Tender247 session restored from storage_state")
                    return True
                logger.info("Persisted Tender247 session expired — logging in fresh")

            # 2. Fresh login via homepage modal
            await self.page.goto(self.base_url, wait_until="domcontentloaded")
            # Wait on the elements, not the clock. Fixed sleeps of 6s + 3s plus a
            # 25s wait_for_url totalled 34s, and on 19-08-2026 the login needed
            # more than that: the run was logged as "check credentials" while the
            # credentials, the network and the markup were all fine.
            #
            # Header button is "Log in" (verified live 11-08-2026). The mobile
            # menu holds a hidden "Sign Up / Log in" duplicate — matching that
            # one waits forever for visibility, so keep this match exact.
            login_button = self.page.get_by_role("button", name="Log in", exact=True).first
            await login_button.wait_for(state="visible", timeout=60_000)
            await login_button.click()
            email_box = self.page.locator("input[name='emailId']")
            await email_box.wait_for(state="visible", timeout=30_000)
            await email_box.fill(self.email)
            await self.page.fill("input[type='password']", self.password)
            await self.page.get_by_role("button", name="SUBMIT").first.click()
            redirected = True
            try:
                await self.page.wait_for_url("**/auth/**", timeout=90_000)
            except Exception:
                redirected = False

            if "/auth/" in self.page.url:
                self.is_logged_in = True
                self.session_file.parent.mkdir(parents=True, exist_ok=True)
                await self.context.storage_state(path=str(self.session_file))
                logger.info("Successfully logged into Tender247 (session persisted)")
                return True

            # Report what happened, not a guess. This used to read "Check
            # credentials.", which is what a redirect that merely ran slow looks
            # like — and it cost a day chasing rotated passwords and an IP
            # whitelist while the credentials were correct all along (19-08-2026).
            # A rejected login leaves us on the homepage with an error in the
            # modal; a slow one just never redirects in time.
            reason = (
                "no redirect within 90s" if not redirected
                else f"landed on {self.page.url}"
            )
            logger.error(
                "Failed to login to Tender247 (%s). Credentials are only one "
                "possible cause — check the login duration in this log before "
                "assuming they are wrong.", reason
            )
            return False
        except Exception as e:
            logger.error(f"Error during Tender247 login: {e}")
            return False

    async def scrape_tenders(self, keywords: List[str] = None, days_back: int = 1) -> List[RawTender]:
        """Query the subscription feed via the JSON API — one call per keyword,
        plus one unfiltered call so nothing in the daily feed is missed (PRD §6.5)."""
        if not self.is_logged_in and not await self.login():
            # Surfaces on the scrape run instead of reading as an empty feed.
            raise RuntimeError("Tender247 login failed — check credentials or the login markup")

        # make sure we're on an /auth page so localStorage + relative fetch work
        if "/auth/" not in self.page.url:
            await self.page.goto(f"{self.base_url}/auth/tender", wait_until="domcontentloaded")
            await asyncio.sleep(6)

        tenders: List[RawTender] = []
        seen = set()
        for keyword in [""] + list(keywords or []):
            try:
                res = await self.page.evaluate(
                    _SEARCH_JS, {"searchText": keyword, "perPage": 100}
                )
                if res["status"] != 200 or not res["success"]:
                    logger.error(f"Tender247 API error for '{keyword}': HTTP {res['status']}")
                    continue
                for it in res["data"]:
                    tid = str(it.get("tender_id"))
                    if tid in seen:
                        continue
                    seen.add(tid)
                    tesd = it.get("submission_enddate") or ""
                    url = f"{self.base_url}/auth/tender/{tid}/{it.get('security_code')}"
                    if tesd:
                        url += f"?tesd={tesd}"
                    brief = (it.get("requirement_workbrief") or "").strip()
                    tenders.append(RawTender(
                        title=brief[:300] or "Unknown",
                        description=brief,
                        tender_reference=it.get("tender_number") or tid,
                        value=str(it.get("estimatedcost") or "") or None,
                        deadline=tesd or None,
                        issuing_authority=it.get("organization_name"),
                        location=it.get("site_location"),
                        url=url,
                        source=self.source_name,
                        search_term=keyword or "(daily feed)",
                        scraped_at=datetime.utcnow().isoformat(),
                    ))
                await asyncio.sleep(1)  # gentle pacing between API calls
            except Exception as e:
                logger.error(f"Tender247 search '{keyword}' failed: {e}")
        logger.info(f"Scraped {len(tenders)} unique tenders from Tender247")
        return tenders

    async def download_documents(self, tender_id: str, tender_url: str) -> List[TenderDocument]:
        # TODO(probe): document endpoints not yet mapped; detail page has doc links
        # behind doc_uploaded flag. Classifier works off workbrief meanwhile.
        return []

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.playwright = None
        self.browser = None
        logger.info("Tender247 connector closed")
