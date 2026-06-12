import logging
from functools import lru_cache
from typing import Any

from app.core.config import settings
from app.core.request_context import current_request_id


logger = logging.getLogger(__name__)


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
    return {"status": "ok", "tables": ["cdss_audit_events", "chat_conversations", "chat_messages", "chat_patient_drafts"]}


def write_audit_event(case_id: str, event_type: str, payload: dict[str, Any]) -> bool:
    if not settings.postgres_audit_enabled:
        return False
    payload.setdefault(
        "audit_metadata",
        {
            "schema_version": settings.audit_schema_version,
            "request_id": current_request_id(),
            "environment": settings.environment,
            "artifact_storage": settings.artifact_storage,
            "artifact_cache_root": settings.artifact_cache_root,
        },
    )
    try:
        psycopg = _psycopg()
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO cdss_audit_events (case_id, event_type, payload) VALUES (%s, %s, %s)",
                    (case_id, event_type, psycopg.types.json.Jsonb(payload)),
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
        return {
            "status": "ok",
            "audit_events": audit_count,
            "chat_conversations": conversation_count,
            "chat_messages": message_count,
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
