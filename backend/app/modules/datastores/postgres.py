import logging
import re
from functools import lru_cache
from typing import Any

from app.core.config import settings
from app.core.request_context import current_request_id


logger = logging.getLogger(__name__)


def _escape_like(value: str) -> str:
    """Escape %, _, and \ characters for SQL LIKE/ILIKE patterns to prevent injection."""
    return re.sub(r"([%_\\])", r"\\\1", value)


# PHI fields that should be redacted from audit logs
_PHI_FIELDS = frozenset(
    {
        "message",
        "first_name",
        "last_name",
        "full_name",
        "email",
        "phone",
        "address",
        "date_of_birth",
        "ssn",
        "insurance_id",
        "mrn",
        "medical_record_number",
    }
)


def _redact_phi(data: Any, depth: int = 0) -> Any:
    """Recursively redact PHI fields from a data structure for safe audit logging."""
    if depth > 10:
        return "[MAX_DEPTH_EXCEEDED]"
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if key.lower() in _PHI_FIELDS or any(phi in key.lower() for phi in ["name", "email", "phone", "address"]):
                result[key] = "[REDACTED]"
            else:
                result[key] = _redact_phi(value, depth + 1)
        return result
    elif isinstance(data, list):
        return [_redact_phi(item, depth + 1) for item in data]
    else:
        return data


def redact_phi_for_audit(payload: dict[str, Any]) -> dict[str, Any]:
    """Redact PHI fields from audit payload before logging."""
    return _redact_phi(payload)


@lru_cache(maxsize=1)
def _psycopg():
    import psycopg

    return psycopg


@lru_cache(maxsize=1)
def postgres_pool():
    from psycopg_pool import ConnectionPool

    return ConnectionPool(
        conninfo=settings.postgres_dsn,
        min_size=settings.postgres_pool_min_size,
        max_size=settings.postgres_pool_max_size,
        kwargs={"connect_timeout": 5},
        open=True,
    )


def initialize_postgres() -> dict[str, Any]:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS cdss_audit_events (
                    id BIGSERIAL PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_cdss_audit_case_created "
                "ON cdss_audit_events (case_id, created_at DESC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_cdss_audit_event_created "
                "ON cdss_audit_events (event_type, created_at DESC)"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_conversations (
                    conversation_id TEXT PRIMARY KEY,
                    case_id TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    message_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES chat_conversations(conversation_id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_patient_drafts (
                    conversation_id TEXT PRIMARY KEY REFERENCES chat_conversations(conversation_id) ON DELETE CASCADE,
                    case_id TEXT NOT NULL,
                    patient JSONB NOT NULL,
                    source TEXT NOT NULL DEFAULT 'chat',
                    updated_at TIMESTAMPTZ NOT NULL
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_created "
                "ON chat_messages (conversation_id, created_at ASC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_conversations_case_updated "
                "ON chat_conversations (case_id, updated_at DESC)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_patient_drafts_case_updated "
                "ON chat_patient_drafts (case_id, updated_at DESC)"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    display_name TEXT,
                    password_hash TEXT NOT NULL,
                    roles TEXT[] NOT NULL DEFAULT '{}',
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_users_username_active "
                "ON users (username) WHERE is_active = TRUE"
            )
            cursor.execute(
                """
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
                )
                """
            )
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_constraint_rules_id_version "
                "ON constraint_rules (constraint_id, version)"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS constraint_rule_history (
                    history_id BIGSERIAL PRIMARY KEY,
                    constraint_id TEXT NOT NULL,
                    status_from TEXT,
                    status_to TEXT NOT NULL,
                    changed_by TEXT NOT NULL,
                    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    reason TEXT
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_constraint_rules_status "
                "ON constraint_rules (status)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_constraint_rules_target_drug_class "
                "ON constraint_rules (target_drug_class)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_constraint_rule_history_constraint "
                "ON constraint_rule_history (constraint_id, changed_at DESC)"
            )
            cursor.execute(
                """
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
                )
                """
            )
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_dose_rules_id_version "
                "ON dose_rules (dose_rule_id, version)"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS dose_rule_history (
                    history_id BIGSERIAL PRIMARY KEY,
                    dose_rule_id TEXT NOT NULL,
                    status_from TEXT,
                    status_to TEXT NOT NULL,
                    changed_by TEXT NOT NULL,
                    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    reason TEXT
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_dose_rules_status ON dose_rules (status)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_dose_rule_history_dose_rule "
                "ON dose_rule_history (dose_rule_id, changed_at DESC)"
            )
            cursor.execute(
                """
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
                )
                """
            )
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_interaction_rules_id_version "
                "ON interaction_rules (interaction_rule_id, version)"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS interaction_rule_history (
                    history_id BIGSERIAL PRIMARY KEY,
                    interaction_rule_id TEXT NOT NULL,
                    status_from TEXT,
                    status_to TEXT NOT NULL,
                    changed_by TEXT NOT NULL,
                    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    reason TEXT
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_interaction_rules_status ON interaction_rules (status)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_interaction_rule_history_ix "
                "ON interaction_rule_history (interaction_rule_id, changed_at DESC)"
            )
            cursor.execute(
                """
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
                )
                """
            )
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_gdmt_policies_id_version "
                "ON gdmt_policies (gdmt_policy_id, version)"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS gdmt_policy_history (
                    history_id BIGSERIAL PRIMARY KEY,
                    gdmt_policy_id TEXT NOT NULL,
                    status_from TEXT,
                    status_to TEXT NOT NULL,
                    changed_by TEXT NOT NULL,
                    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    reason TEXT
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_gdmt_policies_status ON gdmt_policies (status)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_gdmt_policy_history_policy "
                "ON gdmt_policy_history (gdmt_policy_id, changed_at DESC)"
            )
            cursor.execute(
                """
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
                )
                """
            )
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_dose_safety_warnings_id_version "
                "ON dose_safety_warnings (dose_safety_warning_id, version)"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS dose_safety_warning_history (
                    history_id BIGSERIAL PRIMARY KEY,
                    dose_safety_warning_id TEXT NOT NULL,
                    status_from TEXT,
                    status_to TEXT NOT NULL,
                    changed_by TEXT NOT NULL,
                    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    reason TEXT
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_dose_safety_warnings_status "
                "ON dose_safety_warnings (status)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_dose_safety_warning_history_warning "
                "ON dose_safety_warning_history (dose_safety_warning_id, changed_at DESC)"
            )
        connection.commit()

    from app.modules.datastores.users import seed_default_users

    seed_result = seed_default_users()
    return {
        "status": "ok",
        "tables": [
            "cdss_audit_events",
            "chat_conversations",
            "chat_messages",
            "chat_patient_drafts",
            "users",
            "constraint_rules",
            "constraint_rule_history",
            "dose_rules",
            "dose_rule_history",
            "interaction_rules",
            "interaction_rule_history",
            "gdmt_policies",
            "gdmt_policy_history",
            "dose_safety_warnings",
            "dose_safety_warning_history",
        ],
        "users_seed": seed_result,
    }


def write_audit_event(case_id: str, event_type: str, payload: dict[str, Any]) -> bool:
    if not settings.postgres_audit_enabled:
        return False
    # Redact PHI before logging
    safe_payload = redact_phi_for_audit(payload)
    safe_payload.setdefault(
        "audit_metadata",
        {
            "schema_version": settings.audit_schema_version,
            "request_id": current_request_id(),
            "environment": settings.environment,
            "artifact_storage": "s3",
            "artifact_cache_root": settings.artifact_cache_root,
        },
    )
    try:
        psycopg = _psycopg()
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO cdss_audit_events (case_id, event_type, payload) VALUES (%s, %s, %s)",
                    (case_id, event_type, psycopg.types.json.Jsonb(safe_payload)),
                )
        return True
    except Exception as exc:
        logger.warning("PostgreSQL audit write skipped: %s", exc)
        return False


def postgres_status() -> dict[str, Any]:
    try:
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM cdss_audit_events")
                audit_count = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM chat_conversations")
                conversation_count = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM chat_messages")
                message_count = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM users")
                user_count = cursor.fetchone()[0]
        return {
            "status": "ok",
            "audit_events": audit_count,
            "chat_conversations": conversation_count,
            "chat_messages": message_count,
            "users": user_count,
        }
    except Exception as exc:
        return {"status": "unavailable", "detail": str(exc)}


def read_audit_events(case_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, case_id, event_type, payload, created_at
                FROM cdss_audit_events
                WHERE case_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (case_id, max(1, min(limit, 200))),
            )
            return [
                {
                    "id": row[0],
                    "case_id": row[1],
                    "event_type": row[2],
                    "payload": row[3],
                    "created_at": row[4].isoformat(),
                }
                for row in cursor.fetchall()
            ]


def ensure_chat_conversation(conversation_id: str, case_id: str | None = None) -> None:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chat_conversations (conversation_id, case_id)
                VALUES (%s, %s)
                ON CONFLICT (conversation_id) DO UPDATE
                SET case_id = COALESCE(EXCLUDED.case_id, chat_conversations.case_id),
                    updated_at = NOW()
                """,
                (conversation_id, case_id),
            )


def append_chat_message(message: dict[str, Any]) -> None:
    psycopg = _psycopg()
    ensure_chat_conversation(message["conversation_id"])
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chat_messages (message_id, conversation_id, role, content, metadata, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (message_id) DO NOTHING
                """,
                (
                    message["message_id"],
                    message["conversation_id"],
                    message["role"],
                    message["content"],
                    psycopg.types.json.Jsonb(message.get("metadata", {})),
                    message["created_at"],
                ),
            )


def upsert_patient_draft(draft: dict[str, Any]) -> None:
    psycopg = _psycopg()
    patient = draft["patient"]
    case_id = patient.get("patient_identity", {}).get("case_id", draft["conversation_id"])
    ensure_chat_conversation(draft["conversation_id"], case_id)
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO chat_patient_drafts (conversation_id, case_id, patient, source, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (conversation_id) DO UPDATE
                SET case_id = EXCLUDED.case_id,
                    patient = EXCLUDED.patient,
                    source = EXCLUDED.source,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    draft["conversation_id"],
                    case_id,
                    psycopg.types.json.Jsonb(patient),
                    draft.get("source", "chat"),
                    draft["updated_at"],
                ),
            )


def read_chat_messages(conversation_id: str) -> list[dict[str, Any]]:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT message_id, conversation_id, role, content, metadata, created_at
                FROM chat_messages
                WHERE conversation_id = %s
                ORDER BY created_at ASC
                """,
                (conversation_id,),
            )
            return [
                {
                    "message_id": row[0],
                    "conversation_id": row[1],
                    "role": row[2],
                    "content": row[3],
                    "metadata": row[4],
                    "created_at": row[5],
                }
                for row in cursor.fetchall()
            ]


def read_patient_draft(conversation_id: str) -> dict[str, Any] | None:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT conversation_id, patient, updated_at, source
                FROM chat_patient_drafts
                WHERE conversation_id = %s
                """,
                (conversation_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return {
                "conversation_id": row[0],
                "patient": row[1],
                "updated_at": row[2],
                "source": row[3],
            }


# Constraint Rules Management (Pipeline-Generated)


def _log_constraint_rule_history(cursor, constraint_id: str, status_from: str | None, status_to: str, changed_by: str, reason: str | None = None):
    """Internal helper to log a status change for a constraint rule."""
    cursor.execute(
        """
        INSERT INTO constraint_rule_history (constraint_id, status_from, status_to, changed_by, reason)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (constraint_id, status_from, status_to, changed_by, reason),
    )


def read_approved_constraint_rules() -> list[dict[str, Any]]:
    """Read all approved constraint rules for use in constraint builder."""
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """ --noqa: S608
                SELECT id, constraint_id, version, target_drug_class, action,
                       reason, risk_names, severity_any, evidence_ref, 
                       clinical_sources, metadata
                FROM constraint_rules
                WHERE status = 'approved'
                ORDER BY target_drug_class, created_at DESC
                """
            )
            return [
                {
                    "id": row[0],
                    "constraint_id": row[1],
                    "version": row[2],
                    "target_drug_class": row[3],
                    "action": row[4],
                    "reason": row[5],
                    "risk_names": list(row[6]) if row[6] else [],
                    "severity_any": list(row[7]) if row[7] else [],
                    "evidence_ref": row[8],
                    "clinical_sources": row[9] or [],
                    "metadata": row[10] or {},
                }
                for row in cursor.fetchall()
            ]


def read_constraint_rules_by_status(status: str, limit: int = 100) -> list[dict[str, Any]]:
    """Read constraint rules filtered by status."""
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """ --noqa: S608
                SELECT id, constraint_id, version, target_drug_class, action,
                       reason, risk_names, severity_any, evidence_ref, clinical_sources, status,
                       source, approved_by, approved_at, retired_by, retired_at, created_at,
                       updated_at, metadata
                FROM constraint_rules
                WHERE status = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (status, limit),
            )
            return [
                {
                    "id": row[0],
                    "constraint_id": row[1],
                    "version": row[2],
                    "target_drug_class": row[3],
                    "action": row[4],
                    "reason": row[5],
                    "risk_names": list(row[6]) if row[6] else [],
                    "severity_any": list(row[7]) if row[7] else [],
                    "evidence_ref": row[8],
                    "clinical_sources": row[9] or [],
                    "status": row[10],
                    "source": row[11],
                    "approved_by": row[12],
                    "approved_at": row[13].isoformat() if row[13] else None,
                    "retired_by": row[14],
                    "retired_at": row[15].isoformat() if row[15] else None,
                    "created_at": row[16].isoformat(),
                    "updated_at": row[17].isoformat(),
                    "metadata": row[18] or {},
                }
                for row in cursor.fetchall()
            ]


def _constraint_list_filters(
    *,
    status: str | None,
    target_drug_class: str | None,
    action: str | None,
    q: str | None,
    safety_tier: str | None = None,
    needs_condition: bool | None = None,
) -> tuple[list[str], list[Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    if status:
        conditions.append("status = %s")
        params.append(status)
    if target_drug_class:
        conditions.append("target_drug_class ILIKE %s")
        params.append(f"%{_escape_like(target_drug_class)}%")
    if action:
        conditions.append("action ILIKE %s")
        params.append(f"%{_escape_like(action)}%")
    if q:
        conditions.append("constraint_id ILIKE %s")
        params.append(f"%{_escape_like(q)}%")
    if safety_tier:
        conditions.append("metadata->>'safety_tier' = %s")
        params.append(safety_tier)
    if needs_condition is True:
        conditions.append("(metadata->>'needs_condition') = 'true'")
    elif needs_condition is False:
        conditions.append("(metadata->>'needs_condition') IS DISTINCT FROM 'true'")
    return conditions, params


def read_constraint_rules_filtered(
    *,
    status: str | None = None,
    target_drug_class: str | None = None,
    action: str | None = None,
    q: str | None = None,
    safety_tier: str | None = None,
    needs_condition: bool | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    conditions, params = _constraint_list_filters(
        status=status,
        target_drug_class=target_drug_class,
        action=action,
        q=q,
        safety_tier=safety_tier,
        needs_condition=needs_condition,
    )
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f""" --noqa: S608
                SELECT id, constraint_id, version, target_drug_class, action,
                       reason, risk_names, severity_any, evidence_ref, clinical_sources, status,
                       source, approved_by, approved_at, retired_by, retired_at, created_at,
                       updated_at, metadata
                FROM constraint_rules
                {where}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                tuple(params),
            )
            return [
                {
                    "id": row[0],
                    "constraint_id": row[1],
                    "version": row[2],
                    "target_drug_class": row[3],
                    "action": row[4],
                    "reason": row[5],
                    "risk_names": list(row[6]) if row[6] else [],
                    "severity_any": list(row[7]) if row[7] else [],
                    "evidence_ref": row[8],
                    "clinical_sources": row[9] or [],
                    "status": row[10],
                    "source": row[11],
                    "approved_by": row[12],
                    "approved_at": row[13].isoformat() if row[13] else None,
                    "retired_by": row[14],
                    "retired_at": row[15].isoformat() if row[15] else None,
                    "created_at": row[16].isoformat(),
                    "updated_at": row[17].isoformat(),
                    "metadata": row[18] or {},
                }
                for row in cursor.fetchall()
            ]


def list_draft_constraint_rule_ids(
    *,
    rule_ids: list[int] | None = None,
    target_drug_class: str | None = None,
    action: str | None = None,
    q: str | None = None,
    limit: int = 100,
) -> list[int]:
    conditions = ["status = 'draft'"]
    params: list[Any] = []
    if rule_ids:
        conditions.append("id = ANY(%s)")
        params.append(rule_ids)
    if target_drug_class:
        conditions.append("target_drug_class ILIKE %s")
        params.append(f"%{_escape_like(target_drug_class)}%")
    if action:
        conditions.append("action ILIKE %s")
        params.append(f"%{_escape_like(action)}%")
    if q:
        conditions.append("constraint_id ILIKE %s")
        params.append(f"%{_escape_like(q)}%")
    params.append(limit)
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id FROM constraint_rules
                WHERE {' AND '.join(conditions)}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                tuple(params),
            )
            return [row[0] for row in cursor.fetchall()]


def get_constraint_rule_latest_by_status(constraint_id: str, status: str) -> dict[str, Any] | None:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM constraint_rules
                WHERE constraint_id = %s AND status = %s
                ORDER BY version DESC
                LIMIT 1
                """,
                (constraint_id, status),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return get_constraint_rule(row[0])


def read_all_constraint_rules(
    status: str | None = None, limit: int = 100, offset: int = 0
) -> list[dict[str, Any]]:
    """Read all constraint rules with pagination and optional status filter."""
    query = """
        SELECT id, constraint_id, version, target_drug_class, action,
               reason, risk_names, severity_any, evidence_ref, clinical_sources, status,
               source, approved_by, approved_at, retired_by, retired_at, created_at,
               updated_at, metadata
        FROM constraint_rules
    """
    params = []
    if status:
        query += " WHERE status = %s"
        params.append(status)
    
    query += " ORDER BY updated_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, tuple(params))
            return [
                {
                    "id": row[0],
                    "constraint_id": row[1],
                    "version": row[2],
                    "target_drug_class": row[3],
                    "action": row[4],
                    "reason": row[5],
                    "risk_names": list(row[6]) if row[6] else [],
                    "severity_any": list(row[7]) if row[7] else [],
                    "evidence_ref": row[8],
                    "clinical_sources": row[9] or [],
                    "status": row[10],
                    "source": row[11],
                    "approved_by": row[12],
                    "approved_at": row[13].isoformat() if row[13] else None,
                    "retired_by": row[14],
                    "retired_at": row[15].isoformat() if row[15] else None,
                    "created_at": row[16].isoformat(),
                    "updated_at": row[17].isoformat(),
                    "metadata": row[18] or {},
                }
                for row in cursor.fetchall()
            ]


def get_constraint_rule_counts(
    *,
    target_drug_class: str | None = None,
    action: str | None = None,
    q: str | None = None,
) -> dict[str, int]:
    """Get counts of constraint rules by status (ignores status tab filter)."""
    conditions, params = _constraint_list_filters(
        status=None,
        target_drug_class=target_drug_class,
        action=action,
        q=q,
    )
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT status, COUNT(*) FROM constraint_rules {where} GROUP BY status",
                tuple(params),
            )
            counts = {row[0]: row[1] for row in cursor.fetchall()}
            return {
                "draft": counts.get("draft", 0),
                "approved": counts.get("approved", 0),
                "retired": counts.get("retired", 0),
                "total": sum(counts.values()),
            }


def insert_constraint_rule(rule: dict[str, Any]) -> bool:
    """Insert or update a constraint rule from pipeline."""
    try:
        psycopg = _psycopg()
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO constraint_rules ( --noqa: S608
                        constraint_id, version, target_drug_class, action, reason,
                        risk_names, severity_any, evidence_ref, clinical_sources,
                        source, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (constraint_id, version) DO UPDATE -- noqa: S608
                    SET version = EXCLUDED.version,
                        target_drug_class = EXCLUDED.target_drug_class,
                        action = EXCLUDED.action,
                        reason = EXCLUDED.reason,
                        risk_names = EXCLUDED.risk_names,
                        severity_any = EXCLUDED.severity_any,
                        evidence_ref = EXCLUDED.evidence_ref,
                        clinical_sources = EXCLUDED.clinical_sources,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                    WHERE constraint_rules.status = 'draft'
                    RETURNING xmax
                    """,
                    (
                        rule.get("constraint_id"),
                        rule.get("version", 1),
                        rule.get("target_drug_class"),
                        rule.get("action"),
                        rule.get("reason"),
                        rule.get("risk_names", []),
                        rule.get("severity_any", []),
                        rule.get("evidence_ref"),
                        psycopg.types.json.Jsonb(rule.get("clinical_sources", [])),
                        rule.get("source", "pipeline_generated"),
                        psycopg.types.json.Jsonb(rule.get("metadata", {})),
                    ),
                )
                result = cursor.fetchone()
                # xmax = 0 for an insert, which means a new rule was created in 'draft' status.
                if result and result[0] == 0:
                    _log_constraint_rule_history(
                        cursor,
                        rule.get("constraint_id"),
                        status_from=None,
                        status_to='draft',
                        changed_by=rule.get("source", "pipeline_generated"),
                        reason="Rule created"
                    )
        return True
    except Exception as exc:
        logger.warning("Failed to insert constraint rule: %s", exc)
        return False


def approve_constraint_rule(rule_id: int, admin_user_id: str) -> bool:
    """Approve a draft constraint rule, and retire any other approved versions."""
    try:
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                # Step 1: Get the constraint_id of the rule being approved
                cursor.execute(
                    "SELECT constraint_id FROM constraint_rules WHERE id = %s AND status = 'draft'",
                    (rule_id,)
                )
                result = cursor.fetchone()
                if not result:
                    logger.warning(f"No draft rule found with id {rule_id} to approve.")
                    return False
                constraint_id = result[0]

                # Step 2: Retire all other currently approved versions of this rule
                cursor.execute(
                    """
                    UPDATE constraint_rules
                    SET status = 'retired',
                        retired_by = %s,
                        retired_at = NOW(),
                        updated_at = NOW()
                    WHERE constraint_id = %s AND status = 'approved' AND id != %s
                    RETURNING id
                    """,
                    (f"system_auto_retire_by_{admin_user_id}", constraint_id, rule_id)
                )
                for retired_row in cursor.fetchall():
                    _log_constraint_rule_history(cursor, constraint_id, 'approved', 'retired', f"system_auto_retire_by_{admin_user_id}", f"Auto-retired due to new version approval (rule_id: {rule_id})")

                # Step 3: Approve the new version
                cursor.execute(
                    """
                    UPDATE constraint_rules
                    SET status = 'approved',
                        approved_by = %s,
                        approved_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s AND status = 'draft'
                    """,
                    (admin_user_id, rule_id)
                )
                if cursor.rowcount == 0:
                    # This should not happen if step 1 succeeded, but as a safeguard
                    raise Exception(f"Approve failed for rule {rule_id} because it was not in draft state.")
                
                _log_constraint_rule_history(cursor, constraint_id, 'draft', 'approved', admin_user_id, "Rule approved")
        return True
    except Exception as exc:
        logger.warning("Failed to approve constraint rule transaction for rule_id %s: %s", rule_id, exc)
        return False


def retire_constraint_rule(rule_id: int, admin_user_id: str) -> bool:
    """Retire an approved constraint rule."""
    try:
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                # Get constraint_id for logging
                cursor.execute("SELECT constraint_id FROM constraint_rules WHERE id = %s", (rule_id,))
                res = cursor.fetchone()
                if not res: return False
                constraint_id = res[0]

                cursor.execute(
                    """
                    UPDATE constraint_rules
                    SET status = 'retired',
                        retired_by = %s,
                        retired_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s AND status = 'approved'
                    """,
                    (admin_user_id, rule_id),
                )
                if cursor.rowcount > 0:
                    _log_constraint_rule_history(cursor, constraint_id, 'approved', 'retired', admin_user_id, "Rule retired")
        return True
    except Exception as exc:
        logger.warning("Failed to retire constraint rule: %s", exc)
        return False


def unretire_constraint_rule(rule_id: int, admin_user_id: str) -> bool:
    """Un-retire a retired constraint rule, setting it back to approved."""
    try:
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                # Get constraint_id for logging
                cursor.execute("SELECT constraint_id FROM constraint_rules WHERE id = %s", (rule_id,))
                res = cursor.fetchone()
                if not res: return False
                constraint_id = res[0]

                cursor.execute(
                    """
                    UPDATE constraint_rules
                    SET status = 'approved',
                        approved_by = %s,
                        approved_at = NOW(),
                        retired_by = NULL,
                        retired_at = NULL,
                        updated_at = NOW()
                    WHERE id = %s AND status = 'retired'
                    """,
                    (admin_user_id, rule_id),
                )
                if cursor.rowcount > 0:
                    # Note: This doesn't check for other approved versions. The assumption is un-retire is a specific admin action.
                    _log_constraint_rule_history(cursor, constraint_id, 'retired', 'approved', admin_user_id, "Rule un-retired")
        return True
    except Exception as exc:
        logger.warning("Failed to un-retire constraint rule: %s", exc)
        return False


def read_constraint_rule_history(constraint_id: str) -> list[dict[str, Any]]:
    """Read the status change history for a specific constraint rule."""
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT history_id, constraint_id, status_from, status_to,
                       changed_by, changed_at, reason
                FROM constraint_rule_history
                WHERE constraint_id = %s
                ORDER BY changed_at DESC
                """,
                (constraint_id,),
            )
            return [
                {
                    "history_id": row[0],
                    "constraint_id": row[1],
                    "status_from": row[2],
                    "status_to": row[3],
                    "changed_by": row[4],
                    "changed_at": row[5].isoformat(),
                    "reason": row[6],
                }
                for row in cursor.fetchall()
            ]


def get_latest_constraint_rule_version(constraint_id: str) -> dict[str, Any] | None:
    """Get the latest version of a specific constraint rule by its constraint_id."""
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, constraint_id, version, status, metadata
                FROM constraint_rules
                WHERE constraint_id = %s
                ORDER BY version DESC
                LIMIT 1
                """,
                (constraint_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "constraint_id": row[1],
                "version": row[2],
                "status": row[3],
                "metadata": row[4] or {},
            }


def rule_with_constraint_id_exists(constraint_id: str) -> bool:
    """Check if any version of a rule with the given constraint_id exists."""
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM constraint_rules WHERE constraint_id = %s LIMIT 1",
                (constraint_id,)
            )
            return cursor.fetchone() is not None


def get_constraint_rule_versions(constraint_id: str) -> list[dict[str, Any]]:
    """Get all versions of a specific constraint rule."""
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """ --noqa: S608
                SELECT id, constraint_id, version, status, created_at, updated_at
                FROM constraint_rules
                WHERE constraint_id = %s
                ORDER BY version DESC
                """,
                (constraint_id,),
            )
            return [dict(zip(["id", "constraint_id", "version", "status", "created_at", "updated_at"], row)) for row in cursor.fetchall()]


def get_constraint_rule(rule_id: int) -> dict[str, Any] | None:
    """Get a specific constraint rule."""
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """ --noqa: S608
                SELECT id, constraint_id, version, target_drug_class, action,
                       reason, risk_names, severity_any, evidence_ref, clinical_sources,
                       status, source, approved_by, approved_at, retired_by, retired_at,
                       created_at, updated_at, metadata
                FROM constraint_rules
                WHERE id = %s
                """,
                (rule_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return {
                "id": row[0],
                "constraint_id": row[1],
                "version": row[2],
                "target_drug_class": row[3],
                "action": row[4],
                "reason": row[5],
                "risk_names": list(row[6]) if row[6] else [],
                "severity_any": list(row[7]) if row[7] else [],
                "evidence_ref": row[8],
                "clinical_sources": row[9] or [],
                "status": row[10],
                "source": row[11],
                "approved_by": row[12],
                "approved_at": row[13].isoformat() if row[13] else None,
                "retired_by": row[14],
                "retired_at": row[15].isoformat() if row[15] else None,
                "created_at": row[16].isoformat(),
                "updated_at": row[17].isoformat(),
                "metadata": row[18] or {},
            }


def _log_dose_rule_history(
    cursor,
    dose_rule_id: str,
    status_from: str | None,
    status_to: str,
    changed_by: str,
    reason: str | None = None,
) -> None:
    cursor.execute(
        """
        INSERT INTO dose_rule_history (dose_rule_id, status_from, status_to, changed_by, reason)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (dose_rule_id, status_from, status_to, changed_by, reason),
    )


def read_approved_dose_rules() -> list[dict[str, Any]]:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, dose_rule_id, version, drug_keys, drug_class, calculation_type,
                       rule_body, evidence_ref, clinical_sources, metadata, status
                FROM dose_rules
                WHERE status = 'approved'
                ORDER BY drug_class, created_at DESC
                """
            )
            return [
                {
                    "id": row[0],
                    "dose_rule_id": row[1],
                    "version": row[2],
                    "drug_keys": list(row[3]) if row[3] else [],
                    "drug_class": row[4],
                    "calculation_type": row[5],
                    "rule_body": row[6] or {},
                    "evidence_ref": row[7],
                    "clinical_sources": row[8] or [],
                    "metadata": row[9] or {},
                    "status": row[10],
                }
                for row in cursor.fetchall()
            ]


def read_dose_rules_by_status(status: str, limit: int = 100) -> list[dict[str, Any]]:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, dose_rule_id, version, drug_keys, drug_class, calculation_type,
                       rule_body, evidence_ref, clinical_sources, status, source,
                       approved_by, approved_at, retired_by, retired_at, created_at,
                       updated_at, metadata, safety_tier
                FROM dose_rules
                WHERE status = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (status, limit),
            )
            return [
                {
                    "id": row[0],
                    "dose_rule_id": row[1],
                    "version": row[2],
                    "drug_keys": list(row[3]) if row[3] else [],
                    "drug_class": row[4],
                    "calculation_type": row[5],
                    "rule_body": row[6] or {},
                    "evidence_ref": row[7],
                    "clinical_sources": row[8] or [],
                    "status": row[9],
                    "source": row[10],
                    "approved_by": row[11],
                    "approved_at": row[12].isoformat() if row[12] else None,
                    "retired_by": row[13],
                    "retired_at": row[14].isoformat() if row[14] else None,
                    "created_at": row[15].isoformat(),
                    "updated_at": row[16].isoformat(),
                    "metadata": row[17] or {},
                    "safety_tier": row[18],
                }
                for row in cursor.fetchall()
            ]


def insert_dose_rule(rule: dict[str, Any]) -> bool:
    try:
        psycopg = _psycopg()
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO dose_rules (
                        dose_rule_id, version, drug_keys, drug_class, calculation_type,
                        rule_body, evidence_ref, clinical_sources, source, safety_tier, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (dose_rule_id, version) DO UPDATE
                    SET drug_keys = EXCLUDED.drug_keys,
                        drug_class = EXCLUDED.drug_class,
                        calculation_type = EXCLUDED.calculation_type,
                        rule_body = EXCLUDED.rule_body,
                        evidence_ref = EXCLUDED.evidence_ref,
                        clinical_sources = EXCLUDED.clinical_sources,
                        safety_tier = EXCLUDED.safety_tier,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                    WHERE dose_rules.status = 'draft'
                    RETURNING xmax
                    """,
                    (
                        rule.get("dose_rule_id"),
                        rule.get("version", 1),
                        rule.get("drug_keys", []),
                        rule.get("drug_class"),
                        rule.get("calculation_type"),
                        psycopg.types.json.Jsonb(rule.get("rule_body") or {}),
                        rule.get("evidence_ref"),
                        psycopg.types.json.Jsonb(rule.get("clinical_sources") or []),
                        rule.get("source", "pipeline_generated"),
                        rule.get("safety_tier"),
                        psycopg.types.json.Jsonb(rule.get("metadata") or {}),
                    ),
                )
                result = cursor.fetchone()
                if result and result[0] == 0:
                    _log_dose_rule_history(
                        cursor,
                        rule.get("dose_rule_id"),
                        status_from=None,
                        status_to="draft",
                        changed_by=rule.get("source", "pipeline_generated"),
                        reason="Dose rule created",
                    )
        return True
    except Exception as exc:
        logger.warning("Failed to insert dose rule: %s", exc)
        return False


def approve_dose_rule(rule_id: int, admin_user_id: str) -> bool:
    try:
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT dose_rule_id FROM dose_rules WHERE id = %s AND status = 'draft'",
                    (rule_id,),
                )
                result = cursor.fetchone()
                if not result:
                    return False
                dose_rule_id = result[0]

                cursor.execute(
                    """
                    UPDATE dose_rules
                    SET status = 'retired', retired_by = %s, retired_at = NOW(), updated_at = NOW()
                    WHERE dose_rule_id = %s AND status = 'approved' AND id != %s
                    RETURNING id
                    """,
                    (f"system_auto_retire_by_{admin_user_id}", dose_rule_id, rule_id),
                )
                for retired_row in cursor.fetchall():
                    _log_dose_rule_history(
                        cursor,
                        dose_rule_id,
                        "approved",
                        "retired",
                        f"system_auto_retire_by_{admin_user_id}",
                        f"Auto-retired due to new version approval (rule_id: {rule_id})",
                    )

                cursor.execute(
                    """
                    UPDATE dose_rules
                    SET status = 'approved', approved_by = %s, approved_at = NOW(), updated_at = NOW()
                    WHERE id = %s AND status = 'draft'
                    """,
                    (admin_user_id, rule_id),
                )
                if cursor.rowcount == 0:
                    return False
                _log_dose_rule_history(cursor, dose_rule_id, "draft", "approved", admin_user_id, "Dose rule approved")
        return True
    except Exception as exc:
        logger.warning("Failed to approve dose rule %s: %s", rule_id, exc)
        return False


def retire_dose_rule(rule_id: int, admin_user_id: str) -> bool:
    try:
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT dose_rule_id FROM dose_rules WHERE id = %s", (rule_id,))
                row = cursor.fetchone()
                if not row:
                    return False
                dose_rule_id = row[0]
                cursor.execute(
                    """
                    UPDATE dose_rules
                    SET status = 'retired', retired_by = %s, retired_at = NOW(), updated_at = NOW()
                    WHERE id = %s AND status = 'approved'
                    """,
                    (admin_user_id, rule_id),
                )
                if cursor.rowcount > 0:
                    _log_dose_rule_history(cursor, dose_rule_id, "approved", "retired", admin_user_id, "Dose rule retired")
        return True
    except Exception as exc:
        logger.warning("Failed to retire dose rule: %s", exc)
        return False


def unretire_dose_rule(rule_id: int, admin_user_id: str) -> bool:
    try:
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT dose_rule_id FROM dose_rules WHERE id = %s", (rule_id,))
                row = cursor.fetchone()
                if not row:
                    return False
                dose_rule_id = row[0]
                cursor.execute(
                    """
                    UPDATE dose_rules
                    SET status = 'approved', approved_by = %s, approved_at = NOW(),
                        retired_by = NULL, retired_at = NULL, updated_at = NOW()
                    WHERE id = %s AND status = 'retired'
                    """,
                    (admin_user_id, rule_id),
                )
                if cursor.rowcount > 0:
                    _log_dose_rule_history(cursor, dose_rule_id, "retired", "approved", admin_user_id, "Dose rule un-retired")
        return True
    except Exception as exc:
        logger.warning("Failed to un-retire dose rule: %s", exc)
        return False


def get_latest_dose_rule_version(dose_rule_id: str) -> dict[str, Any] | None:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, dose_rule_id, version, status, metadata
                FROM dose_rules
                WHERE dose_rule_id = %s
                ORDER BY version DESC
                LIMIT 1
                """,
                (dose_rule_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "dose_rule_id": row[1],
                "version": row[2],
                "status": row[3],
                "metadata": row[4] or {},
            }


def dose_rule_with_id_exists(dose_rule_id: str) -> bool:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM dose_rules WHERE dose_rule_id = %s LIMIT 1", (dose_rule_id,))
            return cursor.fetchone() is not None


def get_dose_rule(rule_id: int) -> dict[str, Any] | None:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, dose_rule_id, version, drug_keys, drug_class, calculation_type,
                       rule_body, evidence_ref, clinical_sources, status, source,
                       approved_by, approved_at, retired_by, retired_at, created_at,
                       updated_at, metadata, safety_tier
                FROM dose_rules
                WHERE id = %s
                """,
                (rule_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return {
                "id": row[0],
                "dose_rule_id": row[1],
                "version": row[2],
                "drug_keys": list(row[3]) if row[3] else [],
                "drug_class": row[4],
                "calculation_type": row[5],
                "rule_body": row[6] or {},
                "evidence_ref": row[7],
                "clinical_sources": row[8] or [],
                "status": row[9],
                "source": row[10],
                "approved_by": row[11],
                "approved_at": row[12].isoformat() if row[12] else None,
                "retired_by": row[13],
                "retired_at": row[14].isoformat() if row[14] else None,
                "created_at": row[15].isoformat(),
                "updated_at": row[16].isoformat(),
                "metadata": row[17] or {},
                "safety_tier": row[18],
            }


def get_dose_rule_versions(dose_rule_id: str) -> list[dict[str, Any]]:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, dose_rule_id, version, status, created_at, updated_at
                FROM dose_rules
                WHERE dose_rule_id = %s
                ORDER BY version DESC
                """,
                (dose_rule_id,),
            )
            return [
                {
                    "id": row[0],
                    "dose_rule_id": row[1],
                    "version": row[2],
                    "status": row[3],
                    "created_at": row[4].isoformat(),
                    "updated_at": row[5].isoformat(),
                }
                for row in cursor.fetchall()
            ]


def read_dose_rule_history(dose_rule_id: str) -> list[dict[str, Any]]:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT history_id, dose_rule_id, status_from, status_to, changed_by, changed_at, reason
                FROM dose_rule_history
                WHERE dose_rule_id = %s
                ORDER BY changed_at DESC
                """,
                (dose_rule_id,),
            )
            return [
                {
                    "history_id": row[0],
                    "dose_rule_id": row[1],
                    "status_from": row[2],
                    "status_to": row[3],
                    "changed_by": row[4],
                    "changed_at": row[5].isoformat(),
                    "reason": row[6],
                }
                for row in cursor.fetchall()
            ]


def read_dose_rules_filtered(
    *,
    status: str | None = None,
    drug_class: str | None = None,
    calculation_type: str | None = None,
    safety_tier: str | None = None,
    q: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    if status:
        conditions.append("status = %s")
        params.append(status)
    if drug_class:
        conditions.append("drug_class ILIKE %s")
        params.append(f"%{_escape_like(drug_class)}%")
    if calculation_type:
        conditions.append("calculation_type ILIKE %s")
        params.append(f"%{_escape_like(calculation_type)}%")
    if safety_tier:
        conditions.append("safety_tier = %s")
        params.append(safety_tier)
    if q:
        conditions.append("dose_rule_id ILIKE %s")
        params.append(f"%{_escape_like(q)}%")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, dose_rule_id, version, drug_keys, drug_class, calculation_type,
                       rule_body, evidence_ref, clinical_sources, status, source,
                       approved_by, approved_at, retired_by, retired_at, created_at,
                       updated_at, metadata, safety_tier
                FROM dose_rules
                {where}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                tuple(params),
            )
            return [
                {
                    "id": row[0],
                    "dose_rule_id": row[1],
                    "version": row[2],
                    "drug_keys": list(row[3]) if row[3] else [],
                    "drug_class": row[4],
                    "calculation_type": row[5],
                    "rule_body": row[6] or {},
                    "evidence_ref": row[7],
                    "clinical_sources": row[8] or [],
                    "status": row[9],
                    "source": row[10],
                    "approved_by": row[11],
                    "approved_at": row[12].isoformat() if row[12] else None,
                    "retired_by": row[13],
                    "retired_at": row[14].isoformat() if row[14] else None,
                    "created_at": row[15].isoformat(),
                    "updated_at": row[16].isoformat(),
                    "metadata": row[17] or {},
                    "safety_tier": row[18],
                }
                for row in cursor.fetchall()
            ]


def count_dose_rules_by_status(
    *,
    drug_class: str | None = None,
    calculation_type: str | None = None,
    safety_tier: str | None = None,
    q: str | None = None,
) -> dict[str, int]:
    """Status badge counts independent of the selected status tab."""
    conditions: list[str] = []
    params: list[Any] = []
    if drug_class:
        conditions.append("drug_class ILIKE %s")
        params.append(f"%{_escape_like(drug_class)}%")
    if calculation_type:
        conditions.append("calculation_type ILIKE %s")
        params.append(f"%{_escape_like(calculation_type)}%")
    if safety_tier:
        conditions.append("safety_tier = %s")
        params.append(safety_tier)
    if q:
        conditions.append("dose_rule_id ILIKE %s")
        params.append(f"%{_escape_like(q)}%")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT status, COUNT(*) FROM dose_rules {where} GROUP BY status",
                tuple(params),
            )
            counts = {row[0]: row[1] for row in cursor.fetchall()}
            return {
                "draft": counts.get("draft", 0),
                "approved": counts.get("approved", 0),
                "retired": counts.get("retired", 0),
                "total": sum(counts.values()),
            }


def list_draft_dose_rule_ids(
    *,
    rule_ids: list[int] | None = None,
    drug_class: str | None = None,
    calculation_type: str | None = None,
    safety_tier: str | None = None,
    q: str | None = None,
    limit: int = 100,
) -> list[int]:
    conditions = ["status = 'draft'"]
    params: list[Any] = []
    if rule_ids:
        conditions.append("id = ANY(%s)")
        params.append(rule_ids)
    if drug_class:
        conditions.append("drug_class ILIKE %s")
        params.append(f"%{_escape_like(drug_class)}%")
    if calculation_type:
        conditions.append("calculation_type ILIKE %s")
        params.append(f"%{_escape_like(calculation_type)}%")
    if safety_tier:
        conditions.append("safety_tier = %s")
        params.append(safety_tier)
    if q:
        conditions.append("dose_rule_id ILIKE %s")
        params.append(f"%{_escape_like(q)}%")
    params.append(limit)
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id FROM dose_rules
                WHERE {' AND '.join(conditions)}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                tuple(params),
            )
            return [row[0] for row in cursor.fetchall()]


def get_dose_rule_latest_by_status(dose_rule_id: str, status: str) -> dict[str, Any] | None:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM dose_rules
                WHERE dose_rule_id = %s AND status = %s
                ORDER BY version DESC
                LIMIT 1
                """,
                (dose_rule_id, status),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return get_dose_rule(row[0])
