"""Bulk approval helpers for governance catalogs."""

from __future__ import annotations

from typing import Any

from app.modules.datastores.dose_safety_warnings_postgres import (
    approve_dose_safety_warning,
    list_draft_dose_safety_warning_ids,
)
from app.modules.datastores.gdmt_policies_postgres import approve_gdmt_policy, list_draft_gdmt_policy_ids
from app.modules.datastores.interaction_rules_postgres import (
    approve_interaction_rule,
    list_draft_interaction_rule_ids,
)
from app.modules.datastores.postgres import (
    approve_constraint_rule,
    approve_dose_rule,
    list_draft_constraint_rule_ids,
    list_draft_dose_rule_ids,
)


def _dry_run_result(ids: list[int], *, label: str) -> dict[str, Any]:
    return {
        "approved": [],
        "failed": [],
        "skipped": ids,
        "total_requested": len(ids),
        "message": f"Dry run: would approve {len(ids)} draft {label}.",
        "dry_run": True,
        "candidate_ids": ids,
    }


def bulk_approve_constraint_rules(
    admin_user_id: str,
    *,
    rule_ids: list[int] | None = None,
    target_drug_class: str | None = None,
    action: str | None = None,
    q: str | None = None,
    limit: int = 100,
    dry_run: bool = False,
) -> dict[str, Any]:
    ids = list_draft_constraint_rule_ids(
        rule_ids=rule_ids,
        target_drug_class=target_drug_class,
        action=action,
        q=q,
        limit=limit,
    )
    if dry_run:
        return _dry_run_result(ids, label="constraint rules")
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
        "dry_run": False,
        "candidate_ids": [],
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
    dry_run: bool = False,
) -> dict[str, Any]:
    ids = list_draft_dose_rule_ids(
        rule_ids=rule_ids,
        drug_class=drug_class,
        calculation_type=calculation_type,
        safety_tier=safety_tier,
        q=q,
        limit=limit,
    )
    if dry_run:
        return _dry_run_result(ids, label="dose rules")
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
        "dry_run": False,
        "candidate_ids": [],
    }


def bulk_approve_interaction_rules(
    admin_user_id: str,
    *,
    rule_ids: list[int] | None = None,
    severity: str | None = None,
    target: str | None = None,
    safety_tier: str | None = None,
    q: str | None = None,
    extraction_method: str | None = None,
    limit: int = 100,
    dry_run: bool = False,
) -> dict[str, Any]:
    # When approving by filter (no explicit ids), default to usable_rules only.
    effective_tier = safety_tier
    if not rule_ids and not safety_tier:
        effective_tier = "usable_rules"
    ids = list_draft_interaction_rule_ids(
        rule_ids=rule_ids,
        severity=severity,
        target=target,
        safety_tier=effective_tier,
        q=q,
        extraction_method=extraction_method,
        limit=limit,
    )
    if dry_run:
        return _dry_run_result(ids, label="interaction rules")
    approved: list[int] = []
    failed: list[dict[str, Any]] = []
    for rule_id in ids:
        if approve_interaction_rule(rule_id, admin_user_id):
            approved.append(rule_id)
        else:
            failed.append({"id": rule_id, "error": "Approve failed or rule is not draft"})
    return {
        "approved": approved,
        "failed": failed,
        "skipped": [],
        "total_requested": len(ids),
        "message": f"Approved {len(approved)} of {len(ids)} draft interaction rules.",
        "dry_run": False,
        "candidate_ids": [],
    }


def bulk_approve_gdmt_policies(
    admin_user_id: str,
    *,
    rule_ids: list[int] | None = None,
    drug_class_key: str | None = None,
    safety_tier: str | None = None,
    q: str | None = None,
    limit: int = 100,
    dry_run: bool = False,
) -> dict[str, Any]:
    ids = list_draft_gdmt_policy_ids(
        rule_ids=rule_ids,
        drug_class_key=drug_class_key,
        safety_tier=safety_tier,
        q=q,
        limit=limit,
    )
    if dry_run:
        return _dry_run_result(ids, label="GDMT policies")
    approved: list[int] = []
    failed: list[dict[str, Any]] = []
    for rule_id in ids:
        if approve_gdmt_policy(rule_id, admin_user_id):
            approved.append(rule_id)
        else:
            failed.append({"id": rule_id, "error": "Approve failed or policy is not draft"})
    return {
        "approved": approved,
        "failed": failed,
        "skipped": [],
        "total_requested": len(ids),
        "message": f"Approved {len(approved)} of {len(ids)} draft GDMT policies.",
        "dry_run": False,
        "candidate_ids": [],
    }


def bulk_approve_dose_safety_warnings(
    admin_user_id: str,
    *,
    rule_ids: list[int] | None = None,
    target: str | None = None,
    default_severity: str | None = None,
    safety_tier: str | None = None,
    q: str | None = None,
    limit: int = 100,
    dry_run: bool = False,
) -> dict[str, Any]:
    ids = list_draft_dose_safety_warning_ids(
        rule_ids=rule_ids,
        target=target,
        default_severity=default_severity,
        safety_tier=safety_tier,
        q=q,
        limit=limit,
    )
    if dry_run:
        return _dry_run_result(ids, label="dose safety warnings")
    approved: list[int] = []
    failed: list[dict[str, Any]] = []
    for rule_id in ids:
        if approve_dose_safety_warning(rule_id, admin_user_id):
            approved.append(rule_id)
        else:
            failed.append({"id": rule_id, "error": "Approve failed or warning is not draft"})
    return {
        "approved": approved,
        "failed": failed,
        "skipped": [],
        "total_requested": len(ids),
        "message": f"Approved {len(approved)} of {len(ids)} draft dose safety warnings.",
        "dry_run": False,
        "candidate_ids": [],
    }
