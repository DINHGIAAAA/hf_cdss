"""Postgres helpers for dose_safety_warnings governance catalog."""

from __future__ import annotations

import logging
from typing import Any

from app.modules.datastores.postgres import _psycopg, postgres_pool


logger = logging.getLogger(__name__)


def _log_dose_safety_warning_history(
    cursor,
    dose_safety_warning_id: str,
    status_from: str | None,
    status_to: str,
    changed_by: str,
    reason: str | None = None,
) -> None:
    cursor.execute(
        """
        INSERT INTO dose_safety_warning_history (
            dose_safety_warning_id, status_from, status_to, changed_by, reason
        ) VALUES (%s, %s, %s, %s, %s)
        """,
        (dose_safety_warning_id, status_from, status_to, changed_by, reason),
    )


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "dose_safety_warning_id": row[1],
        "version": row[2],
        "drug_keys": list(row[3]) if row[3] else [],
        "target": row[4],
        "default_severity": row[5],
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


_SELECT_COLUMNS = """
    id, dose_safety_warning_id, version, drug_keys, target, default_severity,
    rule_body, evidence_ref, clinical_sources, status, source,
    approved_by, approved_at, retired_by, retired_at, created_at,
    updated_at, metadata, safety_tier
"""


def read_approved_dose_safety_warnings() -> list[dict[str, Any]]:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM dose_safety_warnings
                WHERE status = 'approved'
                ORDER BY created_at DESC
                """
            )
            return [_row_to_dict(row) for row in cursor.fetchall()]


def read_dose_safety_warnings_by_status(status: str, limit: int = 100) -> list[dict[str, Any]]:
    return read_dose_safety_warnings_filtered(status=status, limit=limit)


def read_dose_safety_warnings_filtered(
    *,
    status: str | None = None,
    target: str | None = None,
    default_severity: str | None = None,
    safety_tier: str | None = None,
    q: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    if status:
        conditions.append("status = %s")
        params.append(status)
    if target:
        conditions.append("target ILIKE %s")
        params.append(f"%{target}%")
    if default_severity:
        conditions.append("default_severity = %s")
        params.append(default_severity)
    if safety_tier:
        conditions.append("safety_tier = %s")
        params.append(safety_tier)
    if q:
        conditions.append("(dose_safety_warning_id ILIKE %s OR target ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM dose_safety_warnings
                {where}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                tuple(params),
            )
            return [_row_to_dict(row) for row in cursor.fetchall()]


def count_dose_safety_warnings_by_status(
    *,
    target: str | None = None,
    default_severity: str | None = None,
    safety_tier: str | None = None,
    q: str | None = None,
) -> dict[str, int]:
    """Status badge counts independent of the selected status tab."""
    conditions: list[str] = []
    params: list[Any] = []
    if target:
        conditions.append("target ILIKE %s")
        params.append(f"%{target}%")
    if default_severity:
        conditions.append("default_severity = %s")
        params.append(default_severity)
    if safety_tier:
        conditions.append("safety_tier = %s")
        params.append(safety_tier)
    if q:
        conditions.append("(dose_safety_warning_id ILIKE %s OR target ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT status, COUNT(*) FROM dose_safety_warnings {where} GROUP BY status",
                tuple(params),
            )
            counts = {row[0]: row[1] for row in cursor.fetchall()}
            return {
                "draft": counts.get("draft", 0),
                "approved": counts.get("approved", 0),
                "retired": counts.get("retired", 0),
                "total": sum(counts.values()),
            }


def get_dose_safety_warning(rule_id: int) -> dict[str, Any] | None:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_SELECT_COLUMNS} FROM dose_safety_warnings WHERE id = %s",
                (rule_id,),
            )
            row = cursor.fetchone()
            return _row_to_dict(row) if row else None


def get_latest_dose_safety_warning_version(dose_safety_warning_id: str) -> dict[str, Any] | None:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM dose_safety_warnings
                WHERE dose_safety_warning_id = %s
                ORDER BY version DESC LIMIT 1
                """,
                (dose_safety_warning_id,),
            )
            row = cursor.fetchone()
            return get_dose_safety_warning(row[0]) if row else None


def insert_dose_safety_warning(warning: dict[str, Any]) -> bool:
    try:
        psycopg = _psycopg()
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO dose_safety_warnings (
                        dose_safety_warning_id, version, drug_keys, target, default_severity,
                        rule_body, evidence_ref, clinical_sources, source, safety_tier, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (dose_safety_warning_id, version) DO UPDATE
                    SET drug_keys = EXCLUDED.drug_keys,
                        target = EXCLUDED.target,
                        default_severity = EXCLUDED.default_severity,
                        rule_body = EXCLUDED.rule_body,
                        evidence_ref = EXCLUDED.evidence_ref,
                        clinical_sources = EXCLUDED.clinical_sources,
                        safety_tier = EXCLUDED.safety_tier,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                    WHERE dose_safety_warnings.status = 'draft'
                    RETURNING xmax
                    """,
                    (
                        warning.get("dose_safety_warning_id"),
                        warning.get("version", 1),
                        warning.get("drug_keys", []),
                        warning.get("target"),
                        warning.get("default_severity", "moderate"),
                        psycopg.types.json.Jsonb(warning.get("rule_body") or {}),
                        warning.get("evidence_ref"),
                        psycopg.types.json.Jsonb(warning.get("clinical_sources") or []),
                        warning.get("source", "pipeline_generated"),
                        warning.get("safety_tier"),
                        psycopg.types.json.Jsonb(warning.get("metadata") or {}),
                    ),
                )
                result = cursor.fetchone()
                if result and result[0] == 0:
                    _log_dose_safety_warning_history(
                        cursor,
                        warning.get("dose_safety_warning_id"),
                        None,
                        "draft",
                        warning.get("source", "pipeline_generated"),
                        "Dose safety warning created",
                    )
        return True
    except Exception as exc:
        logger.warning("Failed to insert dose safety warning: %s", exc)
        return False


def approve_dose_safety_warning(rule_id: int, admin_user_id: str) -> bool:
    try:
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT dose_safety_warning_id FROM dose_safety_warnings
                    WHERE id = %s AND status = 'draft'
                    """,
                    (rule_id,),
                )
                result = cursor.fetchone()
                if not result:
                    return False
                warning_id = result[0]
                cursor.execute(
                    """
                    UPDATE dose_safety_warnings
                    SET status = 'retired', retired_by = %s, retired_at = NOW(), updated_at = NOW()
                    WHERE dose_safety_warning_id = %s AND status = 'approved' AND id != %s
                    RETURNING id
                    """,
                    (f"system_auto_retire_by_{admin_user_id}", warning_id, rule_id),
                )
                for _ in cursor.fetchall():
                    _log_dose_safety_warning_history(
                        cursor,
                        warning_id,
                        "approved",
                        "retired",
                        f"system_auto_retire_by_{admin_user_id}",
                        f"Auto-retired due to new version approval (rule_id: {rule_id})",
                    )
                cursor.execute(
                    """
                    UPDATE dose_safety_warnings
                    SET status = 'approved', approved_by = %s, approved_at = NOW(), updated_at = NOW()
                    WHERE id = %s AND status = 'draft'
                    """,
                    (admin_user_id, rule_id),
                )
                if cursor.rowcount == 0:
                    return False
                _log_dose_safety_warning_history(
                    cursor, warning_id, "draft", "approved", admin_user_id, "Dose safety warning approved"
                )
        return True
    except Exception as exc:
        logger.warning("Failed to approve dose safety warning %s: %s", rule_id, exc)
        return False


def retire_dose_safety_warning(rule_id: int, admin_user_id: str) -> bool:
    try:
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT dose_safety_warning_id FROM dose_safety_warnings WHERE id = %s", (rule_id,))
                row = cursor.fetchone()
                if not row:
                    return False
                warning_id = row[0]
                cursor.execute(
                    """
                    UPDATE dose_safety_warnings
                    SET status = 'retired', retired_by = %s, retired_at = NOW(), updated_at = NOW()
                    WHERE id = %s AND status = 'approved'
                    """,
                    (admin_user_id, rule_id),
                )
                if cursor.rowcount > 0:
                    _log_dose_safety_warning_history(
                        cursor, warning_id, "approved", "retired", admin_user_id, "Dose safety warning retired"
                    )
        return True
    except Exception as exc:
        logger.warning("Failed to retire dose safety warning %s: %s", rule_id, exc)
        return False


def unretire_dose_safety_warning(rule_id: int, admin_user_id: str) -> bool:
    try:
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT dose_safety_warning_id FROM dose_safety_warnings WHERE id = %s AND status = 'retired'",
                    (rule_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return False
                warning_id = row[0]
                cursor.execute(
                    """
                    UPDATE dose_safety_warnings
                    SET status = 'retired', retired_by = %s, retired_at = NOW(), updated_at = NOW()
                    WHERE dose_safety_warning_id = %s AND status = 'approved' AND id != %s
                    """,
                    (f"system_auto_retire_by_{admin_user_id}", warning_id, rule_id),
                )
                cursor.execute(
                    """
                    UPDATE dose_safety_warnings
                    SET status = 'approved', approved_by = %s, approved_at = NOW(),
                        retired_by = NULL, retired_at = NULL, updated_at = NOW()
                    WHERE id = %s AND status = 'retired'
                    """,
                    (admin_user_id, rule_id),
                )
                if cursor.rowcount > 0:
                    _log_dose_safety_warning_history(
                        cursor, warning_id, "retired", "approved", admin_user_id, "Dose safety warning restored"
                    )
        return True
    except Exception as exc:
        logger.warning("Failed to un-retire dose safety warning %s: %s", rule_id, exc)
        return False


def dose_safety_warning_with_id_exists(dose_safety_warning_id: str) -> bool:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM dose_safety_warnings WHERE dose_safety_warning_id = %s LIMIT 1",
                (dose_safety_warning_id,),
            )
            return cursor.fetchone() is not None


def get_dose_safety_warning_versions(dose_safety_warning_id: str) -> list[dict[str, Any]]:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, dose_safety_warning_id, version, status, created_at, updated_at
                FROM dose_safety_warnings
                WHERE dose_safety_warning_id = %s
                ORDER BY version DESC
                """,
                (dose_safety_warning_id,),
            )
            return [
                {
                    "id": row[0],
                    "dose_safety_warning_id": row[1],
                    "version": row[2],
                    "status": row[3],
                    "created_at": row[4].isoformat(),
                    "updated_at": row[5].isoformat(),
                }
                for row in cursor.fetchall()
            ]


def read_dose_safety_warning_history(dose_safety_warning_id: str) -> list[dict[str, Any]]:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT history_id, dose_safety_warning_id, status_from, status_to,
                       changed_by, changed_at, reason
                FROM dose_safety_warning_history
                WHERE dose_safety_warning_id = %s
                ORDER BY changed_at DESC
                """,
                (dose_safety_warning_id,),
            )
            return [
                {
                    "history_id": row[0],
                    "dose_safety_warning_id": row[1],
                    "status_from": row[2],
                    "status_to": row[3],
                    "changed_by": row[4],
                    "changed_at": row[5].isoformat(),
                    "reason": row[6],
                }
                for row in cursor.fetchall()
            ]


def list_draft_dose_safety_warning_ids(
    *,
    rule_ids: list[int] | None = None,
    target: str | None = None,
    default_severity: str | None = None,
    safety_tier: str | None = None,
    q: str | None = None,
    limit: int = 100,
) -> list[int]:
    conditions = ["status = 'draft'"]
    params: list[Any] = []
    if rule_ids:
        conditions.append("id = ANY(%s)")
        params.append(rule_ids)
    if target:
        conditions.append("target ILIKE %s")
        params.append(f"%{target}%")
    if default_severity:
        conditions.append("default_severity = %s")
        params.append(default_severity)
    if safety_tier:
        conditions.append("safety_tier = %s")
        params.append(safety_tier)
    if q:
        conditions.append("(dose_safety_warning_id ILIKE %s OR target ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
    params.append(limit)
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id FROM dose_safety_warnings
                WHERE {' AND '.join(conditions)}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                tuple(params),
            )
            return [row[0] for row in cursor.fetchall()]


def get_dose_safety_warning_latest_by_status(dose_safety_warning_id: str, status: str) -> dict[str, Any] | None:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM dose_safety_warnings
                WHERE dose_safety_warning_id = %s AND status = %s
                ORDER BY version DESC LIMIT 1
                """,
                (dose_safety_warning_id, status),
            )
            row = cursor.fetchone()
            return get_dose_safety_warning(row[0]) if row else None
