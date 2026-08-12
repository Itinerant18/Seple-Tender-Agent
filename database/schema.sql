-- SEPLE Tender Platform Database Schema
-- PostgreSQL schema for storing and querying tender data

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- Core Tables
-- ============================================================

-- Status enum type
DO $$ BEGIN
    CREATE TYPE tender_status AS ENUM (
        'new',
        'under_review',
        'qualified',
        'disqualified',
        'submitted',
        'won',
        'lost',
        'closed',
        'ignored'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE fit_label AS ENUM ('strong_fit', 'potential_fit', 'low_fit');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE confidence_level AS ENUM ('high', 'medium', 'low');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Tender sources (TenderTiger, Tender247, GeM, etc.)
CREATE TABLE IF NOT EXISTS sources (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(100) NOT NULL UNIQUE,
    base_url    VARCHAR(500),
    is_active   BOOLEAN DEFAULT true,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Main tenders table
CREATE TABLE IF NOT EXISTS tenders (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fingerprint         VARCHAR(32) NOT NULL UNIQUE,
    tender_reference    VARCHAR(200),
    title               TEXT NOT NULL,
    description         TEXT,
    scope_summary       TEXT,
    category            VARCHAR(200),
    product_categories  TEXT[],
    tender_type         VARCHAR(100),
    value_raw           VARCHAR(200),
    value_inr           NUMERIC(18, 2),
    emd_amount          VARCHAR(200),
    tender_fee          VARCHAR(200),
    deadline            TIMESTAMP WITH TIME ZONE,
    publication_date    DATE,
    issuing_authority   VARCHAR(500),
    location            VARCHAR(300),
    source_id           UUID REFERENCES sources(id),
    source_url          VARCHAR(1000),
    status              tender_status DEFAULT 'new',
    fit_classification  fit_label,
    confidence          confidence_level,
    matched_keywords    TEXT[],
    matched_categories  TEXT[],
    matching_rationale  TEXT,
    gem_verified        BOOLEAN DEFAULT false,
    gem_reference       VARCHAR(100),

    -- Corrigendum tracking
    has_corrigendum     BOOLEAN DEFAULT false,
    corrigendum_count   INTEGER DEFAULT 0,
    last_corrigendum_at TIMESTAMP WITH TIME ZONE,
    original_deadline   TIMESTAMP WITH TIME ZONE,

    -- Eligibility
    eligibility_status  VARCHAR(50),
    eligibility_gaps    TEXT[],

    -- Mandatory activities
    pre_bid_meeting     JSONB,
    site_visit          JSONB,
    clarification_deadline TIMESTAMP WITH TIME ZONE,

    -- Routing
    kavach_routing      BOOLEAN DEFAULT false,
    instant_alert_sent  BOOLEAN DEFAULT false,

    -- User feedback (F14 — design for it from day one)
    user_feedback       VARCHAR(50),  -- relevant, pursued, won, lost, ignored
    feedback_notes      TEXT,
    feedback_at         TIMESTAMP WITH TIME ZONE,

    scraped_at          TIMESTAMP WITH TIME ZONE,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at          TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tender documents (PDFs, attachments)
CREATE TABLE IF NOT EXISTS tender_documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tender_id       UUID NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
    filename        VARCHAR(500) NOT NULL,
    file_url        VARCHAR(1000),
    file_path       VARCHAR(1000),
    mime_type       VARCHAR(100),
    extracted_text  TEXT,
    file_size       INTEGER,
    is_corrigendum  BOOLEAN DEFAULT false,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- AI analysis results
CREATE TABLE IF NOT EXISTS tender_analysis (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tender_id           UUID NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
    fit_classification  fit_label,
    confidence          confidence_level,
    matched_keywords    TEXT[],
    matched_categories  TEXT[],
    matching_rationale  TEXT,
    scope_summary       TEXT,
    key_requirements    TEXT[],
    eligibility_assessment JSONB,
    mandatory_activities   JSONB,
    uncertainty_notes   TEXT[],
    documents_reviewed  JSONB,
    synopsis_md         TEXT,
    raw_analysis        JSONB,
    analysis_model      VARCHAR(100),
    analyzed_at         TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Notification log
CREATE TABLE IF NOT EXISTS notifications (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tender_id       UUID REFERENCES tenders(id),
    channel         VARCHAR(50) NOT NULL,  -- slack, email, digest
    notification_type VARCHAR(50) NOT NULL, -- instant_alert, daily_digest, milestone_reminder
    recipient       VARCHAR(300),
    subject         VARCHAR(500),
    message         TEXT,
    status          VARCHAR(50) DEFAULT 'pending',  -- pending, sent, failed
    error_message   TEXT,
    sent_at         TIMESTAMP WITH TIME ZONE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Scrape run history
CREATE TABLE IF NOT EXISTS scrape_runs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id       UUID REFERENCES sources(id),
    source_name     VARCHAR(100),
    started_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at    TIMESTAMP WITH TIME ZONE,
    tenders_found   INTEGER DEFAULT 0,
    tenders_new     INTEGER DEFAULT 0,
    tenders_updated INTEGER DEFAULT 0,
    duplicates_skipped INTEGER DEFAULT 0,
    status          VARCHAR(50) DEFAULT 'running',  -- running, completed, failed
    error_message   TEXT,
    search_keywords TEXT[]
);

-- Milestone reminders
CREATE TABLE IF NOT EXISTS milestones (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tender_id       UUID NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
    milestone_type  VARCHAR(50) NOT NULL,  -- pre_bid_meeting, site_visit, clarification_deadline, submission_deadline
    milestone_date  TIMESTAMP WITH TIME ZONE NOT NULL,
    location        VARCHAR(500),
    is_mandatory    BOOLEAN DEFAULT false,
    reminder_7d_sent BOOLEAN DEFAULT false,
    reminder_3d_sent BOOLEAN DEFAULT false,
    reminder_1d_sent BOOLEAN DEFAULT false,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Audit log (§9.4)
CREATE TABLE IF NOT EXISTS audit_log (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    action          VARCHAR(100) NOT NULL,  -- search, identify, classify, notify, update_status, feedback
    entity_type     VARCHAR(50),            -- tender, notification, scrape_run
    entity_id       UUID,
    details         JSONB,
    performed_by    VARCHAR(100) DEFAULT 'system',
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================
-- Indexes
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_tenders_deadline ON tenders(deadline);
CREATE INDEX IF NOT EXISTS idx_tenders_status ON tenders(status);
CREATE INDEX IF NOT EXISTS idx_tenders_source ON tenders(source_id);
CREATE INDEX IF NOT EXISTS idx_tenders_category ON tenders(category);
CREATE INDEX IF NOT EXISTS idx_tenders_created ON tenders(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tenders_value ON tenders(value_inr DESC);
CREATE INDEX IF NOT EXISTS idx_tenders_fit ON tenders(fit_classification);
CREATE INDEX IF NOT EXISTS idx_tenders_reference ON tenders(tender_reference);
CREATE INDEX IF NOT EXISTS idx_tenders_feedback ON tenders(user_feedback);
CREATE INDEX IF NOT EXISTS idx_analysis_tender ON tender_analysis(tender_id);
CREATE INDEX IF NOT EXISTS idx_documents_tender ON tender_documents(tender_id);
CREATE INDEX IF NOT EXISTS idx_notifications_tender ON notifications(tender_id);
CREATE INDEX IF NOT EXISTS idx_notifications_type ON notifications(notification_type);
CREATE INDEX IF NOT EXISTS idx_scrape_runs_source ON scrape_runs(source_id);
CREATE INDEX IF NOT EXISTS idx_milestones_tender ON milestones(tender_id);
CREATE INDEX IF NOT EXISTS idx_milestones_date ON milestones(milestone_date);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);

-- Full-text search index on tender title and description
CREATE INDEX IF NOT EXISTS idx_tenders_fulltext ON tenders
    USING GIN (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, '')));

-- ============================================================
-- Seed Data
-- ============================================================

INSERT INTO sources (name, base_url) VALUES
    ('TenderTiger', 'https://www.tendertiger.com'),
    ('Tender247', 'https://www.tender247.com'),
    ('GeM', 'https://gem.gov.in'),
    ('WebSearch', 'https://www.google.com')
ON CONFLICT (name) DO NOTHING;

-- CPPP is retired: eprocure.gov.in gates both its tender listing and its login
-- behind a captcha, so it cannot be scraped. Kept as an inactive row rather
-- than deleted, because historical scrape_runs still reference it.
UPDATE sources SET is_active = false WHERE name = 'CPPP';
