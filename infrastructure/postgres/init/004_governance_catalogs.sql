-- Clinical governance catalogs: constraints, dose rules, interactions, GDMT, dose safety.
-- Applied on fresh Postgres via docker-entrypoint-initdb.d; idempotent for re-runs.

CREATE TABLE IF NOT EXISTS constraint_rules (
    id BIGSERIAL PRIMARY KEY,
    constraint_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft',
    risk_names TEXT[] NOT NULL DEFAULT '{}',
    severity_any TEXT[] NOT NULL DEFAULT '{}',
    target_drug_class TEXT,
    action TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence_ref TEXT,
    clinical_sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    source TEXT NOT NULL,
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    retired_by TEXT,
    retired_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_constraint_rules_id_version
    ON constraint_rules (constraint_id, version);

CREATE TABLE IF NOT EXISTS constraint_rule_history (
    history_id BIGSERIAL PRIMARY KEY,
    constraint_id TEXT NOT NULL,
    status_from TEXT,
    status_to TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_constraint_rules_status ON constraint_rules (status);
CREATE INDEX IF NOT EXISTS idx_constraint_rules_target_drug_class ON constraint_rules (target_drug_class);
CREATE INDEX IF NOT EXISTS idx_constraint_rule_history_constraint
    ON constraint_rule_history (constraint_id, changed_at DESC);

CREATE TABLE IF NOT EXISTS dose_rules (
    id BIGSERIAL PRIMARY KEY,
    dose_rule_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft',
    drug_keys TEXT[] NOT NULL DEFAULT '{}',
    drug_class TEXT,
    calculation_type TEXT NOT NULL,
    rule_body JSONB NOT NULL,
    evidence_ref TEXT,
    clinical_sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    source TEXT NOT NULL,
    safety_tier TEXT,
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    retired_by TEXT,
    retired_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_dose_rules_id_version ON dose_rules (dose_rule_id, version);

CREATE TABLE IF NOT EXISTS dose_rule_history (
    history_id BIGSERIAL PRIMARY KEY,
    dose_rule_id TEXT NOT NULL,
    status_from TEXT,
    status_to TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_dose_rules_status ON dose_rules (status);
CREATE INDEX IF NOT EXISTS idx_dose_rule_history_dose_rule
    ON dose_rule_history (dose_rule_id, changed_at DESC);

CREATE TABLE IF NOT EXISTS interaction_rules (
    id BIGSERIAL PRIMARY KEY,
    interaction_rule_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft',
    drug_set_a TEXT[] NOT NULL DEFAULT '{}',
    drug_set_b TEXT[] NOT NULL DEFAULT '{}',
    severity TEXT NOT NULL DEFAULT 'moderate',
    target TEXT,
    rule_body JSONB NOT NULL,
    evidence_ref TEXT,
    clinical_sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    source TEXT NOT NULL,
    safety_tier TEXT,
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    retired_by TEXT,
    retired_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_interaction_rules_id_version
    ON interaction_rules (interaction_rule_id, version);

CREATE TABLE IF NOT EXISTS interaction_rule_history (
    history_id BIGSERIAL PRIMARY KEY,
    interaction_rule_id TEXT NOT NULL,
    status_from TEXT,
    status_to TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_interaction_rules_status ON interaction_rules (status);
CREATE INDEX IF NOT EXISTS idx_interaction_rule_history_ix
    ON interaction_rule_history (interaction_rule_id, changed_at DESC);

CREATE TABLE IF NOT EXISTS gdmt_policies (
    id BIGSERIAL PRIMARY KEY,
    gdmt_policy_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft',
    drug_class_key TEXT NOT NULL,
    display_label TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    policy_body JSONB NOT NULL,
    evidence_ref TEXT,
    clinical_sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    source TEXT NOT NULL,
    safety_tier TEXT,
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    retired_by TEXT,
    retired_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_gdmt_policies_id_version ON gdmt_policies (gdmt_policy_id, version);

CREATE TABLE IF NOT EXISTS gdmt_policy_history (
    history_id BIGSERIAL PRIMARY KEY,
    gdmt_policy_id TEXT NOT NULL,
    status_from TEXT,
    status_to TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_gdmt_policies_status ON gdmt_policies (status);
CREATE INDEX IF NOT EXISTS idx_gdmt_policy_history_policy
    ON gdmt_policy_history (gdmt_policy_id, changed_at DESC);

CREATE TABLE IF NOT EXISTS dose_safety_warnings (
    id BIGSERIAL PRIMARY KEY,
    dose_safety_warning_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft',
    drug_keys TEXT[] NOT NULL DEFAULT '{}',
    target TEXT,
    default_severity TEXT NOT NULL DEFAULT 'moderate',
    rule_body JSONB NOT NULL,
    evidence_ref TEXT,
    clinical_sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    source TEXT NOT NULL,
    safety_tier TEXT,
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    retired_by TEXT,
    retired_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_dose_safety_warnings_id_version
    ON dose_safety_warnings (dose_safety_warning_id, version);

CREATE TABLE IF NOT EXISTS dose_safety_warning_history (
    history_id BIGSERIAL PRIMARY KEY,
    dose_safety_warning_id TEXT NOT NULL,
    status_from TEXT,
    status_to TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_dose_safety_warnings_status ON dose_safety_warnings (status);
CREATE INDEX IF NOT EXISTS idx_dose_safety_warning_history_warning
    ON dose_safety_warning_history (dose_safety_warning_id, changed_at DESC);
