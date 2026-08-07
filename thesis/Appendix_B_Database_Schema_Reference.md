# APPENDIX B: DATABASE SCHEMA REFERENCE

This appendix provides detailed specifications for all database tables used in the HF-CDSS. For a high-level overview, refer to Section 3.5 in Chapter 3 and Figure A.5 in Appendix A.

---

## B.1. Chat and Conversation Tables

### `chat_conversations`

Stores top-level conversation sessions. Each conversation is keyed by a stable, externally-generated UUID to support stateless load balancing and client-side history management.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `conversation_id` | `TEXT` | **PK** | Unique conversation identifier |
| `case_id` | `TEXT` | — | Optional clinical case reference |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `NOW()` | Conversation creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `NOW()` | Last message or draft update |

**Indexes**

| Index | Columns | Purpose |
|---|---|---|
| `idx_chat_conversations_case_updated` | `(case_id, updated_at DESC)` | Find most-recent conversation for a case |

---

### `chat_messages`

Stores individual messages within a conversation. Messages are immutable appends; edits are not supported.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `message_id` | `TEXT` | **PK** | Unique message identifier |
| `conversation_id` | `TEXT` | FK → `chat_conversations(conversation_id)`, ON DELETE CASCADE | Parent conversation |
| `role` | `TEXT` | NOT NULL | Message author role (`user`, `assistant`, `system`) |
| `content` | `TEXT` | NOT NULL | Message text content |
| `metadata` | `JSONB` | NOT NULL, DEFAULT `'{}'::jsonb` | Optional structured metadata (model, tokens, language, etc.) |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | Message creation timestamp |

**Indexes**

| Index | Columns | Purpose |
|---|---|---|
| `idx_chat_messages_conversation_created` | `(conversation_id, created_at ASC)` | Load messages in chronological order |

---

### `chat_patient_drafts`

Stores the most recently extracted patient profile for a conversation. A new draft row replaces the previous one on each patient-update event, so there is exactly one row per conversation.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `conversation_id` | `TEXT` | **PK**, FK → `chat_conversations(conversation_id)`, ON DELETE CASCADE | Parent conversation |
| `case_id` | `TEXT` | NOT NULL | Clinical case identifier |
| `patient` | `JSONB` | NOT NULL | Structured patient profile (demographics, labs, vitals, medications, diagnoses) |
| `source` | `TEXT` | NOT NULL, DEFAULT `'chat'` | Origin of the draft (`chat`, `manual`, `ehr_sync`) |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL | Last modification timestamp |

**Indexes**

| Index | Columns | Purpose |
|---|---|---|
| `idx_chat_patient_drafts_case_updated` | `(case_id, updated_at DESC)` | Find latest draft for a case |

---

## B.2. User Management Tables

### `users`

Stores user accounts and authentication credentials. Supports role-based access control via a PostgreSQL array column.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `TEXT` | **PK** | Unique user identifier |
| `username` | `TEXT` | NOT NULL, UNIQUE | Login username |
| `display_name` | `TEXT` | — | Human-readable display name |
| `password_hash` | `TEXT` | NOT NULL | Bcrypt-argon2 hashed password |
| `roles` | `TEXT[]` | NOT NULL, DEFAULT `'{}'` | Array of role names (e.g., `["clinician", "admin"]`) |
| `is_active` | `BOOLEAN` | NOT NULL, DEFAULT `TRUE` | Account active flag |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `NOW()` | Account creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `NOW()` | Last modification timestamp |

**Indexes**

| Index | Columns | Conditions | Purpose |
|---|---|---|---|
| `idx_users_username_active` | `(username)` | `is_active = TRUE` | Fast active-user lookup by username |

---

## B.3. Audit Tables

### `cdss_audit_events`

A comprehensive event log recording all clinical decision, governance, and system actions. This table is append-only; records are never updated or deleted.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `BIGSERIAL` | **PK** | Auto-incrementing event ID |
| `case_id` | `TEXT` | NOT NULL | Clinical case this event relates to |
| `event_type` | `TEXT` | NOT NULL | Event category (e.g., `recommendation_generated`, `rule_approved`, `draft_extracted`) |
| `payload` | `JSONB` | NOT NULL | Full event payload (structured per event type) |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `NOW()` | Event timestamp |

**Indexes**

| Index | Columns | Purpose |
|---|---|---|
| `idx_cdss_audit_case_created` | `(case_id, created_at DESC)` | Retrieve audit trail for a case |
| `idx_cdss_audit_event_created` | `(event_type, created_at DESC)` | Filter by event type with time order |

---

## B.4. Governance Catalog Tables

All governance catalog tables share a common lifecycle pattern: a main table holding the current active version of each rule, and a companion history table recording every status transition. The standard lifecycle states are `draft` → `approved` → `retired`. Each rule carries `version` for idempotent upserts and `metadata` (JSONB) for extensibility.

---

### `constraint_rules`

Executable GDMT eligibility constraints. Each rule maps a drug class and a set of predicates to a recommended action (e.g., "Approve", "Warn", "Block") with an associated risk label.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `BIGSERIAL` | **PK** | Auto-incrementing row ID |
| `constraint_id` | `TEXT` | NOT NULL | Stable rule identifier (used for upsert) |
| `version` | `INTEGER` | NOT NULL, DEFAULT `1` | Rule version number |
| `status` | `TEXT` | NOT NULL, DEFAULT `'draft'` | Lifecycle state: `draft`, `approved`, `retired` |
| `risk_names` | `TEXT[]` | NOT NULL, DEFAULT `'{}'` | Risk labels associated with this constraint |
| `severity_any` | `TEXT[]` | NOT NULL, DEFAULT `'{}'` | Severity thresholds (e.g., `["high", "moderate"]`) |
| `target_drug_class` | `TEXT` | — | GDMT drug class this rule applies to |
| `action` | `TEXT` | NOT NULL | Enforcement action: `approve`, `warn`, `block` |
| `reason` | `TEXT` | NOT NULL | Clinical rationale for this constraint |
| `evidence_ref` | `TEXT` | — | Citation or guideline reference |
| `clinical_sources` | `JSONB` | NOT NULL, DEFAULT `'[]'::jsonb` | Structured source metadata array |
| `source` | `TEXT` | NOT NULL | Ingestion source: `guideline`, `drug_label`, `manual` |
| `approved_by` | `TEXT` | — | Username of the approving admin |
| `approved_at` | `TIMESTAMPTZ` | — | Approval timestamp |
| `retired_by` | `TEXT` | — | Username of the retiring admin |
| `retired_at` | `TIMESTAMPTZ` | — | Retirement timestamp |
| `metadata` | `JSONB` | NOT NULL, DEFAULT `'{}'::jsonb` | Extensible rule metadata |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `NOW()` | Creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `NOW()` | Last modification timestamp |

**Indexes**

| Index | Columns | Purpose |
|---|---|---|
| `idx_constraint_rules_id_version` | `(constraint_id, version)` | UNIQUE — enforce version uniqueness per rule |
| `idx_constraint_rules_status` | `(status)` | Filter rules by lifecycle state |
| `idx_constraint_rules_target_drug_class` | `(target_drug_class)` | Fast lookup by drug class |

---

### `constraint_rule_history`

Append-only audit log of constraint rule status transitions. Records every approve, retire, or edit event with the acting user and optional reason.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `history_id` | `BIGSERIAL` | **PK** | Auto-incrementing history ID |
| `constraint_id` | `TEXT` | NOT NULL | Rule whose status changed |
| `status_from` | `TEXT` | — | Previous status (`NULL` on initial creation) |
| `status_to` | `TEXT` | NOT NULL | New status |
| `changed_by` | `TEXT` | NOT NULL | Username of the admin who made the change |
| `changed_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `NOW()` | Change timestamp |
| `reason` | `TEXT` | — | Optional free-text justification |

**Indexes**

| Index | Columns | Purpose |
|---|---|---|
| `idx_constraint_rule_history_constraint` | `(constraint_id, changed_at DESC)` | Timeline of changes for a rule |

---

### `dose_rules`

Medication dose calculation rules. Each rule specifies starting doses, target doses, titration schedules, and renal-function adjustments for a drug key or drug class.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `BIGSERIAL` | **PK** | Auto-incrementing row ID |
| `dose_rule_id` | `TEXT` | NOT NULL | Stable rule identifier |
| `version` | `INTEGER` | NOT NULL, DEFAULT `1` | Rule version number |
| `status` | `TEXT` | NOT NULL, DEFAULT `'draft'` | Lifecycle state |
| `drug_keys` | `TEXT[]` | NOT NULL, DEFAULT `'{}'` | Normalized drug substance keys this rule applies to |
| `drug_class` | `TEXT` | — | GDMT drug class grouping |
| `calculation_type` | `TEXT` | NOT NULL | Calculation type: `fixed`, `weight_based`, `renal_adjusted` |
| `rule_body` | `JSONB` | NOT NULL | Full dose logic: starting dose, target dose, titration steps, renal bands |
| `evidence_ref` | `TEXT` | — | Source citation |
| `clinical_sources` | `JSONB` | NOT NULL, DEFAULT `'[]'::jsonb` | Structured source metadata |
| `source` | `TEXT` | NOT NULL | Ingestion source |
| `safety_tier` | `TEXT` | — | Safety tier: `critical`, `high`, `moderate` |
| `approved_by` | `TEXT` | — | Approving admin username |
| `approved_at` | `TIMESTAMPTZ` | — | Approval timestamp |
| `retired_by` | `TEXT` | — | Retiring admin username |
| `retired_at` | `TIMESTAMPTZ` | — | Retirement timestamp |
| `metadata` | `JSONB` | NOT NULL, DEFAULT `'{}'::jsonb` | Extensible metadata |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `NOW()` | Creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `NOW()` | Last modification timestamp |

**Indexes**

| Index | Columns | Purpose |
|---|---|---|
| `idx_dose_rules_id_version` | `(dose_rule_id, version)` | UNIQUE — enforce version uniqueness |
| `idx_dose_rules_status` | `(status)` | Filter rules by lifecycle state |

---

### `dose_rule_history`

Audit log for dose rule status transitions.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `history_id` | `BIGSERIAL` | **PK** | Auto-incrementing history ID |
| `dose_rule_id` | `TEXT` | NOT NULL | Rule whose status changed |
| `status_from` | `TEXT` | — | Previous status |
| `status_to` | `TEXT` | NOT NULL | New status |
| `changed_by` | `TEXT` | NOT NULL | Username of the admin who made the change |
| `changed_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `NOW()` | Change timestamp |
| `reason` | `TEXT` | — | Optional justification |

**Indexes**

| Index | Columns | Purpose |
|---|---|---|
| `idx_dose_rule_history_dose_rule` | `(dose_rule_id, changed_at DESC)` | Timeline of changes for a dose rule |

---

### `interaction_rules`

Drug-drug interaction rules. Each rule pairs two drug sets (A and B), specifies severity, and embeds a management recommendation.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `BIGSERIAL` | **PK** | Auto-incrementing row ID |
| `interaction_rule_id` | `TEXT` | NOT NULL | Stable rule identifier |
| `version` | `INTEGER` | NOT NULL, DEFAULT `1` | Rule version number |
| `status` | `TEXT` | NOT NULL, DEFAULT `'draft'` | Lifecycle state |
| `drug_set_a` | `TEXT[]` | NOT NULL, DEFAULT `'{}'` | First drug set (normalized substance keys) |
| `drug_set_b` | `TEXT[]` | NOT NULL, DEFAULT `'{}'` | Second drug set (normalized substance keys) |
| `severity` | `TEXT` | NOT NULL, DEFAULT `'moderate'` | Interaction severity: `critical`, `high`, `moderate`, `low` |
| `target` | `TEXT` | — | Clinical target or condition this interaction affects |
| `rule_body` | `JSONB` | NOT NULL | Structured interaction logic and management guidance |
| `evidence_ref` | `TEXT` | — | Source citation |
| `clinical_sources` | `JSONB` | NOT NULL, DEFAULT `'[]'::jsonb` | Structured source metadata |
| `source` | `TEXT` | NOT NULL | Ingestion source |
| `safety_tier` | `TEXT` | — | Safety tier |
| `approved_by` | `TEXT` | — | Approving admin username |
| `approved_at` | `TIMESTAMPTZ` | — | Approval timestamp |
| `retired_by` | `TEXT` | — | Retiring admin username |
| `retired_at` | `TIMESTAMPTZ` | — | Retirement timestamp |
| `metadata` | `JSONB` | NOT NULL, DEFAULT `'{}'::jsonb` | Extensible metadata |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `NOW()` | Creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `NOW()` | Last modification timestamp |

**Indexes**

| Index | Columns | Purpose |
|---|---|---|
| `idx_interaction_rules_id_version` | `(interaction_rule_id, version)` | UNIQUE — enforce version uniqueness |
| `idx_interaction_rules_status` | `(status)` | Filter rules by lifecycle state |

---

### `interaction_rule_history`

Audit log for interaction rule status transitions.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `history_id` | `BIGSERIAL` | **PK** | Auto-incrementing history ID |
| `interaction_rule_id` | `TEXT` | NOT NULL | Rule whose status changed |
| `status_from` | `TEXT` | — | Previous status |
| `status_to` | `TEXT` | NOT NULL | New status |
| `changed_by` | `TEXT` | NOT NULL | Username of the admin who made the change |
| `changed_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `NOW()` | Change timestamp |
| `reason` | `TEXT` | — | Optional justification |

**Indexes**

| Index | Columns | Purpose |
|---|---|---|
| `idx_interaction_rule_history_ix` | `(interaction_rule_id, changed_at DESC)` | Timeline of changes for an interaction rule |

---

### `gdmt_policies`

Executable heart-failure GDMT class policies. Each policy defines which drug classes are recommended, contraindicated, or require monitoring for a given patient profile.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `BIGSERIAL` | **PK** | Auto-incrementing row ID |
| `gdmt_policy_id` | `TEXT` | NOT NULL | Stable policy identifier |
| `version` | `INTEGER` | NOT NULL, DEFAULT `1` | Policy version number |
| `status` | `TEXT` | NOT NULL, DEFAULT `'draft'` | Lifecycle state |
| `drug_class_key` | `TEXT` | NOT NULL | GDMT drug class key (e.g., `ace_inhibitor`, `arni`, `sglt2_inhibitor`) |
| `display_label` | `TEXT` | NOT NULL | Human-readable class label |
| `sort_order` | `INTEGER` | NOT NULL, DEFAULT `0` | Display ordering within a GDMT grid |
| `policy_body` | `JSONB` | NOT NULL | Full policy logic: indications, contraindications, monitoring requirements |
| `evidence_ref` | `TEXT` | — | Source citation |
| `clinical_sources` | `JSONB` | NOT NULL, DEFAULT `'[]'::jsonb` | Structured source metadata |
| `source` | `TEXT` | NOT NULL | Ingestion source |
| `safety_tier` | `TEXT` | — | Safety tier |
| `approved_by` | `TEXT` | — | Approving admin username |
| `approved_at` | `TIMESTAMPTZ` | — | Approval timestamp |
| `retired_by` | `TEXT` | — | Retiring admin username |
| `retired_at` | `TIMESTAMPTZ` | — | Retirement timestamp |
| `metadata` | `JSONB` | NOT NULL, DEFAULT `'{}'::jsonb` | Extensible metadata |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `NOW()` | Creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `NOW()` | Last modification timestamp |

**Indexes**

| Index | Columns | Purpose |
|---|---|---|
| `idx_gdmt_policies_id_version` | `(gdmt_policy_id, version)` | UNIQUE — enforce version uniqueness |
| `idx_gdmt_policies_status` | `(status)` | Filter policies by lifecycle state |

---

### `gdmt_policy_history`

Audit log for GDMT policy status transitions.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `history_id` | `BIGSERIAL` | **PK** | Auto-incrementing history ID |
| `gdmt_policy_id` | `TEXT` | NOT NULL | Policy whose status changed |
| `status_from` | `TEXT` | — | Previous status |
| `status_to` | `TEXT` | NOT NULL | New status |
| `changed_by` | `TEXT` | NOT NULL | Username of the admin who made the change |
| `changed_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `NOW()` | Change timestamp |
| `reason` | `TEXT` | — | Optional justification |

**Indexes**

| Index | Columns | Purpose |
|---|---|---|
| `idx_gdmt_policy_history_policy` | `(gdmt_policy_id, changed_at DESC)` | Timeline of changes for a GDMT policy |

---

### `dose_safety_warnings`

Numeric dose ceiling and safety predicate warnings. These rules fire when a computed or prescribed dose exceeds a defined threshold for the patient's clinical band (e.g., renal function, weight, age).

| Column | Type | Constraints | Description |
|---|---|---|---|
| `id` | `BIGSERIAL` | **PK** | Auto-incrementing row ID |
| `dose_safety_warning_id` | `TEXT` | NOT NULL | Stable warning identifier |
| `version` | `INTEGER` | NOT NULL, DEFAULT `1` | Warning version number |
| `status` | `TEXT` | NOT NULL, DEFAULT `'draft'` | Lifecycle state |
| `drug_keys` | `TEXT[]` | NOT NULL, DEFAULT `'{}'` | Normalized drug keys this warning applies to |
| `target` | `TEXT` | — | Clinical target context |
| `default_severity` | `TEXT` | NOT NULL, DEFAULT `'moderate'` | Default severity if not overridden |
| `rule_body` | `JSONB` | NOT NULL | Safety predicate: maximum dose, condition, override criteria |
| `evidence_ref` | `TEXT` | — | Source citation |
| `clinical_sources` | `JSONB` | NOT NULL, DEFAULT `'[]'::jsonb` | Structured source metadata |
| `source` | `TEXT` | NOT NULL | Ingestion source |
| `safety_tier` | `TEXT` | — | Safety tier |
| `approved_by` | `TEXT` | — | Approving admin username |
| `approved_at` | `TIMESTAMPTZ` | — | Approval timestamp |
| `retired_by` | `TEXT` | — | Retiring admin username |
| `retired_at` | `TIMESTAMPTZ` | — | Retirement timestamp |
| `metadata` | `JSONB` | NOT NULL, DEFAULT `'{}'::jsonb` | Extensible metadata |
| `created_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `NOW()` | Creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `NOW()` | Last modification timestamp |

**Indexes**

| Index | Columns | Purpose |
|---|---|---|
| `idx_dose_safety_warnings_id_version` | `(dose_safety_warning_id, version)` | UNIQUE — enforce version uniqueness |
| `idx_dose_safety_warnings_status` | `(status)` | Filter warnings by lifecycle state |

---

### `dose_safety_warning_history`

Audit log for dose safety warning status transitions.

| Column | Type | Constraints | Description |
|---|---|---|---|
| `history_id` | `BIGSERIAL` | **PK** | Auto-incrementing history ID |
| `dose_safety_warning_id` | `TEXT` | NOT NULL | Warning whose status changed |
| `status_from` | `TEXT` | — | Previous status |
| `status_to` | `TEXT` | NOT NULL | New status |
| `changed_by` | `TEXT` | NOT NULL | Username of the admin who made the change |
| `changed_at` | `TIMESTAMPTZ` | NOT NULL, DEFAULT `NOW()` | Change timestamp |
| `reason` | `TEXT` | — | Optional justification |

**Indexes**

| Index | Columns | Purpose |
|---|---|---|
| `idx_ddsw_history_warning` | `(dose_safety_warning_id, changed_at DESC)` | Timeline of changes for a dose safety warning |

---

## B.5. Database Summary

| # | Table | Purpose | History Table |
|---|---|---|---|
| 1 | `chat_conversations` | Top-level conversation sessions | — |
| 2 | `chat_messages` | Individual messages within a conversation | — |
| 3 | `chat_patient_drafts` | Persisted patient profile drafts | — |
| 4 | `users` | User accounts and RBAC | — |
| 5 | `cdss_audit_events` | Comprehensive event audit log | — |
| 6 | `constraint_rules` | GDMT eligibility constraints | `constraint_rule_history` |
| 7 | `dose_rules` | Medication dose calculation rules | `dose_rule_history` |
| 8 | `interaction_rules` | Drug-drug interaction rules | `interaction_rule_history` |
| 9 | `gdmt_policies` | GDMT class policies | `gdmt_policy_history` |
| 10 | `dose_safety_warnings` | Dose ceiling and safety warnings | `dose_safety_warning_history` |

**Total: 10 tables, 6 history tables, 15 indexes.**
