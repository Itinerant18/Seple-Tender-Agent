"""
SEPLE Tender Connectors — TenderTiger
Scraper for tendertiger.com using Playwright.
"""
import os
import logging
import asyncio
from typing import List, Optional
from datetime import datetime, timedelta
from playwright.async_api import async_playwright, Page, BrowserContext
from database.models import RawTender, TenderDocument
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
        """Authenticate with TenderTiger."""
        if not self.email or not self.password:
            logger.error("TenderTiger credentials not found in environment")
            return False

        try:
            await self._init_browser()
            logger.info("Navigating to TenderTiger login...")
            # Selectors verified against live site 16-07-2026:
            # login page /User/Account?login, input[name='Email'],
            # input[name='Password'], button#btnlogin
            await self.page.goto(f"{self.base_url}/User/Account?login")
            await self.page.fill("input[name='Email']", self.email)
            await self.page.fill("input[name='Password']", self.password)
            await self.page.click("#btnlogin")

            try:
                await self.page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass  # trackers keep the connection busy; URL check below decides

            # Still on the account/login page => credentials rejected
            if "/User/Account" not in self.page.url:
                self.is_logged_in = True
                logger.info("Successfully logged into TenderTiger")
                return True
            else:
                logger.error("Failed to login to TenderTiger. Check credentials.")
                return False
                
        except Exception as e:
            logger.error(f"Error during TenderTiger login: {e}")
            return False

    async def scrape_tenders(self, keywords: List[str] = None, days_back: int = 1) -> List[RawTender]:
        """Scrape tenders from TenderTiger."""
        if not self.is_logged_in:
            await self.login()
            
        tenders = []
        try:
            # Note: This is placeholder logic for navigating to the search page and extracting data.
            # Real implementation requires exact DOM inspection of tendertiger.com.
            logger.info(f"Starting TenderTiger scrape for keywords: {keywords}")
            
            await self.page.goto(f"{self.base_url}/TenderSearch.aspx")
            
            # For each keyword, perform a search (or use advanced search if supported)
            for keyword in (keywords or ["security"]):
                logger.info(f"Searching for '{keyword}'...")
                await self.page.fill("input[name='txtSearch']", keyword)
                await self.page.click("input[name='btnSearch']")
                await self.page.wait_for_load_state("networkidle")
                
                # Extract tender rows (placeholder selector)
                rows = await self.page.query_selector_all("tr.tender-row")
                for row in rows:
                    title_elem = await row.query_selector("a.tender-title")
                    ref_elem = await row.query_selector("span.tender-ref")
                    val_elem = await row.query_selector("span.tender-value")
                    date_elem = await row.query_selector("span.tender-deadline")
                    
                    title = await title_elem.inner_text() if title_elem else "Unknown"
                    url = await title_elem.get_attribute("href") if title_elem else None
                    ref = await ref_elem.inner_text() if ref_elem else None
                    val = await val_elem.inner_text() if val_elem else None
                    deadline = await date_elem.inner_text() if date_elem else None
                    
                    if url and not url.startswith("http"):
                        url = f"{self.base_url}/{url.lstrip('/')}"
                        
                    raw_tender = RawTender(
                        title=title.strip(),
                        tender_reference=ref.strip() if ref else None,
                        value=val.strip() if val else None,
                        deadline=deadline.strip() if deadline else None,
                        url=url,
                        source=self.source_name,
                        search_term=keyword,
                        scraped_at=datetime.utcnow().isoformat()
                    )
                    tenders.append(raw_tender)
                    
                # Respectful scraping delay
                await asyncio.sleep(2)
                
            logger.info(f"Scraped {len(tenders)} raw tenders from TenderTiger")
            return tenders
            
        except Exception as e:
            logger.error(f"Error scraping TenderTiger: {e}")
            return tenders

    async def download_documents(self, tender_id: str, tender_url: str) -> List[TenderDocument]:
        """Download documents for a specific tender from TenderTiger."""
        docs = []
        if not self.is_logged_in:
            await self.login()
            
        try:
            logger.info(f"Downloading documents for tender {tender_id} at {tender_url}")
            await self.page.goto(tender_url)
            
            # Find download links (placeholder selector)
            download_links = await self.page.query_selector_all("a.doc-download")
            
            import uuid
            import aiohttp
            
            # In a real implementation, we would probably use self.page.expect_download()
            # or extract the URL and download using aiohttp with the session cookies.
            for link in download_links:
                doc_name = await link.inner_text()
                doc_url = await link.get_attribute("href")
                
                # Placeholder for actual download logic
                logger.info(f"Found document: {doc_name}")
                
                docs.append(TenderDocument(
                    tender_id=uuid.UUID(tender_id) if isinstance(tender_id, str) else tender_id,
                    filename=doc_name.strip(),
                    file_url=doc_url
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
        logger.info("TenderTiger connector closed")
