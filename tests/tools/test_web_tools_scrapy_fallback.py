import asyncio
import pytest
from typing import Any, Dict, List, Optional
from tools import web_tools

# We use the isolated async event loop fixture for async tests.
pytestmark = pytest.mark.asyncio

class MockScrapyProvider:
    def __init__(self, available: bool = True, results: Optional[List[Dict[str, Any]]] = None, raises: bool = False):
        self._available = available
        self._results = results or []
        self._raises = raises
        self.called_urls = []

    def is_available(self) -> bool:
        return self._available

    async def extract(self, urls: List[str], format: Optional[str] = None) -> List[Dict[str, Any]]:
        if self._raises:
            raise Exception("Mock Scrapy Error")
        self.called_urls.extend(urls)
        # return one result per URL or whatever was configured
        if len(self._results) == len(urls):
            return self._results
        # otherwise just return some dummy results
        return [
            {
                "url": url,
                "title": f"Scrapy title for {url}",
                "content": f"Scrapy content for {url}",
                "raw_content": f"Scrapy raw_content for {url}",
            }
            for url in urls
        ]

@pytest.fixture
def mock_registry(monkeypatch):
    class RegistryMock:
        def __init__(self):
            self.provider = MockScrapyProvider()
        def get_provider(self, name: str):
            if name == "scrapy":
                return self.provider
            return None
    
    registry = RegistryMock()
    # Need to patch the get_provider function in agent.web_search_registry since _scrapy_fallback_extract imports it locally
    # It imports it like: from agent.web_search_registry import get_provider
    # We can patch sys.modules or use monkeypatch.setattr on the module before it's imported
    import agent.web_search_registry
    monkeypatch.setattr(agent.web_search_registry, "get_provider", registry.get_provider)
    return registry

@pytest.fixture
def enable_config(monkeypatch):
    monkeypatch.setattr(web_tools, "_load_web_config", lambda: {"scrapy_fallback": True}, raising=False)
    # Also patch hermes_cli.config.load_config which is what _scrapy_fallback_extract uses locally
    import hermes_cli.config
    monkeypatch.setattr(hermes_cli.config, "load_config", lambda: {"web": {"scrapy_fallback": True}})

@pytest.fixture
def disable_config(monkeypatch):
    import hermes_cli.config
    monkeypatch.setattr(hermes_cli.config, "load_config", lambda: {"web": {"scrapy_fallback": False}})

async def test_fallback_disabled_in_config(disable_config, mock_registry):
    safe_urls = ["https://example.com"]
    safe_indices = [0]
    results = [{"url": "https://example.com", "content": "", "error": "Primary error"}]
    
    updated = await web_tools._scrapy_fallback_extract(safe_urls, safe_indices, results, "markdown")
    
    assert updated == results
    assert len(mock_registry.provider.called_urls) == 0

async def test_fallback_not_needed(enable_config, mock_registry):
    safe_urls = ["https://example.com", "https://example.org"]
    safe_indices = [0, 1]
    results = [
        {"url": "https://example.com", "content": "valid content with deadline", "raw_content": "valid content with deadline"},
        {"url": "https://example.org", "content": "valid content with deadline", "raw_content": "valid content with deadline"}
    ]
    
    updated = await web_tools._scrapy_fallback_extract(safe_urls, safe_indices, results, "markdown")
    
    assert updated == results
    assert len(mock_registry.provider.called_urls) == 0

async def test_fallback_triggered_for_empty_content(enable_config, mock_registry):
    safe_urls = ["https://example.com", "https://example.org"]
    safe_indices = [0, 1]
    results = [
        {"url": "https://example.com", "content": "valid content with deadline", "raw_content": "valid content with deadline"},
        {"url": "https://example.org", "content": "", "error": "Empty primary result"}
    ]
    
    updated = await web_tools._scrapy_fallback_extract(safe_urls, safe_indices, results, "markdown")
    
    # Provider should have been called for the second URL
    assert mock_registry.provider.called_urls == ["https://example.org"]
    
    # First result unchanged
    assert updated[0]["content"] == "valid content with deadline"
    
    # Second result updated with scrapy fallback
    assert updated[1]["content"] == "Scrapy content for https://example.org"
    assert updated[1]["title"] == "Scrapy title for https://example.org"

async def test_fallback_preserves_error_if_scrapy_fails(enable_config, mock_registry):
    mock_registry.provider._results = [
        {"url": "https://example.com", "content": "", "error": "Scrapy failed too"}
    ]
    
    safe_urls = ["https://example.com"]
    safe_indices = [0]
    results = [{"url": "https://example.com", "content": "", "error": "Primary failed"}]
    
    updated = await web_tools._scrapy_fallback_extract(safe_urls, safe_indices, results, "markdown")
    
    # The original result with original error should be returned because scrapy also failed
    assert updated[0]["error"] == "Primary failed"
    assert updated[0]["content"] == ""

async def test_fallback_handles_provider_exception(enable_config, mock_registry):
    mock_registry.provider._raises = True
    
    safe_urls = ["https://example.com"]
    safe_indices = [0]
    results = [{"url": "https://example.com", "content": "", "error": "Primary failed"}]
    
    updated = await web_tools._scrapy_fallback_extract(safe_urls, safe_indices, results, "markdown")
    
    # Should catch exception and return original results
    assert updated == results

async def test_fallback_skips_when_provider_unavailable(enable_config, mock_registry):
    mock_registry.provider._available = False
    
    safe_urls = ["https://example.com"]
    safe_indices = [0]
    results = [{"url": "https://example.com", "content": "", "error": "Primary failed"}]
    
    updated = await web_tools._scrapy_fallback_extract(safe_urls, safe_indices, results, "markdown")
    
    # Should skip extraction and return original results
    assert updated == results
    assert len(mock_registry.provider.called_urls) == 0
