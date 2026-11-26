"""Zero-cost local Tender247 sync via visible browser session OR alert emails (.eml / IMAP).

Supports three modes:
- --eml PATH: parse a saved .eml / HTML Tender247 alert email and upload to /api/tenders/ingest
- --email-only: read recent Tender247 alert emails from IMAP (no browser, no Cloudflare)
- --interactive / auto: reuse Tender247 session on your Indian ISP or open a visible
  browser once so you can sign in / clear Cloudflare normally and persist storage_state
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path
import sys
from typing import Optional

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config.keywords import SEARCH_KEYWORDS  # noqa: E402
from scripts import ingest_client  # noqa: E402

# Overridable in tests; lazily loaded to avoid importing connectors/__init__.py.
Tender247Connector = None
EmailParserConnector = None


def _load_email_parser_cls():
    return ingest_client.load_module_direct(
        "connectors_email_parser", "connectors/email_parser.py"
    ).EmailParserConnector


def _load_tender247_cls():
    from connectors.tender247 import Tender247Connector as _T247
    return _T247


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("sync_tender247_local")


async def run_sync(
    *,
    api_url: str,
    mode: str = "auto",
    interactive: bool = False,
    eml_path: Optional[Path] = None,
    days_back: int = 2,
    dry_run: bool = False,
) -> dict:
    """Ingest Tender247 tenders via .eml, IMAP email, or local browser and upload."""
    email_cls = EmailParserConnector or _load_email_parser_cls()
    tenders = []

    if eml_path is not None:
        raw_bytes = Path(eml_path).read_bytes()
        parser = email_cls(source_name="Tender247")
        tenders = parser.parse_email_content(raw_bytes)
        logger.info("Parsed %d Tender247 tenders from %s", len(tenders), eml_path)
    elif mode == "email":
        parser = email_cls(source_name="Tender247")
        tenders = await parser.scrape_tenders(days_back=days_back)
        logger.info("Fetched %d Tender247 tenders from IMAP inbox", len(tenders))
    else:
        t247_cls = Tender247Connector or _load_tender247_cls()
        connector = t247_cls(
            headless=False if interactive else None,
            wait_for_manual_login=interactive,
        )
        try:
            tenders = await connector.scrape_tenders(keywords=SEARCH_KEYWORDS)
            logger.info("Scraped %d Tender247 tenders via browser", len(tenders))
        except Exception as err:
            if mode == "auto" and email_cls._imap_config() is not None:
                logger.warning(
                    "Tender247 browser scrape failed (%s); falling back to IMAP inbox", err
                )
                parser = email_cls(source_name="Tender247")
                tenders = await parser.scrape_tenders(days_back=days_back)
            else:
                raise
        finally:
            await connector.close()

    if dry_run:
        return {"status": "dry_run", "scraped": len(tenders)}

    result = await ingest_client.upload_tenders(
        "Tender247", tenders, api_url=api_url
    )
    logger.info("Ingest accepted: %s", result)
    return result


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Sync Tender247 tenders locally to production API.")
    parser.add_argument(
        "--api-url",
        default=os.getenv("TENDER_API_URL", "https://api.seple.in"),
        help="Target Tender API base URL (default: https://api.seple.in)",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "browser", "email"),
        default="auto",
        help="auto = try browser then IMAP fallback; browser = portal only; email = IMAP only",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Open visible Chromium window if saved session expired / Cloudflare needs human login",
    )
    parser.add_argument(
        "--eml",
        type=Path,
        default=None,
        help="Parse a saved Tender247 .eml or .html digest file instead of IMAP/browser",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=2,
        help="Days back to search IMAP emails (default: 2)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse/scrape locally and print counts without uploading",
    )
    args = parser.parse_args()
    asyncio.run(
        run_sync(
            api_url=args.api_url,
            mode=args.mode,
            interactive=args.interactive,
            eml_path=args.eml,
            days_back=args.days_back,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
