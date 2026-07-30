"""One-shot scheduler entrypoint for managed cron platforms such as Render."""

import asyncio
import logging

from dotenv import load_dotenv

from database import repository
from database.db import close_pool
from scheduler.run import run_cycle


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


async def main() -> None:
    load_dotenv()
    try:
        if not await repository.init_schema():
            raise RuntimeError("Database schema initialization failed")
        result = await run_cycle()
        if not result["scan_succeeded"]:
            raise RuntimeError("Tender scan failed; see preceding logs")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
