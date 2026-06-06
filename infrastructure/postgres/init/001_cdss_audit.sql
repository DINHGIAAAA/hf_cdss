CREATE TABLE IF NOT EXISTS cdss_audit_events (
    id BIGSERIAL PRIMARY KEY,
    case_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cdss_audit_case_created
    ON cdss_audit_events (case_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_cdss_audit_event_created
    ON cdss_audit_events (event_type, created_at DESC);

