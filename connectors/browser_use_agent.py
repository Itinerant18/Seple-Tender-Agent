"""
Browser-Use AI agent — fallback when Playwright selectors break.
Uses natural language to control browser.
Only used when standard scraping fails.

Written against browser-use 0.13.x, which ships its own LLM clients
(no langchain needed).

Credentials are passed via browser-use's sensitive_data mechanism:
the LLM only ever sees the placeholder names (x_email / x_password);
real values are substituted locally in the browser. Raw credentials
must never appear in the task prompt (PRD 9.3).
"""
import logging
from browser_use import Agent
from config.tools import browser_use_config

logger = logging.getLogger(__name__)

class BrowserUseAgent:
    def __init__(self):
        if browser_use_config.llm_provider == "anthropic":
            from browser_use.llm.anthropic.chat import ChatAnthropic
            self.llm = ChatAnthropic(model=browser_use_config.model)
        else:
            from browser_use.llm.openai.chat import ChatOpenAI
            self.llm = ChatOpenAI(model=browser_use_config.model)

    async def extract_tenders(
        self,
        portal_url: str,
        keyword: str,
        credentials: dict = None
    ) -> list:
        """
        AI-driven tender extraction — fallback only.
        Use when Playwright selectors break after portal UI changes.
        """
        task = f"""
        Go to {portal_url}.
        {"Login with email x_email and password x_password." if credentials else ""}
        Search for tenders related to: {keyword}
        Extract all visible tenders with:
        - Title
        - Reference number
        - Deadline
        - Value/EMD
        - Organization
        - URL
        Return as a list. Do not submit any forms other than search and login.
        Do not click any bid submission or payment links.
        Do not register, accept terms, or make any payment.
        """
        sensitive = None
        if credentials:
            sensitive = {
                "x_email": credentials["email"],
                "x_password": credentials["password"],
            }
        try:
            agent = Agent(
                task=task,
                llm=self.llm,
                sensitive_data=sensitive,
            )
            history = await agent.run(max_steps=browser_use_config.max_steps)
            return history.extracted_content() or []
        except Exception as e:
            logger.error(f"Browser-Use agent error: {e}")
            return []
