"""
SEPLE Tender Platform — Tool Configuration
All external tool settings in one place.
Credentials always come from environment variables.
"""
import os
from dataclasses import dataclass

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
