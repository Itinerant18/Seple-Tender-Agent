"""
SEPLE Tender Database — Pydantic Models
Data models matching the PostgreSQL schema for type-safe operations.
"""
from __future__ import annotations

import enum
from datetime import datetime, date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ─── Enums ─────────────────────────────────────────────────

class TenderStatus(str, enum.Enum):
    NEW = "new"
    UNDER_REVIEW = "under_review"
    QUALIFIED = "qualified"
    DISQUALIFIED = "disqualified"
    SUBMITTED = "submitted"
    WON = "won"
    LOST = "lost"
    CLOSED = "closed"
    IGNORED = "ignored"


class FitLabel(str, enum.Enum):
    STRONG_FIT = "strong_fit"
    POTENTIAL_FIT = "potential_fit"
    LOW_FIT = "low_fit"


class ConfidenceLevel(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MilestoneType(str, enum.Enum):
    PRE_BID_MEETING = "pre_bid_meeting"
    SITE_VISIT = "site_visit"
    CLARIFICATION_DEADLINE = "clarification_deadline"
    SUBMISSION_DEADLINE = "submission_deadline"


class NotificationType(str, enum.Enum):
    INSTANT_ALERT = "instant_alert"
    DAILY_DIGEST = "daily_digest"
    MILESTONE_REMINDER = "milestone_reminder"


class UserFeedback(str, enum.Enum):
    RELEVANT = "relevant"
    PURSUED = "pursued"
    WON = "won"
    LOST = "lost"
    IGNORED = "ignored"


# ─── Sub-models ────────────────────────────────────────────

class MandatoryActivity(BaseModel):
    date: Optional[str] = None
    location: Optional[str] = None
    mandatory: bool = False


class EligibilityAssessment(BaseModel):
    turnover_requirement: Optional[str] = None
    experience_requirement: Optional[str] = None
    oem_authorization: Optional[str] = None
    certifications: list[str] = Field(default_factory=list)
    local_office: Optional[str] = None
    other_conditions: list[str] = Field(default_factory=list)
    eligibility_gaps: list[str] = Field(default_factory=list)
    eligibility_status: str = "Needs Verification"


class DocumentReview(BaseModel):
    name: str
    reviewed: bool = False
    reason: Optional[str] = None


# ─── Core Models ───────────────────────────────────────────

class Source(BaseModel):
    id: Optional[UUID] = None
    name: str
    base_url: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None


class RawTender(BaseModel):
    """Raw tender data as scraped from a portal — before processing."""
    title: str
    description: Optional[str] = None
    tender_reference: Optional[str] = None
    value: Optional[str] = None
    deadline: Optional[str] = None
    publication_date: Optional[str] = None
    issuing_authority: Optional[str] = None
    location: Optional[str] = None
    category: Optional[str] = None
    url: Optional[str] = None
    source: str  # TenderTiger, Tender247, GeM, CPPP
    scraped_at: Optional[str] = None
    search_term: Optional[str] = None
    documents: list[dict] = Field(default_factory=list)


class Tender(BaseModel):
    """Full tender model after processing and classification."""
    id: Optional[UUID] = None
    fingerprint: Optional[str] = None
    tender_reference: Optional[str] = None
    title: str
    description: Optional[str] = None
    scope_summary: Optional[str] = None
    category: Optional[str] = None
    product_categories: list[str] = Field(default_factory=list)
    tender_type: Optional[str] = None
    value_raw: Optional[str] = None
    value_inr: Optional[float] = None
    emd_amount: Optional[str] = None
    tender_fee: Optional[str] = None
    deadline: Optional[datetime] = None
    publication_date: Optional[date] = None
    issuing_authority: Optional[str] = None
    location: Optional[str] = None
    source_id: Optional[UUID] = None
    source_url: Optional[str] = None
    status: TenderStatus = TenderStatus.NEW

    # Classification
    fit_classification: Optional[FitLabel] = None
    confidence: Optional[ConfidenceLevel] = None
    matched_keywords: list[str] = Field(default_factory=list)
    matched_categories: list[str] = Field(default_factory=list)
    matching_rationale: Optional[str] = None

    # Verification
    gem_verified: bool = False
    gem_reference: Optional[str] = None

    # Corrigendum
    has_corrigendum: bool = False
    corrigendum_count: int = 0
    last_corrigendum_at: Optional[datetime] = None
    original_deadline: Optional[datetime] = None

    # Eligibility
    eligibility_status: Optional[str] = None
    eligibility_gaps: list[str] = Field(default_factory=list)

    # Mandatory activities
    pre_bid_meeting: Optional[MandatoryActivity] = None
    site_visit: Optional[MandatoryActivity] = None
    clarification_deadline: Optional[datetime] = None

    # Routing
    kavach_routing: bool = False
    instant_alert_sent: bool = False

    # Feedback (F14)
    user_feedback: Optional[UserFeedback] = None
    feedback_notes: Optional[str] = None
    feedback_at: Optional[datetime] = None

    scraped_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TenderDocument(BaseModel):
    id: Optional[UUID] = None
    tender_id: UUID
    filename: str
    file_url: Optional[str] = None
    file_path: Optional[str] = None
    mime_type: Optional[str] = None
    extracted_text: Optional[str] = None
    file_size: Optional[int] = None
    is_corrigendum: bool = False
    created_at: Optional[datetime] = None


class TenderAnalysis(BaseModel):
    id: Optional[UUID] = None
    tender_id: Optional[UUID] = None  # set by repository after the tender row is inserted
    fit_classification: Optional[FitLabel] = None
    confidence: Optional[ConfidenceLevel] = None
    matched_keywords: list[str] = Field(default_factory=list)
    matched_categories: list[str] = Field(default_factory=list)
    matching_rationale: Optional[str] = None
    scope_summary: Optional[str] = None
    key_requirements: list[str] = Field(default_factory=list)
    eligibility_assessment: Optional[EligibilityAssessment] = None
    mandatory_activities: Optional[dict] = None
    uncertainty_notes: list[str] = Field(default_factory=list)
    documents_reviewed: list[DocumentReview] = Field(default_factory=list)
    synopsis_md: Optional[str] = None
    raw_analysis: Optional[dict] = None
    analysis_model: Optional[str] = None
    analyzed_at: Optional[datetime] = None


class Notification(BaseModel):
    id: Optional[UUID] = None
    tender_id: Optional[UUID] = None
    channel: str  # slack, email, digest
    notification_type: NotificationType
    recipient: Optional[str] = None
    subject: Optional[str] = None
    message: Optional[str] = None
    status: str = "pending"
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class ScrapeRun(BaseModel):
    id: Optional[UUID] = None
    source_id: Optional[UUID] = None
    source_name: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    tenders_found: int = 0
    tenders_new: int = 0
    tenders_updated: int = 0
    duplicates_skipped: int = 0
    status: str = "running"
    error_message: Optional[str] = None
    search_keywords: list[str] = Field(default_factory=list)


class Milestone(BaseModel):
    id: Optional[UUID] = None
    tender_id: UUID
    milestone_type: MilestoneType
    milestone_date: datetime
    location: Optional[str] = None
    is_mandatory: bool = False
    reminder_7d_sent: bool = False
    reminder_3d_sent: bool = False
    reminder_1d_sent: bool = False
    created_at: Optional[datetime] = None


class AuditEntry(BaseModel):
    id: Optional[UUID] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[UUID] = None
    details: Optional[dict] = None
    performed_by: str = "system"
    created_at: Optional[datetime] = None
