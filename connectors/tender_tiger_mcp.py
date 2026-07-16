"""
Tender Tiger MCP Server Connector
Official MCP server — replaces the Playwright scraper entirely once live.
Status: PENDING — awaiting sales confirmation from Ramesh Sinha
Contact: +91 99243 32267 / Sales@TenderTiger.com
Product page: https://www.tendertiger.com/Services/MCPServer
"""
import logging
import os

logger = logging.getLogger(__name__)


class TenderTigerMCPConnector:
    """
    Connects to Tender Tiger's official MCP server.
    Hermes speaks MCP natively — no browser automation needed.
    TODO: fill endpoint + auth after sales call confirms access.
    """

    def __init__(self):
        self.mcp_endpoint = os.getenv("TENDER_TIGER_MCP_ENDPOINT", "")
        self.mcp_api_key = os.getenv("TENDER_TIGER_MCP_KEY", "")
        self.enabled = bool(self.mcp_endpoint and self.mcp_api_key)

        if not self.enabled:
            logger.warning(
                "Tender Tiger MCP not configured — "
                "call Ramesh Sinha: +91 99243 32267"
            )

    async def search_tenders(self, keywords: list, max_results: int = 100) -> list:
        if not self.enabled:
            logger.error("MCP connector not configured")
            return []
        raise NotImplementedError(
            "MCP endpoint not yet configured — pending sales confirmation"
        )
