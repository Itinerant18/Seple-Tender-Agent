"""
SEPLE Tender247 Connector
Playwright-based scraper for Tender247.com portal.
"""
import os
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class Tender247Connector:
    """Scrapes tender listings from Tender247.com using Playwright."""

    BASE_URL = "https://www.tender247.com"

    def __init__(self):
        self.email = os.getenv("TENDER247_EMAIL")
        self.password = os.getenv("TENDER247_PASSWORD")
        if not self.email or not self.password:
            raise ValueError("TENDER247_EMAIL and TENDER247_PASSWORD must be set in .env")

    async def login(self, page):
        """Authenticate with Tender247 portal."""
        logger.info("Logging into Tender247...")
        await page.goto(f"{self.BASE_URL}/login")
        await page.fill('input[name="email"]', self.email)
        await page.fill('input[name="password"]', self.password)
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        logger.info("Tender247 login successful")

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
        search_terms = keywords or ["IT", "software", "technology", "consulting"]

        for term in search_terms:
            logger.info(f"Searching Tender247 for: {term}")
            await page.goto(f"{self.BASE_URL}/tenders?search={term}")
            await page.wait_for_load_state("networkidle")

            for page_num in range(1, max_pages + 1):
                listings = await page.query_selector_all(".tender-row")

                for listing in listings:
                    try:
                        tender = {
                            "title": await listing.inner_text(".title"),
                            "deadline": await listing.inner_text(".deadline"),
                            "value": await listing.inner_text(".value"),
                            "category": await listing.inner_text(".category"),
                            "url": await listing.get_attribute("a", "href"),
                            "source": "Tender247",
                            "scraped_at": datetime.utcnow().isoformat(),
                            "search_term": term,
                        }
                        tenders.append(tender)
                    except Exception as e:
                        logger.warning(f"Failed to parse listing: {e}")
                        continue

                next_btn = await page.query_selector(".next-page")
                if next_btn:
                    await next_btn.click()
                    await page.wait_for_load_state("networkidle")
                else:
                    break

        logger.info(f"Scraped {len(tenders)} tenders from Tender247")
        return tenders
