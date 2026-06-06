import logging
from functools import lru_cache
from typing import Any

from app.core.config import settings


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
    return {"status": "ok", "table": "cdss_audit_events"}


def write_audit_event(case_id: str, event_type: str, payload: dict[str, Any]) -> bool:
    if not settings.postgres_audit_enabled:
        return False
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
                count = cursor.fetchone()[0]
        return {"status": "ok", "audit_events": count}
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
