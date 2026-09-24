"""Scrapy web extract provider.

Fallback extraction backend using httpx + parsel (Scrapy's parsing engine)
for cases where the primary provider returns empty or falsy content.
Implements extract-only capability.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from agent.web_search_provider import WebSearchProvider

logger = logging.getLogger(__name__)


class ScrapyWebSearchProvider(WebSearchProvider):
    """Scrapy-style web content extraction provider.

    Uses httpx + parsel (Scrapy's parsing engine) for simple, reliable
    extraction without the full Scrapy reactor complexity. This provider
    is extract-only (no search capability) and serves as a fallback when
    primary providers return empty content.
    """

    @property
    def name(self) -> str:
        return "scrapy"

    @property
    def display_name(self) -> str:
        return "Scrapy (Fallback)"

    def is_available(self) -> bool:
        """Return True when httpx and parsel are importable."""
        try:
            import httpx  # noqa: F401
            import parsel  # noqa: F401
            return True
        except ImportError:
            return False

    def supports_search(self) -> bool:
        return False

    def supports_extract(self) -> bool:
        return True

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        raise NotImplementedError("Scrapy provider does not support search")

    async def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        """Extract content from URLs using httpx + parsel.

        Runs in a thread pool to avoid blocking the event loop.
        Each URL is fetched with a timeout and the content is extracted
        using CSS/XPath selectors to get clean text content.
        """
        from tools.interrupt import is_interrupted as _is_interrupted

        if _is_interrupted():
            return [{"url": u, "error": "Interrupted", "title": ""} for u in urls]

        format = kwargs.get("format")
        results: List[Dict[str, Any]] = []

        for url in urls:
            if _is_interrupted():
                results.append({"url": url, "error": "Interrupted", "title": ""})
                continue

            try:
                logger.info("Scrapy fallback scraping: %s", url)
                result = await asyncio.wait_for(
                    asyncio.to_thread(self._scrape_single, url, format),
                    timeout=60,
                )
                results.append(result)
            except asyncio.TimeoutError:
                logger.warning("Scrapy fallback scrape timed out for %s", url)
                results.append({
                    "url": url,
                    "title": "",
                    "content": "",
                    "raw_content": "",
                    "error": "Scrapy fallback scrape timed out after 60s",
                })
            except Exception as exc:  # noqa: BLE001
                logger.debug("Scrapy fallback scrape failed for %s: %s", url, exc)
                results.append({
                    "url": url,
                    "title": "",
                    "content": "",
                    "raw_content": "",
                    "error": str(exc),
                })

        return results

    def _scrape_single(self, url: str, format: Optional[str]) -> Dict[str, Any]:
        """Synchronous HTTP fetch and parse for a single URL.

        Uses httpx for fetching and parsel (Scrapy's parser) for extraction.
        """
        import httpx
        from parsel import Selector

        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; Scrapy/2.11; +https://scrapy.org)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
            
            with httpx.Client(
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
                headers=headers,
            ) as client:
                response = client.get(url)
                response.raise_for_status()
                
                # Get final URL after redirects
                final_url = str(response.url)
                
                # Parse HTML with parsel (Scrapy's selector engine)
                selector = Selector(text=response.text)
                
                # Extract title
                title = selector.css("title::text").get() or ""
                
                # Extract main content using multiple strategies
                content = self._extract_content(selector)
                
                # For html format, return raw HTML
                if format == "html":
                    chosen_content = response.text
                else:
                    chosen_content = content
                
                return {
                    "url": final_url,
                    "title": title.strip() if title else "",
                    "content": chosen_content,
                    "raw_content": chosen_content,
                    "metadata": {
                        "sourceURL": final_url,
                        "status": response.status_code,
                    },
                }
                
        except httpx.HTTPStatusError as exc:
            return {
                "url": url,
                "title": "",
                "content": "",
                "raw_content": "",
                "error": f"HTTP error {exc.response.status_code}: {exc}",
            }
        except httpx.TimeoutException:
            return {
                "url": url,
                "title": "",
                "content": "",
                "raw_content": "",
                "error": "Request timed out after 30s",
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "url": url,
                "title": "",
                "content": "",
                "raw_content": "",
                "error": f"Scrapy fallback error: {exc}",
            }

    def _extract_content(self, selector: "Selector") -> str:
        """Extract clean text content from the page using parsel selectors."""
        # Create a copy to avoid modifying the original
        # Remove script, style, nav, footer, header elements
        for element in selector.css("script, style, nav, footer, header, aside, .advertisement, .ads, .sidebar"):
            element.drop()
        
        # Try to find main content area
        main_selectors = [
            "main",
            "article",
            "[role='main']",
            ".main-content",
            ".content",
            "#content",
            ".post-content",
            ".entry-content",
        ]
        
        content_text = ""
        for sel in main_selectors:
            elements = selector.css(sel)
            if elements:
                content_text = " ".join(elements.css("::text").getall())
                break
        
        # Fallback: get all text from body
        if not content_text:
            content_text = " ".join(selector.css("body ::text").getall())
        
        # Clean up whitespace
        content_text = re.sub(r"\s+", " ", content_text).strip()
        
        return content_text

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Scrapy (Fallback)",
            "badge": "free · fallback",
            "tag": "Extract-only fallback for when primary providers return empty content",
            "env_vars": [],
        }