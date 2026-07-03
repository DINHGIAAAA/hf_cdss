"""Postgres helpers for gdmt_policies governance catalog."""

from __future__ import annotations

import logging
from typing import Any

from app.modules.datastores.postgres import _psycopg, postgres_pool


logger = logging.getLogger(__name__)


def _log_gdmt_policy_history(
    cursor,
    gdmt_policy_id: str,
    status_from: str | None,
    status_to: str,
    changed_by: str,
    reason: str | None = None,
) -> None:
    cursor.execute(
        """
        INSERT INTO gdmt_policy_history (gdmt_policy_id, status_from, status_to, changed_by, reason)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (gdmt_policy_id, status_from, status_to, changed_by, reason),
    )


def _row_to_dict(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "gdmt_policy_id": row[1],
        "version": row[2],
        "drug_class_key": row[3],
        "display_label": row[4],
        "sort_order": row[5],
        "policy_body": row[6] or {},
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
    id, gdmt_policy_id, version, drug_class_key, display_label, sort_order,
    policy_body, evidence_ref, clinical_sources, status, source,
    approved_by, approved_at, retired_by, retired_at, created_at,
    updated_at, metadata, safety_tier
"""


def read_approved_gdmt_policies() -> list[dict[str, Any]]:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM gdmt_policies
                WHERE status = 'approved'
                ORDER BY sort_order ASC, created_at DESC
                """
            )
            return [_row_to_dict(row) for row in cursor.fetchall()]


def read_gdmt_policies_by_status(status: str, limit: int = 100) -> list[dict[str, Any]]:
    return read_gdmt_policies_filtered(status=status, limit=limit)


def read_gdmt_policies_filtered(
    *,
    status: str | None = None,
    drug_class_key: str | None = None,
    safety_tier: str | None = None,
    q: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    if status:
        conditions.append("status = %s")
        params.append(status)
    if drug_class_key:
        conditions.append("drug_class_key ILIKE %s")
        params.append(f"%{drug_class_key}%")
    if safety_tier:
        conditions.append("safety_tier = %s")
        params.append(safety_tier)
    if q:
        conditions.append("(gdmt_policy_id ILIKE %s OR display_label ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM gdmt_policies
                {where}
                ORDER BY sort_order ASC, created_at DESC
                LIMIT %s
                """,
                tuple(params),
            )
            return [_row_to_dict(row) for row in cursor.fetchall()]


def get_gdmt_policy(rule_id: int) -> dict[str, Any] | None:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_SELECT_COLUMNS} FROM gdmt_policies WHERE id = %s",
                (rule_id,),
            )
            row = cursor.fetchone()
            return _row_to_dict(row) if row else None


def get_latest_gdmt_policy_version(gdmt_policy_id: str) -> dict[str, Any] | None:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM gdmt_policies
                WHERE gdmt_policy_id = %s
                ORDER BY version DESC LIMIT 1
                """,
                (gdmt_policy_id,),
            )
            row = cursor.fetchone()
            return get_gdmt_policy(row[0]) if row else None


def insert_gdmt_policy(policy: dict[str, Any]) -> bool:
    try:
        psycopg = _psycopg()
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO gdmt_policies (
                        gdmt_policy_id, version, drug_class_key, display_label, sort_order,
                        policy_body, evidence_ref, clinical_sources, source, safety_tier, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (gdmt_policy_id, version) DO UPDATE
                    SET drug_class_key = EXCLUDED.drug_class_key,
                        display_label = EXCLUDED.display_label,
                        sort_order = EXCLUDED.sort_order,
                        policy_body = EXCLUDED.policy_body,
                        evidence_ref = EXCLUDED.evidence_ref,
                        clinical_sources = EXCLUDED.clinical_sources,
                        safety_tier = EXCLUDED.safety_tier,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                    WHERE gdmt_policies.status = 'draft'
                    RETURNING xmax
                    """,
                    (
                        policy.get("gdmt_policy_id"),
                        policy.get("version", 1),
                        policy.get("drug_class_key"),
                        policy.get("display_label"),
                        policy.get("sort_order", 0),
                        psycopg.types.json.Jsonb(policy.get("policy_body") or {}),
                        policy.get("evidence_ref"),
                        psycopg.types.json.Jsonb(policy.get("clinical_sources") or []),
                        policy.get("source", "pipeline_generated"),
                        policy.get("safety_tier"),
                        psycopg.types.json.Jsonb(policy.get("metadata") or {}),
                    ),
                )
                result = cursor.fetchone()
                if result and result[0] == 0:
                    _log_gdmt_policy_history(
                        cursor,
                        policy.get("gdmt_policy_id"),
                        None,
                        "draft",
                        policy.get("source", "pipeline_generated"),
                        "GDMT policy created",
                    )
        return True
    except Exception as exc:
        logger.warning("Failed to insert GDMT policy: %s", exc)
        return False


def approve_gdmt_policy(rule_id: int, admin_user_id: str) -> bool:
    try:
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT gdmt_policy_id FROM gdmt_policies WHERE id = %s AND status = 'draft'",
                    (rule_id,),
                )
                result = cursor.fetchone()
                if not result:
                    return False
                gdmt_policy_id = result[0]
                cursor.execute(
                    """
                    UPDATE gdmt_policies
                    SET status = 'retired', retired_by = %s, retired_at = NOW(), updated_at = NOW()
                    WHERE gdmt_policy_id = %s AND status = 'approved' AND id != %s
                    RETURNING id
                    """,
                    (f"system_auto_retire_by_{admin_user_id}", gdmt_policy_id, rule_id),
                )
                for _ in cursor.fetchall():
                    _log_gdmt_policy_history(
                        cursor,
                        gdmt_policy_id,
                        "approved",
                        "retired",
                        f"system_auto_retire_by_{admin_user_id}",
                        f"Auto-retired due to new version approval (rule_id: {rule_id})",
                    )
                cursor.execute(
                    """
                    UPDATE gdmt_policies
                    SET status = 'approved', approved_by = %s, approved_at = NOW(), updated_at = NOW()
                    WHERE id = %s AND status = 'draft'
                    """,
                    (admin_user_id, rule_id),
                )
                if cursor.rowcount == 0:
                    return False
                _log_gdmt_policy_history(
                    cursor, gdmt_policy_id, "draft", "approved", admin_user_id, "GDMT policy approved"
                )
        return True
    except Exception as exc:
        logger.warning("Failed to approve GDMT policy %s: %s", rule_id, exc)
        return False


def retire_gdmt_policy(rule_id: int, admin_user_id: str) -> bool:
    try:
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT gdmt_policy_id FROM gdmt_policies WHERE id = %s", (rule_id,))
                row = cursor.fetchone()
                if not row:
                    return False
                gdmt_policy_id = row[0]
                cursor.execute(
                    """
                    UPDATE gdmt_policies
                    SET status = 'retired', retired_by = %s, retired_at = NOW(), updated_at = NOW()
                    WHERE id = %s AND status = 'approved'
                    """,
                    (admin_user_id, rule_id),
                )
                if cursor.rowcount > 0:
                    _log_gdmt_policy_history(
                        cursor, gdmt_policy_id, "approved", "retired", admin_user_id, "GDMT policy retired"
                    )
        return True
    except Exception as exc:
        logger.warning("Failed to retire GDMT policy %s: %s", rule_id, exc)
        return False


def unretire_gdmt_policy(rule_id: int, admin_user_id: str) -> bool:
    try:
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT gdmt_policy_id FROM gdmt_policies WHERE id = %s AND status = 'retired'",
                    (rule_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return False
                gdmt_policy_id = row[0]
                cursor.execute(
                    """
                    UPDATE gdmt_policies
                    SET status = 'retired', retired_by = %s, retired_at = NOW(), updated_at = NOW()
                    WHERE gdmt_policy_id = %s AND status = 'approved' AND id != %s
                    """,
                    (f"system_auto_retire_by_{admin_user_id}", gdmt_policy_id, rule_id),
                )
                cursor.execute(
                    """
                    UPDATE gdmt_policies
                    SET status = 'approved', approved_by = %s, approved_at = NOW(),
                        retired_by = NULL, retired_at = NULL, updated_at = NOW()
                    WHERE id = %s AND status = 'retired'
                    """,
                    (admin_user_id, rule_id),
                )
                if cursor.rowcount > 0:
                    _log_gdmt_policy_history(
                        cursor, gdmt_policy_id, "retired", "approved", admin_user_id, "GDMT policy restored"
                    )
        return True
    except Exception as exc:
        logger.warning("Failed to un-retire GDMT policy %s: %s", rule_id, exc)
        return False


def gdmt_policy_with_id_exists(gdmt_policy_id: str) -> bool:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM gdmt_policies WHERE gdmt_policy_id = %s LIMIT 1", (gdmt_policy_id,))
            return cursor.fetchone() is not None


def get_gdmt_policy_versions(gdmt_policy_id: str) -> list[dict[str, Any]]:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, gdmt_policy_id, version, status, created_at, updated_at
                FROM gdmt_policies
                WHERE gdmt_policy_id = %s
                ORDER BY version DESC
                """,
                (gdmt_policy_id,),
            )
            return [
                {
                    "id": row[0],
                    "gdmt_policy_id": row[1],
                    "version": row[2],
                    "status": row[3],
                    "created_at": row[4].isoformat(),
                    "updated_at": row[5].isoformat(),
                }
                for row in cursor.fetchall()
            ]


def read_gdmt_policy_history(gdmt_policy_id: str) -> list[dict[str, Any]]:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT history_id, gdmt_policy_id, status_from, status_to, changed_by, changed_at, reason
                FROM gdmt_policy_history
                WHERE gdmt_policy_id = %s
                ORDER BY changed_at DESC
                """,
                (gdmt_policy_id,),
            )
            return [
                {
                    "history_id": row[0],
                    "gdmt_policy_id": row[1],
                    "status_from": row[2],
                    "status_to": row[3],
                    "changed_by": row[4],
                    "changed_at": row[5].isoformat(),
                    "reason": row[6],
                }
                for row in cursor.fetchall()
            ]


def list_draft_gdmt_policy_ids(
    *,
    rule_ids: list[int] | None = None,
    drug_class_key: str | None = None,
    safety_tier: str | None = None,
    q: str | None = None,
    limit: int = 100,
) -> list[int]:
    conditions = ["status = 'draft'"]
    params: list[Any] = []
    if rule_ids:
        conditions.append("id = ANY(%s)")
        params.append(rule_ids)
    if drug_class_key:
        conditions.append("drug_class_key ILIKE %s")
        params.append(f"%{drug_class_key}%")
    if safety_tier:
        conditions.append("safety_tier = %s")
        params.append(safety_tier)
    if q:
        conditions.append("(gdmt_policy_id ILIKE %s OR display_label ILIKE %s)")
        params.extend([f"%{q}%", f"%{q}%"])
    params.append(limit)
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id FROM gdmt_policies
                WHERE {' AND '.join(conditions)}
                ORDER BY sort_order ASC, created_at DESC
                LIMIT %s
                """,
                tuple(params),
            )
            return [row[0] for row in cursor.fetchall()]


def get_gdmt_policy_latest_by_status(gdmt_policy_id: str, status: str) -> dict[str, Any] | None:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM gdmt_policies
                WHERE gdmt_policy_id = %s AND status = %s
                ORDER BY version DESC LIMIT 1
                """,
                (gdmt_policy_id, status),
            )
            row = cursor.fetchone()
            return get_gdmt_policy(row[0]) if row else None
