"""
Tender MCP Server — bridges the Hermes agent to the SEPLE tender pipeline.

This is the §19.4 "Hermes reads the tender DB" arrow. Hermes speaks MCP
natively; this stdio server exposes the tender-api REST endpoints as MCP tools
so the agent can query, summarize, and recommend tenders — and nothing else.

Guardrails (PRD §9.1) are enforced by ABSENCE: the only tools here are reads
plus two safe writes (trigger a scan, record human feedback). There is no
register/submit/pay/upload/send capability to call.

Run:  python -m tender_mcp.server
Config (cli-config.seple.yaml):
    mcp_servers:
      tenders:
        command: python
        args: ["-m", "tender_mcp.server"]
        env:
          TENDER_API_URL: http://tender-api:8000
"""
import os
import httpx
from mcp.server.fastmcp import FastMCP

API = os.getenv("TENDER_API_URL", "http://tender-api:8000").rstrip("/")
mcp = FastMCP("tenders")


def _get(path: str, **params):
    params = {k: v for k, v in params.items() if v is not None}
    with httpx.Client(base_url=API, timeout=30) as c:
        r = c.get(path, params=params)
        r.raise_for_status()
        return r.json()


def _post(path: str, **params):
    params = {k: v for k, v in params.items() if v is not None}
    with httpx.Client(base_url=API, timeout=30) as c:
        r = c.post(path, params=params)
        r.raise_for_status()
        return r.json()


@mcp.tool()
def list_tenders(fit: str | None = None, status: str | None = None,
                 category: str | None = None, source: str | None = None,
                 min_value: float | None = None, limit: int = 50) -> dict:
    """List tenders from the pipeline database, newest first.

    fit: strong_fit | potential_fit | low_fit
    status: new | under_review | qualified | disqualified | submitted | won
    category: e.g. 'CCTV', 'Fire Alarm', 'Access Control'
    source: TenderTiger | Tender247 | CPPP | GeM
    min_value: minimum tender value in INR
    """
    return _get("/api/tenders", fit=fit, status=status, category=category,
                source=source, min_value=min_value, limit=limit)


@mcp.tool()
def get_tender(tender_id: str) -> dict:
    """Full detail for one tender by its UUID, including analysis and eligibility."""
    return _get(f"/api/tenders/{tender_id}")


@mcp.tool()
def get_stats() -> dict:
    """High-level pipeline stats: counts by fit, status, source."""
    return _get("/api/stats")


@mcp.tool()
def trigger_scan() -> dict:
    """Kick off a discovery scan across all sources in the background.
    Read-only against the portals — finds and classifies, never submits."""
    return _post("/api/scan/trigger")


@mcp.tool()
def record_feedback(tender_id: str, feedback: str, notes: str | None = None) -> dict:
    """Record a human's verdict on a tender for the learning loop (PRD F14).
    feedback: relevant | pursued | won | lost | ignored"""
    return _post(f"/api/tenders/{tender_id}/feedback", feedback=feedback, notes=notes)


if __name__ == "__main__":
    mcp.run()
