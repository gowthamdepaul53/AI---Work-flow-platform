-- =============================================================================
-- Database Initialization — AI Workflow Platform
-- =============================================================================

-- Create databases
CREATE DATABASE platform_db;
CREATE DATABASE n8n_db;

\c platform_db;

-- Ticket responses (populated by the n8n workflow after each support ticket)
CREATE TABLE IF NOT EXISTS ticket_responses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id       VARCHAR(100) NOT NULL,
    summary         TEXT,
    response        TEXT,
    tokens_used     INTEGER DEFAULT 0,
    flagged         BOOLEAN DEFAULT FALSE,
    flag_reason     TEXT,
    hitl_status     VARCHAR(50) DEFAULT 'auto_approved',
    urgency         VARCHAR(20),
    customer_name   VARCHAR(255),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ticket_responses_ticket_id ON ticket_responses(ticket_id);
CREATE INDEX idx_ticket_responses_created_at ON ticket_responses(created_at DESC);
CREATE INDEX idx_ticket_responses_flagged ON ticket_responses(flagged) WHERE flagged = TRUE;

-- Token usage analytics (for Power BI / Grafana dashboards)
CREATE TABLE IF NOT EXISTS token_usage (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name      VARCHAR(100) NOT NULL,
    model           VARCHAR(100),
    tokens_in       INTEGER DEFAULT 0,
    tokens_out      INTEGER DEFAULT 0,
    total_tokens    INTEGER DEFAULT 0,
    latency_ms      FLOAT,
    success         BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_token_usage_agent ON token_usage(agent_name);
CREATE INDEX idx_token_usage_created ON token_usage(created_at DESC);

-- Human-in-the-loop approval queue
CREATE TABLE IF NOT EXISTS hitl_queue (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id       VARCHAR(100),
    agent_output    TEXT,
    flag_reason     TEXT,
    status          VARCHAR(20) DEFAULT 'pending',  -- pending | approved | rejected
    reviewed_by     VARCHAR(255),
    reviewed_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_hitl_status ON hitl_queue(status) WHERE status = 'pending';

-- Anomaly detection log (from n8n anomaly workflow)
CREATE TABLE IF NOT EXISTS anomaly_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type      VARCHAR(100),
    severity        VARCHAR(20),    -- LOW | MEDIUM | HIGH | CRITICAL
    description     TEXT,
    raw_data        JSONB,
    resolved        BOOLEAN DEFAULT FALSE,
    resolved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Analytics view for Power BI
CREATE OR REPLACE VIEW daily_metrics AS
SELECT
    DATE_TRUNC('day', created_at) AS day,
    COUNT(*)                       AS total_tickets,
    SUM(tokens_used)               AS total_tokens,
    AVG(tokens_used)               AS avg_tokens_per_ticket,
    COUNT(*) FILTER (WHERE flagged)        AS flagged_count,
    COUNT(*) FILTER (WHERE hitl_status = 'pending_review') AS pending_review,
    urgency,
    hitl_status
FROM ticket_responses
GROUP BY 1, urgency, hitl_status
ORDER BY 1 DESC;

-- Hourly throughput view (for 50K TPS validation)
CREATE OR REPLACE VIEW hourly_throughput AS
SELECT
    DATE_TRUNC('hour', created_at) AS hour,
    COUNT(*) AS requests,
    COUNT(*) / 3600.0 AS avg_rps,
    SUM(tokens_used) AS total_tokens
FROM ticket_responses
GROUP BY 1
ORDER BY 1 DESC;
