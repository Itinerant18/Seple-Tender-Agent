"""
SEPLE Tender API
FastAPI backend for internal tooling, stats dashboard, and ad-hoc scans.
"""
import hmac
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from database import repository
from database.db import close_pool, init_schema
from database.models import FitLabel, RawTender, TenderStatus, UserFeedback
from scheduler.daily_scan import ScannerOrchestrator

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting SEPLE Tender API...")
    await init_schema()
    # Auto-close expired/stale tenders so the dashboard never shows a 2024
    # notice as live. A DB hiccup here must not keep the API down — the next
    # scan cycle syncs again.
    try:
        await repository.sync_expired_tenders()
    except Exception:
        logger.exception("Expired-tender sync failed at startup; continuing")
    yield
    # Shutdown
    logger.info("Shutting down SEPLE Tender API...")
    await close_pool()

app = FastAPI(title="SEPLE Tender Intelligence Platform", lifespan=lifespan)

# Allow CORS for internal dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    """Root endpoint - redirect or return platform info."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")

@app.get("/health")
async def health_check():
    """Service health check."""
    from database.db import health_check as db_health
    db_ok = await db_health()
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "service": "Tender API"
    }

@app.get("/api/tenders")
async def get_tenders(
    status: Optional[TenderStatus] = None,
    fit: Optional[FitLabel] = None,
    source: Optional[str] = None,
    category: Optional[str] = None,
    min_value: Optional[float] = None,
    q: Optional[str] = Query(None, max_length=200),
    closing_soon: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    """List tenders with optional filtering.

    Expired and stale tenders are hidden in every view — there is no flag that
    reveals them. closing_soon=true narrows the board to live tenders close
    to their closing date (the urgent view). Every row carries a computed
    is_expired flag for badging.
    """
    # Over-fetch one row to answer "is there a next page". A COUNT(*) would need
    # the WHERE builder factored out of list_tenders for a number the UI does not
    # show; revisit if the board ever wants "page 7 of 18".
    rows = await repository.list_tenders(
        status=status,
        fit=fit,
        source_name=source,
        category=category,
        min_value=min_value,
        q=q,
        closing_soon=closing_soon,
        limit=limit + 1,
        offset=offset
    )
    has_more = len(rows) > limit
    tenders = rows[:limit]
    return {
        "data": tenders,
        "count": len(tenders),
        "offset": offset,
        "has_more": has_more,
    }

@app.get("/api/tenders/{tender_id}")
async def get_tender_detail(tender_id: uuid.UUID):
    """Get full details of a specific tender."""
    tender = await repository.get_tender(tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")
    return tender

@app.post("/api/tenders/{tender_id}/feedback")
async def record_feedback(tender_id: uuid.UUID, feedback: UserFeedback, notes: str = None):
    """Record human feedback on a tender (F14)."""
    tender = await repository.get_tender(tender_id)
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")
        
    await repository.record_feedback(tender_id, feedback, notes)
    return {"status": "success", "message": "Feedback recorded"}

@app.get("/api/stats")
async def get_dashboard_stats():
    """Get high-level statistics for the dashboard."""
    return await repository.get_stats()

@app.post("/api/scan/trigger")
async def trigger_scan(background_tasks: BackgroundTasks):
    """Manually trigger the daily scan pipeline in the background."""
    background_tasks.add_task(_scan_with_expiry_sync)
    return {"status": "accepted", "message": "Scan triggered in background"}


async def _scan_with_expiry_sync() -> None:
    """Manual scan with the scheduled cycle's expiry hygiene.

    The scheduled run_cycle syncs expired/stale tenders before AND after the
    scan; a bare run_daily_scan does neither, so deployments driven by this
    endpoint let 'new' rows with past deadlines pile up unclosed between API
    restarts. Same order as run_cycle: clean state in, backfilled deadlines
    closed before the task returns.
    """
    try:
        await repository.sync_expired_tenders()
    except Exception:
        logger.exception("Expired-tender sync failed before manual scan; continuing")
    try:
        await ScannerOrchestrator().run_daily_scan()
    finally:
        try:
            await repository.sync_expired_tenders()
        except Exception:
            logger.exception("Expired-tender sync failed after manual scan; continuing")


class TenderIngestRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=64)
    tenders: List[RawTender] = Field(default_factory=list, max_length=1000)


def _verify_ingest_token(authorization: Optional[str]) -> None:
    expected = (os.getenv("TENDER_INGEST_TOKEN") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Tender ingest is not configured (missing TENDER_INGEST_TOKEN).",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    provided = authorization[len("Bearer "):].strip()
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="Invalid ingest token")


@app.post("/api/tenders/ingest", status_code=202)
async def ingest_tenders(
    payload: TenderIngestRequest,
    background_tasks: BackgroundTasks,
    authorization: Optional[str] = Header(None),
):
    """Ingest pre-scraped RawTender rows from an Indian/local runner into RDS."""
    _verify_ingest_token(authorization)
    run_id = await repository.start_scrape_run(payload.source, [])
    background_tasks.add_task(_ingest_batch, run_id, payload.source, payload.tenders)
    return {
        "status": "accepted",
        "run_id": str(run_id),
        "source": payload.source,
        "received": len(payload.tenders),
    }


async def _ingest_batch(
    run_id: uuid.UUID,
    source: str,
    raw_tenders: List[RawTender],
) -> None:
    """Process an ingested RawTender batch through dedup, classification, and expiry sync."""
    orchestrator = ScannerOrchestrator()
    stored = 0
    try:
        await repository.sync_expired_tenders()
    except Exception:
        logger.exception("Expired-tender sync failed before ingest; continuing")

    try:
        for raw in raw_tenders:
            try:
                tender = await orchestrator._process_raw(raw)
                if tender is not None:
                    stored += 1
            except Exception:
                logger.exception("Failed to process ingested %s tender: %s", source, raw.title)
        status = "success_no_results" if not raw_tenders else "completed"
        await repository.complete_scrape_run(
            run_id,
            tenders_found=len(raw_tenders),
            tenders_new=stored,
            duplicates_skipped=max(0, len(raw_tenders) - stored),
            status=status,
        )
    except Exception as e:
        logger.exception("Ingest batch %s (%s) failed", run_id, source)
        await repository.complete_scrape_run(run_id, error=str(e))
    finally:
        try:
            await repository.sync_expired_tenders()
        except Exception:
            logger.exception("Expired-tender sync failed after ingest; continuing")

@app.get("/api/tenders/export")
async def export_tenders():
    """Export tenders to Excel/CSV (Placeholder for F13)"""
    return {"status": "not_implemented", "message": "Excel export coming in Phase 2"}
