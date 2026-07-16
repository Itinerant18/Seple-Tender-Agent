"""
SEPLE Tender Connectors — GeM Direct
Scraper for the Government e-Marketplace (GeM) public portal.
Used primarily for verification and direct search.
"""
import logging
import asyncio
from typing import List, Optional
from datetime import datetime
from playwright.async_api import async_playwright, Page, BrowserContext
from database.models import RawTender, TenderDocument
from .base import BaseConnector

logger = logging.getLogger(__name__)

class GeMConnector(BaseConnector):
    def __init__(self):
        # We don't need login credentials for basic public search and verification on GeM
        super().__init__(source_name="GeM", base_url="https://bidplus.gem.gov.in")
        self.playwright = None
        self.browser = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def _init_browser(self):
        if not self.playwright:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True)
            self.context = await self.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            self.page = await self.context.new_page()
            self.page.set_default_timeout(30000)

    async def login(self) -> bool:
        """GeM public search does not require login for basic data."""
        self.is_logged_in = True
        return True

    async def scrape_tenders(self, keywords: List[str] = None, days_back: int = 1) -> List[RawTender]:
        """Search GeM for specific keywords."""
        await self._init_browser()
        tenders = []
        try:
            logger.info(f"Starting GeM search for keywords: {keywords}")
            # The URL structure for GeM bid search
            await self.page.goto(f"{self.base_url}/bidlists")
            
            for keyword in (keywords or ["security"]):
                logger.info(f"Searching GeM for '{keyword}'...")
                
                # Fill search box
                await self.page.fill("input#searchBid", keyword)
                await self.page.click("button#searchBtn")
                await self.page.wait_for_load_state("networkidle")
                await asyncio.sleep(2) # Allow React/Angular to render
                
                # Extract bid cards
                cards = await self.page.query_selector_all("div.card")
                for card in cards:
                    bid_no_elem = await card.query_selector("p.bid_no > a")
                    title_elem = await card.query_selector("div.bid_cat > p")
                    auth_elem = await card.query_selector("div.add-req > div:first-child")
                    date_elem = await card.query_selector("div.add-req > div:last-child")
                    
                    bid_no = await bid_no_elem.inner_text() if bid_no_elem else None
                    title = await title_elem.inner_text() if title_elem else "Unknown"
                    url = f"{self.base_url}/biddetails/{bid_no}" if bid_no else None
                    authority = await auth_elem.inner_text() if auth_elem else None
                    deadline = await date_elem.inner_text() if date_elem else None
                    
                    if bid_no:
                        raw_tender = RawTender(
                            title=title.strip(),
                            tender_reference=bid_no.strip(),
                            deadline=deadline.strip() if deadline else None,
                            issuing_authority=authority.strip() if authority else None,
                            url=url,
                            source=self.source_name,
                            search_term=keyword,
                            scraped_at=datetime.utcnow().isoformat()
                        )
                        tenders.append(raw_tender)
                        
            logger.info(f"Scraped {len(tenders)} raw tenders from GeM")
            return tenders
            
        except Exception as e:
            logger.error(f"Error scraping GeM: {e}")
            return tenders

    async def verify_tender(self, tender_reference: str) -> Optional[RawTender]:
        """Directly look up a specific tender by its GeM reference number (e.g. GEM/2025/B/...)."""
        await self._init_browser()
        try:
            logger.info(f"Verifying GeM reference: {tender_reference}")
            await self.page.goto(f"{self.base_url}/bidlists")
            
            await self.page.fill("input#searchBid", tender_reference)
            await self.page.click("button#searchBtn")
            await self.page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            
            cards = await self.page.query_selector_all("div.card")
            if cards:
                card = cards[0]
                title_elem = await card.query_selector("div.bid_cat > p")
                auth_elem = await card.query_selector("div.add-req > div:first-child")
                date_elem = await card.query_selector("div.add-req > div:last-child")
                
                title = await title_elem.inner_text() if title_elem else "Unknown"
                authority = await auth_elem.inner_text() if auth_elem else None
                deadline = await date_elem.inner_text() if date_elem else None
                url = f"{self.base_url}/biddetails/{tender_reference}"
                
                return RawTender(
                    title=title.strip(),
                    tender_reference=tender_reference,
                    deadline=deadline.strip() if deadline else None,
                    issuing_authority=authority.strip() if authority else None,
                    url=url,
                    source=self.source_name,
                    scraped_at=datetime.utcnow().isoformat()
                )
            return None
            
        except Exception as e:
            logger.error(f"Error verifying GeM reference {tender_reference}: {e}")
            return None

    async def download_documents(self, tender_id: str, tender_url: str) -> List[TenderDocument]:
        """Download documents for a GeM bid."""
        # Note: GeM requires login to download the actual bid documents.
        # As a verification channel, we might just skip this or implement login if needed later.
        logger.warning("GeM document download requires authenticated session. Skipping for verification channel.")
        return []

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("GeM connector closed")
