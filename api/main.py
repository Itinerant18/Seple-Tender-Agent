"""
SEPLE Tender API
FastAPI backend for internal tooling, stats dashboard, and ad-hoc scans.
"""
import uuid
import logging
from typing import List, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from database import repository
from database.db import init_schema, close_pool
from database.models import FitLabel, TenderStatus, UserFeedback
from scheduler.daily_scan import ScannerOrchestrator

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting SEPLE Tender API...")
    await init_schema()
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
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    """List tenders with optional filtering."""
    tenders = await repository.list_tenders(
        status=status,
        fit=fit,
        source_name=source,
        category=category,
        min_value=min_value,
        q=q,
        limit=limit,
        offset=offset
    )
    return {"data": tenders, "count": len(tenders)}

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
    orchestrator = ScannerOrchestrator()
    background_tasks.add_task(orchestrator.run_daily_scan)
    return {"status": "accepted", "message": "Scan triggered in background"}

@app.get("/api/tenders/export")
async def export_tenders():
    """Export tenders to Excel/CSV (Placeholder for F13)"""
    return {"status": "not_implemented", "message": "Excel export coming in Phase 2"}
