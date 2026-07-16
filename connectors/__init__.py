"""
SEPLE Tender Connectors
Scraping and ingestion modules for external tender sources.
"""
from .base import BaseConnector
from .tender_tiger import TenderTigerConnector
from .tender247 import Tender247Connector
from .email_parser import EmailParserConnector
from .gem_direct import GeMConnector

__all__ = [
    "BaseConnector",
    "TenderTigerConnector",
    "Tender247Connector",
    "EmailParserConnector",
    "GeMConnector"
]
