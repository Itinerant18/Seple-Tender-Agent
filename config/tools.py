"""
SEPLE Tender Platform — Tool Configuration
All external tool settings in one place.
Credentials always come from environment variables.
"""
import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import unquote, urlsplit, urlunsplit


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

@dataclass
class PlaywrightConfig:
    headless: bool = True
    slow_mo: int = 500          # ms between actions — appears more human
    timeout: int = 30000        # 30 seconds
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    # Session storage path — keeps login alive across runs
    session_dir: str = os.path.join(
        os.path.expanduser("~"), ".seple", "browser_sessions"
    )

@dataclass
class FirecrawlConfig:
    api_key: str = os.getenv("FIRECRAWL_API_KEY", "")
    base_url: str = "https://api.firecrawl.dev"
    # Free tier: 500 pages/month
    # Use only for complex JS pages, not every page
    formats: list = None

    def __post_init__(self):
        self.formats = ["markdown", "links"]

@dataclass
class BrowserUseConfig:
    # AI-driven browser control — fallback only
    # Uses your existing LLM key
    llm_provider: str = os.getenv("LLM_PROVIDER", "anthropic")
    model: str = os.getenv("LLM_MODEL", "claude-3-5-haiku-20241022")
    api_key: str = os.getenv("ANTHROPIC_API_KEY", os.getenv("OPENAI_API_KEY", "")) # Fallback to OpenAI key if anthropic missing
    max_steps: int = 20         # Limit AI browser steps per task
    headless: bool = False      # Show browser when AI is controlling

# Singleton instances
playwright_config = PlaywrightConfig()
firecrawl_config = FirecrawlConfig()
browser_use_config = BrowserUseConfig()
