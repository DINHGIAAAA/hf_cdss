"""Postgres helpers for interaction_rules governance catalog."""

from __future__ import annotations

import logging
from typing import Any

from app.modules.datastores.postgres import _psycopg, postgres_pool


logger = logging.getLogger(__name__)


def _log_interaction_rule_history(
    cursor,
    interaction_rule_id: str,
    status_from: str | None,
    status_to: str,
    changed_by: str,
    reason: str | None = None,
) -> None:
    cursor.execute(
        """
        INSERT INTO interaction_rule_history (interaction_rule_id, status_from, status_to, changed_by, reason)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (interaction_rule_id, status_from, status_to, changed_by, reason),
    )


def read_approved_interaction_rules() -> list[dict[str, Any]]:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, interaction_rule_id, version, drug_set_a, drug_set_b, severity, target,
                       rule_body, evidence_ref, clinical_sources, metadata, status
                FROM interaction_rules
                WHERE status = 'approved'
                ORDER BY created_at DESC
                """
            )
            return [
                {
                    "id": row[0],
                    "interaction_rule_id": row[1],
                    "version": row[2],
                    "drug_set_a": list(row[3]) if row[3] else [],
                    "drug_set_b": list(row[4]) if row[4] else [],
                    "severity": row[5],
                    "target": row[6],
                    "rule_body": row[7] or {},
                    "evidence_ref": row[8],
                    "clinical_sources": row[9] or [],
                    "metadata": row[10] or {},
                    "status": row[11],
                }
                for row in cursor.fetchall()
            ]


def read_interaction_rules_by_status(status: str, limit: int = 100) -> list[dict[str, Any]]:
    return read_interaction_rules_filtered(status=status, limit=limit)


def read_interaction_rules_filtered(
    *,
    status: str | None = None,
    severity: str | None = None,
    target: str | None = None,
    safety_tier: str | None = None,
    q: str | None = None,
    extraction_method: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    if status:
        conditions.append("status = %s")
        params.append(status)
    if severity:
        conditions.append("severity = %s")
        params.append(severity)
    if target:
        conditions.append("target ILIKE %s")
        params.append(f"%{target}%")
    if safety_tier:
        conditions.append("safety_tier = %s")
        params.append(safety_tier)
    if q:
        conditions.append("interaction_rule_id ILIKE %s")
        params.append(f"%{q}%")
    if extraction_method:
        conditions.append("metadata->>'extraction_method' ILIKE %s")
        params.append(f"%{extraction_method}%")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, interaction_rule_id, version, drug_set_a, drug_set_b, severity, target,
                       rule_body, evidence_ref, clinical_sources, status, source,
                       approved_by, approved_at, retired_by, retired_at, created_at,
                       updated_at, metadata, safety_tier
                FROM interaction_rules
                {where}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                tuple(params),
            )
            return [
                {
                    "id": row[0],
                    "interaction_rule_id": row[1],
                    "version": row[2],
                    "drug_set_a": list(row[3]) if row[3] else [],
                    "drug_set_b": list(row[4]) if row[4] else [],
                    "severity": row[5],
                    "target": row[6],
                    "rule_body": row[7] or {},
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
                    "safety_tier": row[19],
                }
                for row in cursor.fetchall()
            ]


def get_interaction_rule(rule_id: int) -> dict[str, Any] | None:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, interaction_rule_id, version, drug_set_a, drug_set_b, severity, target,
                       rule_body, evidence_ref, clinical_sources, status, source,
                       approved_by, approved_at, retired_by, retired_at, created_at,
                       updated_at, metadata, safety_tier
                FROM interaction_rules WHERE id = %s
                """,
                (rule_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "interaction_rule_id": row[1],
                "version": row[2],
                "drug_set_a": list(row[3]) if row[3] else [],
                "drug_set_b": list(row[4]) if row[4] else [],
                "severity": row[5],
                "target": row[6],
                "rule_body": row[7] or {},
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
                "safety_tier": row[19],
            }


def get_latest_interaction_rule_version(interaction_rule_id: str) -> dict[str, Any] | None:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM interaction_rules
                WHERE interaction_rule_id = %s
                ORDER BY version DESC LIMIT 1
                """,
                (interaction_rule_id,),
            )
            row = cursor.fetchone()
            return get_interaction_rule(row[0]) if row else None


def insert_interaction_rule(rule: dict[str, Any]) -> bool:
    try:
        psycopg = _psycopg()
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO interaction_rules (
                        interaction_rule_id, version, drug_set_a, drug_set_b, severity, target,
                        rule_body, evidence_ref, clinical_sources, source, safety_tier, metadata
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (interaction_rule_id, version) DO UPDATE
                    SET drug_set_a = EXCLUDED.drug_set_a,
                        drug_set_b = EXCLUDED.drug_set_b,
                        severity = EXCLUDED.severity,
                        target = EXCLUDED.target,
                        rule_body = EXCLUDED.rule_body,
                        evidence_ref = EXCLUDED.evidence_ref,
                        clinical_sources = EXCLUDED.clinical_sources,
                        safety_tier = EXCLUDED.safety_tier,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                    WHERE interaction_rules.status = 'draft'
                    RETURNING xmax
                    """,
                    (
                        rule.get("interaction_rule_id"),
                        rule.get("version", 1),
                        rule.get("drug_set_a", []),
                        rule.get("drug_set_b", []),
                        rule.get("severity", "moderate"),
                        rule.get("target"),
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
                    _log_interaction_rule_history(
                        cursor,
                        rule.get("interaction_rule_id"),
                        None,
                        "draft",
                        rule.get("source", "pipeline_generated"),
                        "Interaction rule created",
                    )
        return True
    except Exception as exc:
        logger.warning("Failed to insert interaction rule: %s", exc)
        return False


def approve_interaction_rule(rule_id: int, admin_user_id: str) -> bool:
    try:
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT interaction_rule_id FROM interaction_rules WHERE id = %s AND status = 'draft'",
                    (rule_id,),
                )
                result = cursor.fetchone()
                if not result:
                    return False
                interaction_rule_id = result[0]
                cursor.execute(
                    """
                    UPDATE interaction_rules
                    SET status = 'retired', retired_by = %s, retired_at = NOW(), updated_at = NOW()
                    WHERE interaction_rule_id = %s AND status = 'approved' AND id != %s
                    RETURNING id
                    """,
                    (f"system_auto_retire_by_{admin_user_id}", interaction_rule_id, rule_id),
                )
                for _ in cursor.fetchall():
                    _log_interaction_rule_history(
                        cursor,
                        interaction_rule_id,
                        "approved",
                        "retired",
                        f"system_auto_retire_by_{admin_user_id}",
                        f"Auto-retired due to new version approval (rule_id: {rule_id})",
                    )
                cursor.execute(
                    """
                    UPDATE interaction_rules
                    SET status = 'approved', approved_by = %s, approved_at = NOW(), updated_at = NOW()
                    WHERE id = %s AND status = 'draft'
                    """,
                    (admin_user_id, rule_id),
                )
                if cursor.rowcount == 0:
                    return False
                _log_interaction_rule_history(
                    cursor, interaction_rule_id, "draft", "approved", admin_user_id, "Interaction rule approved"
                )
        return True
    except Exception as exc:
        logger.warning("Failed to approve interaction rule %s: %s", rule_id, exc)
        return False


def retire_interaction_rule(rule_id: int, admin_user_id: str) -> bool:
    try:
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT interaction_rule_id FROM interaction_rules WHERE id = %s", (rule_id,))
                row = cursor.fetchone()
                if not row:
                    return False
                interaction_rule_id = row[0]
                cursor.execute(
                    """
                    UPDATE interaction_rules
                    SET status = 'retired', retired_by = %s, retired_at = NOW(), updated_at = NOW()
                    WHERE id = %s AND status = 'approved'
                    """,
                    (admin_user_id, rule_id),
                )
                if cursor.rowcount > 0:
                    _log_interaction_rule_history(
                        cursor, interaction_rule_id, "approved", "retired", admin_user_id, "Interaction rule retired"
                    )
        return True
    except Exception as exc:
        logger.warning("Failed to retire interaction rule %s: %s", rule_id, exc)
        return False


def unretire_interaction_rule(rule_id: int, admin_user_id: str) -> bool:
    try:
        with postgres_pool().connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT interaction_rule_id FROM interaction_rules WHERE id = %s AND status = 'retired'",
                    (rule_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return False
                interaction_rule_id = row[0]
                cursor.execute(
                    """
                    UPDATE interaction_rules
                    SET status = 'retired', retired_by = %s, retired_at = NOW(), updated_at = NOW()
                    WHERE interaction_rule_id = %s AND status = 'approved' AND id != %s
                    """,
                    (f"system_auto_retire_by_{admin_user_id}", interaction_rule_id, rule_id),
                )
                cursor.execute(
                    """
                    UPDATE interaction_rules
                    SET status = 'approved', approved_by = %s, approved_at = NOW(),
                        retired_by = NULL, retired_at = NULL, updated_at = NOW()
                    WHERE id = %s AND status = 'retired'
                    """,
                    (admin_user_id, rule_id),
                )
                if cursor.rowcount > 0:
                    _log_interaction_rule_history(
                        cursor, interaction_rule_id, "retired", "approved", admin_user_id, "Interaction rule restored"
                    )
        return True
    except Exception as exc:
        logger.warning("Failed to un-retire interaction rule %s: %s", rule_id, exc)
        return False


def interaction_rule_with_id_exists(interaction_rule_id: str) -> bool:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM interaction_rules WHERE interaction_rule_id = %s LIMIT 1",
                (interaction_rule_id,),
            )
            return cursor.fetchone() is not None


def get_interaction_rule_versions(interaction_rule_id: str) -> list[dict[str, Any]]:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, interaction_rule_id, version, status, created_at, updated_at
                FROM interaction_rules
                WHERE interaction_rule_id = %s
                ORDER BY version DESC
                """,
                (interaction_rule_id,),
            )
            return [
                {
                    "id": row[0],
                    "interaction_rule_id": row[1],
                    "version": row[2],
                    "status": row[3],
                    "created_at": row[4].isoformat(),
                    "updated_at": row[5].isoformat(),
                }
                for row in cursor.fetchall()
            ]


def read_interaction_rule_history(interaction_rule_id: str) -> list[dict[str, Any]]:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT history_id, interaction_rule_id, status_from, status_to, changed_by, changed_at, reason
                FROM interaction_rule_history
                WHERE interaction_rule_id = %s
                ORDER BY changed_at DESC
                """,
                (interaction_rule_id,),
            )
            return [
                {
                    "history_id": row[0],
                    "interaction_rule_id": row[1],
                    "status_from": row[2],
                    "status_to": row[3],
                    "changed_by": row[4],
                    "changed_at": row[5].isoformat(),
                    "reason": row[6],
                }
                for row in cursor.fetchall()
            ]


def list_draft_interaction_rule_ids(
    *,
    rule_ids: list[int] | None = None,
    severity: str | None = None,
    target: str | None = None,
    safety_tier: str | None = None,
    q: str | None = None,
    extraction_method: str | None = None,
    limit: int = 100,
) -> list[int]:
    conditions = ["status = 'draft'"]
    params: list[Any] = []
    if rule_ids:
        conditions.append("id = ANY(%s)")
        params.append(rule_ids)
    if severity:
        conditions.append("severity = %s")
        params.append(severity)
    if target:
        conditions.append("target ILIKE %s")
        params.append(f"%{target}%")
    if safety_tier:
        conditions.append("safety_tier = %s")
        params.append(safety_tier)
    if q:
        conditions.append("interaction_rule_id ILIKE %s")
        params.append(f"%{q}%")
    if extraction_method:
        conditions.append("metadata->>'extraction_method' ILIKE %s")
        params.append(f"%{extraction_method}%")
    params.append(limit)
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id FROM interaction_rules
                WHERE {' AND '.join(conditions)}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                tuple(params),
            )
            return [row[0] for row in cursor.fetchall()]


def get_interaction_rule_latest_by_status(interaction_rule_id: str, status: str) -> dict[str, Any] | None:
    with postgres_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM interaction_rules
                WHERE interaction_rule_id = %s AND status = %s
                ORDER BY version DESC LIMIT 1
                """,
                (interaction_rule_id, status),
            )
            row = cursor.fetchone()
            return get_interaction_rule(row[0]) if row else None
