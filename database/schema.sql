-- SEPLE Tender Platform Database Schema
-- PostgreSQL schema for storing and querying tender data

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- Core Tables
-- ============================================================

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
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fingerprint     VARCHAR(32) NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    description     TEXT,
    category        VARCHAR(200),
    value_raw       VARCHAR(200),
    value_inr       NUMERIC(18, 2),
    deadline        TIMESTAMP WITH TIME ZONE,
    issuing_authority VARCHAR(500),
    location        VARCHAR(300),
    source_id       UUID REFERENCES sources(id),
    source_url      VARCHAR(1000),
    status          VARCHAR(50) DEFAULT 'new',  -- new, analyzed, qualified, disqualified, applied
    gem_verified    BOOLEAN DEFAULT false,
    gem_reference   VARCHAR(100),
    scraped_at      TIMESTAMP WITH TIME ZONE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tender documents (PDFs, attachments)
CREATE TABLE IF NOT EXISTS tender_documents (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tender_id   UUID NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
    filename    VARCHAR(500) NOT NULL,
    file_url    VARCHAR(1000),
    file_path   VARCHAR(1000),
    mime_type   VARCHAR(100),
    extracted_text TEXT,
    file_size   INTEGER,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- AI analysis results
CREATE TABLE IF NOT EXISTS tender_analysis (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tender_id       UUID NOT NULL REFERENCES tenders(id) ON DELETE CASCADE,
    relevance_score NUMERIC(5, 2),      -- 0-100 relevance score
    risk_score      NUMERIC(5, 2),      -- 0-100 risk assessment
    opportunity_score NUMERIC(5, 2),    -- 0-100 opportunity rating
    summary         TEXT,               -- AI-generated summary
    key_requirements TEXT[],            -- Array of key requirements
    recommended_action VARCHAR(50),     -- apply, skip, review
    analysis_model  VARCHAR(100),       -- LLM model used
    raw_analysis    JSONB,              -- Full LLM response
    analyzed_at     TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Notification log
CREATE TABLE IF NOT EXISTS notifications (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tender_id       UUID REFERENCES tenders(id),
    channel         VARCHAR(50) NOT NULL,  -- slack, email
    recipient       VARCHAR(300),
    message         TEXT,
    status          VARCHAR(50) DEFAULT 'pending',  -- pending, sent, failed
    sent_at         TIMESTAMP WITH TIME ZONE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Scrape run history
CREATE TABLE IF NOT EXISTS scrape_runs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id       UUID REFERENCES sources(id),
    started_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at    TIMESTAMP WITH TIME ZONE,
    tenders_found   INTEGER DEFAULT 0,
    tenders_new     INTEGER DEFAULT 0,
    tenders_updated INTEGER DEFAULT 0,
    status          VARCHAR(50) DEFAULT 'running',  -- running, completed, failed
    error_message   TEXT
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
CREATE INDEX IF NOT EXISTS idx_analysis_tender ON tender_analysis(tender_id);
CREATE INDEX IF NOT EXISTS idx_documents_tender ON tender_documents(tender_id);
CREATE INDEX IF NOT EXISTS idx_notifications_tender ON notifications(tender_id);
CREATE INDEX IF NOT EXISTS idx_scrape_runs_source ON scrape_runs(source_id);

-- Full-text search index on tender title and description
CREATE INDEX IF NOT EXISTS idx_tenders_fulltext ON tenders
    USING GIN (to_tsvector('english', coalesce(title, '') || ' ' || coalesce(description, '')));

-- ============================================================
-- Seed Data
-- ============================================================

INSERT INTO sources (name, base_url) VALUES
    ('TenderTiger', 'https://www.tendertiger.com'),
    ('Tender247', 'https://www.tender247.com'),
    ('GeM', 'https://gem.gov.in')
ON CONFLICT (name) DO NOTHING;
