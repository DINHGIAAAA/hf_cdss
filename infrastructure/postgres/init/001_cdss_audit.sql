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

CREATE TABLE IF NOT EXISTS chat_conversations (
    conversation_id TEXT PRIMARY KEY,
    case_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_messages (
    message_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES chat_conversations(conversation_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_patient_drafts (
    conversation_id TEXT PRIMARY KEY REFERENCES chat_conversations(conversation_id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    patient JSONB NOT NULL,
    source TEXT NOT NULL DEFAULT 'chat',
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_created
    ON chat_messages (conversation_id, created_at ASC);

CREATE INDEX IF NOT EXISTS idx_chat_conversations_case_updated
    ON chat_conversations (case_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_patient_drafts_case_updated
    ON chat_patient_drafts (case_id, updated_at DESC);

