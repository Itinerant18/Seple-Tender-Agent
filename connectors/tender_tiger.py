"""
SEPLE Tender Tiger Connector
Playwright-based scraper for TenderTiger.com portal.
"""
import os
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class TenderTigerConnector:
    """Scrapes tender listings from TenderTiger.com using Playwright."""

    BASE_URL = "https://www.tendertiger.com"

    def __init__(self):
        self.email = os.getenv("TENDER_TIGER_EMAIL")
        self.password = os.getenv("TENDER_TIGER_PASSWORD")
        if not self.email or not self.password:
            raise ValueError("TENDER_TIGER_EMAIL and TENDER_TIGER_PASSWORD must be set in .env")

    async def login(self, page):
        """Authenticate with TenderTiger portal."""
        logger.info("Logging into TenderTiger...")
        await page.goto(f"{self.BASE_URL}/login")
        await page.fill('input[name="email"]', self.email)
        await page.fill('input[name="password"]', self.password)
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        logger.info("TenderTiger login successful")

    async def scrape_tenders(self, page, keywords: list[str] = None, max_pages: int = 5) -> list[dict]:
        """
        Scrape tender listings matching given keywords.

        Args:
            page: Playwright page object
            keywords: List of search keywords to filter tenders
            max_pages: Maximum number of result pages to scrape

        Returns:
            List of tender dicts with title, deadline, value, category, url, source
        """
        tenders = []
        search_terms = keywords or ["IT", "software", "digital", "cloud"]

        for term in search_terms:
            logger.info(f"Searching TenderTiger for: {term}")
            await page.goto(f"{self.BASE_URL}/search?q={term}")
            await page.wait_for_load_state("networkidle")

            for page_num in range(1, max_pages + 1):
                listings = await page.query_selector_all(".tender-listing-item")

                for listing in listings:
                    try:
                        tender = {
                            "title": await listing.inner_text(".tender-title"),
                            "deadline": await listing.inner_text(".tender-deadline"),
                            "value": await listing.inner_text(".tender-value"),
                            "category": await listing.inner_text(".tender-category"),
                            "url": await listing.get_attribute("a", "href"),
                            "source": "TenderTiger",
                            "scraped_at": datetime.utcnow().isoformat(),
                            "search_term": term,
                        }
                        tenders.append(tender)
                    except Exception as e:
                        logger.warning(f"Failed to parse listing: {e}")
                        continue

                # Navigate to next page
                next_btn = await page.query_selector(".pagination .next")
                if next_btn:
                    await next_btn.click()
                    await page.wait_for_load_state("networkidle")
                else:
                    break

        logger.info(f"Scraped {len(tenders)} tenders from TenderTiger")
        return tenders

    async def get_tender_details(self, page, tender_url: str) -> dict:
        """Scrape full details from an individual tender page."""
        await page.goto(tender_url)
        await page.wait_for_load_state("networkidle")

        details = {
            "url": tender_url,
            "full_description": await page.inner_text(".tender-description"),
            "documents": [],
            "scraped_at": datetime.utcnow().isoformat(),
        }

        # Extract attached documents
        doc_links = await page.query_selector_all(".document-download a")
        for doc in doc_links:
            details["documents"].append({
                "name": await doc.inner_text(),
                "url": await doc.get_attribute("href"),
            })

        return details
