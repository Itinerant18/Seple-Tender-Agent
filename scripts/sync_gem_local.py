"""Zero-cost local GeM sync: scrape GeM from an Indian ISP and upload to /api/tenders/ingest.

bidplus.gem.gov.in refuses TCP connections from AWS Singapore datacenter IPs but
responds cleanly over Indian residential/office broadband (~270 tenders in ~15s).
This script runs GeMConnector locally and forwards the RawTender batch to the
production API, avoiding any paid proxy subscription.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path
import sys

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import ingest_client  # noqa: E402

# Overridable in tests; lazily loaded directly from gem_direct.py to avoid
# importing connectors/__init__.py (which requires playwright at import time).
GeMConnector = None


def _load_gem_connector_cls():
    return ingest_client.load_module_direct(
        "connectors_gem_direct", "connectors/gem_direct.py"
    ).GeMConnector


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("sync_gem_local")


async def run_sync(*, api_url: str, max_results: int, dry_run: bool) -> dict:
    """Scrape GeM tenders locally and upload them to /api/tenders/ingest."""
    connector_cls = GeMConnector or _load_gem_connector_cls()
    connector = connector_cls()
    try:
        tenders = await connector.scrape_tenders(max_results=max_results)
    finally:
        await connector.close()

    logger.info("Scraped %d GeM tenders locally", len(tenders))
    if dry_run:
        return {"status": "dry_run", "scraped": len(tenders)}

    result = await ingest_client.upload_tenders(
        connector.source_name, tenders, api_url=api_url
    )
    logger.info("Ingest accepted: %s", result)
    return result


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Sync GeM tenders to production API.")
    parser.add_argument(
        "--api-url",
        default=os.getenv("TENDER_API_URL", "https://api.seple.in"),
        help="Target Tender API base URL (default: https://api.seple.in)",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=300,
        help="Maximum GeM tenders to scrape per run (default: 300)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape locally and log counts without uploading",
    )
    args = parser.parse_args()
    asyncio.run(run_sync(api_url=args.api_url, max_results=args.max_results, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
