"""
SEPLE Tender Connectors — Base Interface
Abstract base class for all tender source connectors.
"""
from abc import ABC, abstractmethod
import logging
import os
from typing import List, Optional
from urllib.parse import unquote, urlsplit, urlunsplit
from database.models import RawTender, TenderDocument

logger = logging.getLogger(__name__)


def scraper_proxy_url() -> Optional[str]:
    """Return configured SCRAPER_PROXY URL, or None when unset/blank."""
    val = (os.getenv("SCRAPER_PROXY") or "").strip()
    return val or None


def playwright_proxy_config(proxy_url: Optional[str] = None) -> Optional[dict]:
    """Build Playwright proxy config with credentials split out of the URL.

    Chromium ignores user:pass embedded in a proxy URL — the proxy then
    answers 407 and every navigation hangs until it times out. Playwright
    wants them as separate username/password fields.
    """
    url = proxy_url if proxy_url is not None else scraper_proxy_url()
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

class BaseConnector(ABC):
    """
    Abstract base class defining the interface for all tender source connectors.
    Connectors are responsible for fetching raw tender data from specific sources (e.g., TenderTiger, Tender247).
    """
    
    def __init__(self, source_name: str, base_url: str):
        self.source_name = source_name
        self.base_url = base_url
        self.is_logged_in = False
        
    @abstractmethod
    async def login(self) -> bool:
        """
        Authenticate with the tender source.
        Returns True if successful, False otherwise.
        """
        pass

    @abstractmethod
    async def scrape_tenders(self, keywords: List[str] = None, days_back: int = 1) -> List[RawTender]:
        """
        Scrape tenders from the source based on keywords and time range.
        If keywords is None, fetch all latest tenders (if supported).
        Returns a list of RawTender objects.
        """
        pass

    @abstractmethod
    async def download_documents(self, tender_id: str, tender_url: str) -> List[TenderDocument]:
        """
        Download documents for a specific tender.
        Returns a list of TenderDocument objects (metadata, actual files saved to disk).
        """
        pass
        
    async def close(self):
        """
        Cleanup resources (e.g., close browser/HTTP sessions).
        """
        pass
