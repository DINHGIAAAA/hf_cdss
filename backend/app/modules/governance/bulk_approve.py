"""Bulk approval helpers for governance catalogs."""

from __future__ import annotations

from typing import Any

from app.modules.datastores.postgres import (
    approve_constraint_rule,
    approve_dose_rule,
    list_draft_constraint_rule_ids,
    list_draft_dose_rule_ids,
)


def bulk_approve_constraint_rules(
    admin_user_id: str,
    *,
    rule_ids: list[int] | None = None,
    target_drug_class: str | None = None,
    action: str | None = None,
    q: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    ids = list_draft_constraint_rule_ids(
        rule_ids=rule_ids,
        target_drug_class=target_drug_class,
        action=action,
        q=q,
        limit=limit,
    )
    approved: list[int] = []
    failed: list[dict[str, Any]] = []
    for rule_id in ids:
        if approve_constraint_rule(rule_id, admin_user_id):
            approved.append(rule_id)
        else:
            failed.append({"id": rule_id, "error": "Approve failed or rule is not draft"})
    return {
        "approved": approved,
        "failed": failed,
        "skipped": [],
        "total_requested": len(ids),
        "message": f"Approved {len(approved)} of {len(ids)} draft constraint rules.",
    }


def bulk_approve_dose_rules(
    admin_user_id: str,
    *,
    rule_ids: list[int] | None = None,
    drug_class: str | None = None,
    calculation_type: str | None = None,
    safety_tier: str | None = None,
    q: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    ids = list_draft_dose_rule_ids(
        rule_ids=rule_ids,
        drug_class=drug_class,
        calculation_type=calculation_type,
        safety_tier=safety_tier,
        q=q,
        limit=limit,
    )
    approved: list[int] = []
    failed: list[dict[str, Any]] = []
    for rule_id in ids:
        if approve_dose_rule(rule_id, admin_user_id):
            approved.append(rule_id)
        else:
            failed.append({"id": rule_id, "error": "Approve failed or rule is not draft"})
    return {
        "approved": approved,
        "failed": failed,
        "skipped": [],
        "total_requested": len(ids),
        "message": f"Approved {len(approved)} of {len(ids)} draft dose rules.",
    }
