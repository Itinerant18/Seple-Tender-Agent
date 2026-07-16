"""
SEPLE Tender Connectors — Base Interface
Abstract base class for all tender source connectors.
"""
from abc import ABC, abstractmethod
import logging
from typing import List, Optional
from database.models import RawTender, TenderDocument

logger = logging.getLogger(__name__)

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
