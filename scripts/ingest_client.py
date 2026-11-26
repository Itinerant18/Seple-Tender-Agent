"""Shared HTTP client helper for local-to-production /api/tenders/ingest uploads."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Iterable

import httpx

from database.models import RawTender

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_module_direct(name: str, rel_path: str):
    """Load a connector module directly without importing connectors/__init__.py."""
    path = REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def upload_tenders(
    source: str,
    tenders: Iterable[RawTender],
    *,
    api_url: str,
    timeout: int = 60,
) -> dict:
    """POST a scraped RawTender batch to /api/tenders/ingest with Bearer auth."""
    token = (os.getenv("TENDER_INGEST_TOKEN") or "").strip()
    if not token:
        raise RuntimeError(
            "TENDER_INGEST_TOKEN is not set; add it to .env before uploading."
        )

    items = list(tenders)
    endpoint = f"{api_url.rstrip('/')}/api/tenders/ingest"
    payload = {
        "source": source,
        "tenders": [t.model_dump() for t in items],
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            endpoint,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()
