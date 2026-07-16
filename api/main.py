"""
SEPLE Tender API
FastAPI service providing internal access to tender data.
"""
import os
import logging
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI(
    title="SEPLE Tender Intelligence API",
    description="Internal API for the SEPLE Tender Intelligence Platform",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Models ────────────────────────────────────────────────────

class TenderResponse(BaseModel):
    id: str
    title: str
    source: str
    category: Optional[str] = None
    value_inr: Optional[float] = None
    value_formatted: Optional[str] = None
    deadline: Optional[str] = None
    status: str = "new"
    relevance_score: Optional[float] = None
    url: Optional[str] = None


class ScanTriggerResponse(BaseModel):
    message: str
    started_at: str


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str


# ─── Endpoints ─────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        timestamp=datetime.utcnow().isoformat(),
    )


@app.get("/tenders", response_model=list[TenderResponse])
async def list_tenders(
    status: Optional[str] = Query(None, description="Filter by status"),
    source: Optional[str] = Query(None, description="Filter by source"),
    category: Optional[str] = Query(None, description="Filter by category"),
    min_value: Optional[float] = Query(None, description="Minimum value in INR"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List tenders with optional filters."""
    # TODO: Replace with actual database query
    return []


@app.get("/tenders/{tender_id}", response_model=TenderResponse)
async def get_tender(tender_id: str):
    """Get a specific tender by ID."""
    # TODO: Replace with actual database lookup
    raise HTTPException(status_code=404, detail="Tender not found")


@app.post("/scan/trigger", response_model=ScanTriggerResponse)
async def trigger_scan():
    """Manually trigger a tender scan."""
    from scheduler.daily_scan import DailyScanScheduler

    scheduler = DailyScanScheduler()
    # Run in background
    import asyncio
    asyncio.create_task(scheduler.run_daily_scan())

    return ScanTriggerResponse(
        message="Scan triggered successfully",
        started_at=datetime.utcnow().isoformat(),
    )


@app.get("/stats")
async def get_stats():
    """Get platform statistics."""
    # TODO: Replace with actual database stats
    return {
        "total_tenders": 0,
        "tenders_today": 0,
        "sources_active": 0,
        "last_scan": None,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
