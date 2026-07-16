"""
SEPLE Tender Connectors — Tender247
Scraper for tender247.com using Playwright.
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

class Tender247Connector(BaseConnector):
    def __init__(self):
        super().__init__(source_name="Tender247", base_url="https://www.tender247.com")
        self.email = os.getenv("TENDER247_EMAIL")
        self.password = os.getenv("TENDER247_PASSWORD")
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
        """Authenticate with Tender247."""
        if not self.email or not self.password:
            logger.error("Tender247 credentials not found in environment")
            return False

        try:
            await self._init_browser()
            logger.info("Navigating to Tender247 login...")
            # Note: Actual login URL and selectors need to be verified against the live site.
            await self.page.goto(f"{self.base_url}/Login")
            
            # Fill login form (selectors are placeholders for the real DOM)
            await self.page.fill("input[name='email']", self.email)
            await self.page.fill("input[name='password']", self.password)
            await self.page.click("button[type='submit']")
            
            # Wait for navigation or specific element that indicates successful login
            await self.page.wait_for_load_state("networkidle")
            
            # Check for error messages or verify we are logged in
            if "Login" not in self.page.url:
                self.is_logged_in = True
                logger.info("Successfully logged into Tender247")
                return True
            else:
                logger.error("Failed to login to Tender247. Check credentials.")
                return False
                
        except Exception as e:
            logger.error(f"Error during Tender247 login: {e}")
            return False

    async def scrape_tenders(self, keywords: List[str] = None, days_back: int = 1) -> List[RawTender]:
        """Scrape tenders from Tender247."""
        if not self.is_logged_in:
            await self.login()
            
        tenders = []
        try:
            logger.info(f"Starting Tender247 scrape for keywords: {keywords}")
            
            # Tender247 likely has a dashboard for subscribed alerts, which is much better than searching manually.
            # If so, we navigate there. Assuming a search approach for now:
            await self.page.goto(f"{self.base_url}/TenderSearch")
            
            for keyword in (keywords or ["security"]):
                logger.info(f"Searching for '{keyword}'...")
                await self.page.fill("input[name='search_keyword']", keyword)
                await self.page.click("button.search-btn")
                await self.page.wait_for_load_state("networkidle")
                
                # Extract tender rows (placeholder selector)
                rows = await self.page.query_selector_all("div.tender-item")
                for row in rows:
                    title_elem = await row.query_selector("h4.title > a")
                    ref_elem = await row.query_selector("span.ref-no")
                    val_elem = await row.query_selector("span.est-val")
                    date_elem = await row.query_selector("span.closing-date")
                    auth_elem = await row.query_selector("span.authority")
                    
                    title = await title_elem.inner_text() if title_elem else "Unknown"
                    url = await title_elem.get_attribute("href") if title_elem else None
                    ref = await ref_elem.inner_text() if ref_elem else None
                    val = await val_elem.inner_text() if val_elem else None
                    deadline = await date_elem.inner_text() if date_elem else None
                    authority = await auth_elem.inner_text() if auth_elem else None
                    
                    if url and not url.startswith("http"):
                        url = f"{self.base_url}/{url.lstrip('/')}"
                        
                    raw_tender = RawTender(
                        title=title.strip(),
                        tender_reference=ref.strip() if ref else None,
                        value=val.strip() if val else None,
                        deadline=deadline.strip() if deadline else None,
                        issuing_authority=authority.strip() if authority else None,
                        url=url,
                        source=self.source_name,
                        search_term=keyword,
                        scraped_at=datetime.utcnow().isoformat()
                    )
                    tenders.append(raw_tender)
                    
                # Respectful scraping delay
                await asyncio.sleep(2)
                
            logger.info(f"Scraped {len(tenders)} raw tenders from Tender247")
            return tenders
            
        except Exception as e:
            logger.error(f"Error scraping Tender247: {e}")
            return tenders

    async def download_documents(self, tender_id: str, tender_url: str) -> List[TenderDocument]:
        """Download documents for a specific tender from Tender247."""
        docs = []
        if not self.is_logged_in:
            await self.login()
            
        try:
            logger.info(f"Downloading documents for tender {tender_id} at {tender_url}")
            await self.page.goto(tender_url)
            
            # Find download links (placeholder selector)
            download_links = await self.page.query_selector_all("a.download-btn")
            
            import uuid
            
            for link in download_links:
                doc_name = await link.inner_text()
                doc_url = await link.get_attribute("href")
                
                logger.info(f"Found document: {doc_name}")
                
                docs.append(TenderDocument(
                    tender_id=uuid.UUID(tender_id) if isinstance(tender_id, str) else tender_id,
                    filename=doc_name.strip(),
                    file_url=doc_url
                ))
                
            return docs
            
        except Exception as e:
            logger.error(f"Error downloading documents from Tender247: {e}")
            return docs

    async def close(self):
        """Clean up Playwright resources."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Tender247 connector closed")
