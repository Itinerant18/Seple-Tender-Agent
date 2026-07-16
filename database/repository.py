"""
SEPLE Tender Database — Repository (CRUD + Audit)
All database operations with automatic audit logging.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from .db import get_connection
from .models import (
    AuditEntry, FitLabel, Milestone, MilestoneType, Notification,
    NotificationType, ScrapeRun, Tender, TenderAnalysis,
    TenderDocument, TenderStatus, UserFeedback,
)

logger = logging.getLogger(__name__)


# ─── Audit Helper ──────────────────────────────────────────

async def _audit(
    conn,
    action: str,
    entity_type: str = None,
    entity_id: UUID = None,
    details: dict = None,
    performed_by: str = "system",
):
    """Insert an audit log entry."""
    await conn.execute(
        """
        INSERT INTO audit_log (action, entity_type, entity_id, details, performed_by)
        VALUES ($1, $2, $3, $4::jsonb, $5)
        """,
        action,
        entity_type,
        entity_id,
        json.dumps(details) if details else None,
        performed_by,
    )


# ─── Tender CRUD ───────────────────────────────────────────

async def upsert_tender(tender: Tender) -> UUID:
    """Insert a new tender or update if fingerprint exists. Returns tender ID."""
    async with get_connection() as conn:
        # Check if fingerprint exists
        existing = await conn.fetchrow(
            "SELECT id FROM tenders WHERE fingerprint = $1",
            tender.fingerprint,
        )

        if existing:
            tender_id = existing["id"]
            await conn.execute(
                """
                UPDATE tenders SET
                    title = $2, description = $3, tender_reference = $4,
                    value_raw = $5, value_inr = $6, deadline = $7,
                    issuing_authority = $8, location = $9, source_url = $10,
                    updated_at = NOW()
                WHERE id = $1
                """,
                tender_id, tender.title, tender.description,
                tender.tender_reference, tender.value_raw, tender.value_inr,
                tender.deadline, tender.issuing_authority, tender.location,
                tender.source_url,
            )
            await _audit(conn, "update_tender", "tender", tender_id,
                         {"fingerprint": tender.fingerprint, "title": tender.title})
            return tender_id
        else:
            tender_id = await conn.fetchval(
                """
                INSERT INTO tenders (
                    fingerprint, tender_reference, title, description, scope_summary,
                    category, product_categories, tender_type,
                    value_raw, value_inr, emd_amount, tender_fee,
                    deadline, publication_date, issuing_authority, location,
                    source_id, source_url, status,
                    fit_classification, confidence,
                    matched_keywords, matched_categories, matching_rationale,
                    eligibility_status, eligibility_gaps,
                    pre_bid_meeting, site_visit, clarification_deadline,
                    kavach_routing, scraped_at
                ) VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8,
                    $9, $10, $11, $12,
                    $13, $14, $15, $16,
                    $17, $18, $19,
                    $20, $21,
                    $22, $23, $24,
                    $25, $26,
                    $27, $28, $29,
                    $30, $31
                ) RETURNING id
                """,
                tender.fingerprint, tender.tender_reference, tender.title,
                tender.description, tender.scope_summary,
                tender.category, tender.product_categories, tender.tender_type,
                tender.value_raw, tender.value_inr, tender.emd_amount, tender.tender_fee,
                tender.deadline, tender.publication_date, tender.issuing_authority,
                tender.location, tender.source_id, tender.source_url,
                tender.status.value if tender.status else "new",
                tender.fit_classification.value if tender.fit_classification else None,
                tender.confidence.value if tender.confidence else None,
                tender.matched_keywords, tender.matched_categories,
                tender.matching_rationale,
                tender.eligibility_status, tender.eligibility_gaps,
                json.dumps(tender.pre_bid_meeting.model_dump()) if tender.pre_bid_meeting else None,
                json.dumps(tender.site_visit.model_dump()) if tender.site_visit else None,
                tender.clarification_deadline,
                tender.kavach_routing, tender.scraped_at,
            )
            await _audit(conn, "create_tender", "tender", tender_id,
                         {"fingerprint": tender.fingerprint, "title": tender.title})
            return tender_id


async def get_tender(tender_id: UUID) -> Optional[dict]:
    """Get a single tender by ID."""
    async with get_connection() as conn:
        row = await conn.fetchrow("SELECT * FROM tenders WHERE id = $1", tender_id)
        return dict(row) if row else None


async def find_by_fingerprint(fingerprint: str) -> Optional[dict]:
    """Find a tender by its dedup fingerprint."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM tenders WHERE fingerprint = $1", fingerprint
        )
        return dict(row) if row else None


async def list_tenders(
    status: Optional[TenderStatus] = None,
    fit: Optional[FitLabel] = None,
    source_name: Optional[str] = None,
    category: Optional[str] = None,
    min_value: Optional[float] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List tenders with optional filters."""
    conditions = []
    params = []
    idx = 1

    if status:
        conditions.append(f"t.status = ${idx}")
        params.append(status.value)
        idx += 1
    if fit:
        conditions.append(f"t.fit_classification = ${idx}")
        params.append(fit.value)
        idx += 1
    if source_name:
        conditions.append(f"s.name = ${idx}")
        params.append(source_name)
        idx += 1
    if category:
        conditions.append(f"${idx} = ANY(t.product_categories)")
        params.append(category)
        idx += 1
    if min_value is not None:
        conditions.append(f"t.value_inr >= ${idx}")
        params.append(min_value)
        idx += 1

    where_clause = " AND ".join(conditions) if conditions else "TRUE"
    params.extend([limit, offset])

    query = f"""
        SELECT t.*, s.name as source_name
        FROM tenders t
        LEFT JOIN sources s ON t.source_id = s.id
        WHERE {where_clause}
        ORDER BY t.created_at DESC
        LIMIT ${idx} OFFSET ${idx + 1}
    """

    async with get_connection() as conn:
        rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]


async def update_status(tender_id: UUID, status: TenderStatus, performed_by: str = "system"):
    """Update tender status with audit trail."""
    async with get_connection() as conn:
        old_row = await conn.fetchrow(
            "SELECT status FROM tenders WHERE id = $1", tender_id
        )
        old_status = old_row["status"] if old_row else None

        await conn.execute(
            "UPDATE tenders SET status = $1, updated_at = NOW() WHERE id = $2",
            status.value, tender_id,
        )
        await _audit(conn, "update_status", "tender", tender_id,
                     {"old_status": old_status, "new_status": status.value},
                     performed_by)


async def record_feedback(
    tender_id: UUID,
    feedback: UserFeedback,
    notes: Optional[str] = None,
    performed_by: str = "presales",
):
    """Record user feedback on a tender (F14)."""
    async with get_connection() as conn:
        await conn.execute(
            """
            UPDATE tenders SET
                user_feedback = $1, feedback_notes = $2,
                feedback_at = NOW(), updated_at = NOW()
            WHERE id = $3
            """,
            feedback.value, notes, tender_id,
        )
        await _audit(conn, "feedback", "tender", tender_id,
                     {"feedback": feedback.value, "notes": notes},
                     performed_by)


# ─── Analysis ──────────────────────────────────────────────

async def save_analysis(analysis: TenderAnalysis) -> UUID:
    """Save an AI analysis result for a tender."""
    async with get_connection() as conn:
        analysis_id = await conn.fetchval(
            """
            INSERT INTO tender_analysis (
                tender_id, fit_classification, confidence,
                matched_keywords, matched_categories, matching_rationale,
                scope_summary, key_requirements,
                eligibility_assessment, mandatory_activities,
                uncertainty_notes, documents_reviewed,
                synopsis_md, raw_analysis, analysis_model
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8,
                $9::jsonb, $10::jsonb, $11, $12::jsonb,
                $13, $14::jsonb, $15
            ) RETURNING id
            """,
            analysis.tender_id,
            analysis.fit_classification.value if analysis.fit_classification else None,
            analysis.confidence.value if analysis.confidence else None,
            analysis.matched_keywords, analysis.matched_categories,
            analysis.matching_rationale,
            analysis.scope_summary, analysis.key_requirements,
            json.dumps(analysis.eligibility_assessment.model_dump()) if analysis.eligibility_assessment else None,
            json.dumps(analysis.mandatory_activities) if analysis.mandatory_activities else None,
            analysis.uncertainty_notes,
            json.dumps([d.model_dump() for d in analysis.documents_reviewed]) if analysis.documents_reviewed else None,
            analysis.synopsis_md,
            json.dumps(analysis.raw_analysis) if analysis.raw_analysis else None,
            analysis.analysis_model,
        )
        await _audit(conn, "analyze", "tender", analysis.tender_id,
                     {"analysis_id": str(analysis_id),
                      "fit": analysis.fit_classification.value if analysis.fit_classification else None})
        return analysis_id


async def get_pending_analysis(limit: int = 20) -> list[dict]:
    """Get tenders that haven't been analyzed yet."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT t.* FROM tenders t
            LEFT JOIN tender_analysis ta ON t.id = ta.tender_id
            WHERE ta.id IS NULL AND t.status = 'new'
            ORDER BY t.created_at ASC
            LIMIT $1
            """,
            limit,
        )
        return [dict(r) for r in rows]


# ─── Documents ─────────────────────────────────────────────

async def save_document(doc: TenderDocument) -> UUID:
    """Save a tender document record."""
    async with get_connection() as conn:
        doc_id = await conn.fetchval(
            """
            INSERT INTO tender_documents (
                tender_id, filename, file_url, file_path,
                mime_type, extracted_text, file_size, is_corrigendum
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            doc.tender_id, doc.filename, doc.file_url, doc.file_path,
            doc.mime_type, doc.extracted_text, doc.file_size, doc.is_corrigendum,
        )
        await _audit(conn, "save_document", "tender_document", doc_id,
                     {"tender_id": str(doc.tender_id), "filename": doc.filename})
        return doc_id


# ─── Milestones ────────────────────────────────────────────

async def upsert_milestone(milestone: Milestone) -> UUID:
    """Insert or update a milestone for a tender."""
    async with get_connection() as conn:
        existing = await conn.fetchrow(
            """
            SELECT id FROM milestones
            WHERE tender_id = $1 AND milestone_type = $2
            """,
            milestone.tender_id, milestone.milestone_type.value,
        )
        if existing:
            await conn.execute(
                """
                UPDATE milestones SET
                    milestone_date = $1, location = $2, is_mandatory = $3
                WHERE id = $4
                """,
                milestone.milestone_date, milestone.location,
                milestone.is_mandatory, existing["id"],
            )
            return existing["id"]
        else:
            return await conn.fetchval(
                """
                INSERT INTO milestones (
                    tender_id, milestone_type, milestone_date,
                    location, is_mandatory
                ) VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                milestone.tender_id, milestone.milestone_type.value,
                milestone.milestone_date, milestone.location, milestone.is_mandatory,
            )


async def get_upcoming_milestones(
    within_days: int = 7,
    reminder_level: str = "7d",
) -> list[dict]:
    """Get milestones coming up within N days that haven't had their reminder sent."""
    reminder_col = {
        "7d": "reminder_7d_sent",
        "3d": "reminder_3d_sent",
        "1d": "reminder_1d_sent",
    }.get(reminder_level, "reminder_7d_sent")

    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT m.*, t.title as tender_title, t.tender_reference,
                   t.issuing_authority, t.source_url
            FROM milestones m
            JOIN tenders t ON m.tender_id = t.id
            WHERE m.milestone_date <= NOW() + INTERVAL '{within_days} days'
              AND m.milestone_date > NOW()
              AND m.{reminder_col} = false
              AND t.status NOT IN ('closed', 'won', 'lost', 'ignored', 'disqualified')
            ORDER BY m.milestone_date ASC
            """,
        )
        return [dict(r) for r in rows]


async def mark_reminder_sent(milestone_id: UUID, level: str):
    """Mark a milestone reminder as sent."""
    col = {"7d": "reminder_7d_sent", "3d": "reminder_3d_sent", "1d": "reminder_1d_sent"}.get(level)
    if col:
        async with get_connection() as conn:
            await conn.execute(
                f"UPDATE milestones SET {col} = true WHERE id = $1",
                milestone_id,
            )


# ─── Scrape Runs ───────────────────────────────────────────

async def start_scrape_run(source_name: str, keywords: list[str] = None) -> UUID:
    """Record the start of a scrape run."""
    async with get_connection() as conn:
        source = await conn.fetchrow(
            "SELECT id FROM sources WHERE name = $1", source_name
        )
        run_id = await conn.fetchval(
            """
            INSERT INTO scrape_runs (source_id, source_name, search_keywords)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            source["id"] if source else None, source_name, keywords or [],
        )
        await _audit(conn, "start_scrape", "scrape_run", run_id,
                     {"source": source_name})
        return run_id


async def complete_scrape_run(
    run_id: UUID,
    tenders_found: int = 0,
    tenders_new: int = 0,
    tenders_updated: int = 0,
    duplicates_skipped: int = 0,
    error: Optional[str] = None,
):
    """Record the completion of a scrape run."""
    status = "failed" if error else "completed"
    async with get_connection() as conn:
        await conn.execute(
            """
            UPDATE scrape_runs SET
                completed_at = NOW(), tenders_found = $2,
                tenders_new = $3, tenders_updated = $4,
                duplicates_skipped = $5, status = $6, error_message = $7
            WHERE id = $1
            """,
            run_id, tenders_found, tenders_new, tenders_updated,
            duplicates_skipped, status, error,
        )
        await _audit(conn, "complete_scrape", "scrape_run", run_id,
                     {"status": status, "found": tenders_found, "new": tenders_new})


# ─── Notifications ─────────────────────────────────────────

async def log_notification(notification: Notification) -> UUID:
    """Log a notification attempt."""
    async with get_connection() as conn:
        notif_id = await conn.fetchval(
            """
            INSERT INTO notifications (
                tender_id, channel, notification_type,
                recipient, subject, message, status, sent_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
            """,
            notification.tender_id, notification.channel,
            notification.notification_type.value,
            notification.recipient, notification.subject, notification.message,
            notification.status,
            notification.sent_at if notification.status == "sent" else None,
        )
        return notif_id


# ─── Statistics ────────────────────────────────────────────

async def get_stats() -> dict:
    """Get platform statistics for the dashboard."""
    async with get_connection() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM tenders")
        today = await conn.fetchval(
            "SELECT COUNT(*) FROM tenders WHERE created_at >= CURRENT_DATE"
        )
        strong = await conn.fetchval(
            "SELECT COUNT(*) FROM tenders WHERE fit_classification = 'strong_fit'"
        )
        potential = await conn.fetchval(
            "SELECT COUNT(*) FROM tenders WHERE fit_classification = 'potential_fit'"
        )
        sources_active = await conn.fetchval(
            "SELECT COUNT(*) FROM sources WHERE is_active = true"
        )
        last_run = await conn.fetchrow(
            "SELECT completed_at, source_name FROM scrape_runs ORDER BY completed_at DESC NULLS LAST LIMIT 1"
        )
        upcoming = await conn.fetchval(
            """
            SELECT COUNT(*) FROM milestones
            WHERE milestone_date > NOW()
              AND milestone_date <= NOW() + INTERVAL '7 days'
            """
        )

        return {
            "total_tenders": total or 0,
            "tenders_today": today or 0,
            "strong_fit_count": strong or 0,
            "potential_fit_count": potential or 0,
            "sources_active": sources_active or 0,
            "last_scan": {
                "completed_at": last_run["completed_at"].isoformat() if last_run and last_run["completed_at"] else None,
                "source": last_run["source_name"] if last_run else None,
            } if last_run else None,
            "upcoming_milestones_7d": upcoming or 0,
        }
