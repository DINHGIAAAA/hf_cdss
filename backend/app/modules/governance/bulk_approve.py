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


BULK_APPROVE_BATCH_SIZE = 200


def _approve_ids(
    approve_fn,
    admin_user_id: str,
    ids: list[int],
) -> tuple[list[int], list[dict[str, Any]]]:
    approved: list[int] = []
    failed: list[dict[str, Any]] = []
    for rule_id in ids:
        if approve_fn(rule_id, admin_user_id):
            approved.append(rule_id)
        else:
            failed.append({"id": rule_id, "error": "Approve failed or rule is not draft"})
    return approved, failed


def _bulk_approve_result(
    *,
    approved: list[int],
    failed: list[dict[str, Any]],
    total_requested: int,
    label: str,
    dry_run: bool,
    candidate_ids: list[int] | None = None,
) -> dict[str, Any]:
    if dry_run:
        return _dry_run_result(candidate_ids or [], label=label)
    return {
        "approved": approved,
        "failed": failed,
        "skipped": [],
        "total_requested": total_requested,
        "message": f"Approved {len(approved)} of {total_requested} draft {label}.",
        "dry_run": False,
        "candidate_ids": [],
    }


def _run_bulk_approve(
    *,
    list_ids_fn,
    approve_fn,
    admin_user_id: str,
    list_kwargs: dict[str, Any],
    rule_ids: list[int] | None,
    match_all: bool,
    limit: int,
    dry_run: bool,
    label: str,
) -> dict[str, Any]:
    if rule_ids:
        ids = list_ids_fn(rule_ids=rule_ids, limit=max(len(rule_ids), limit), **list_kwargs)
        if dry_run:
            return _dry_run_result(ids, label=label)
        approved, failed = _approve_ids(approve_fn, admin_user_id, ids)
        return _bulk_approve_result(
            approved=approved,
            failed=failed,
            total_requested=len(ids),
            label=label,
            dry_run=False,
        )

    if match_all:
        if dry_run:
            preview = list_ids_fn(limit=10_000, **list_kwargs)
            return _dry_run_result(preview, label=label)

        approved_all: list[int] = []
        failed_all: list[dict[str, Any]] = []
        total = 0
        while True:
            ids = list_ids_fn(limit=BULK_APPROVE_BATCH_SIZE, **list_kwargs)
            if not ids:
                break
            total += len(ids)
            approved, failed = _approve_ids(approve_fn, admin_user_id, ids)
            approved_all.extend(approved)
            failed_all.extend(failed)
            if len(ids) < BULK_APPROVE_BATCH_SIZE:
                break
        return _bulk_approve_result(
            approved=approved_all,
            failed=failed_all,
            total_requested=total,
            label=label,
            dry_run=False,
        )

    ids = list_ids_fn(limit=limit, **list_kwargs)
    if dry_run:
        return _dry_run_result(ids, label=label)
    approved, failed = _approve_ids(approve_fn, admin_user_id, ids)
    return _bulk_approve_result(
        approved=approved,
        failed=failed,
        total_requested=len(ids),
        label=label,
        dry_run=False,
    )


def bulk_approve_constraint_rules(
    admin_user_id: str,
    *,
    rule_ids: list[int] | None = None,
    target_drug_class: str | None = None,
    action: str | None = None,
    q: str | None = None,
    safety_tier: str | None = None,
    needs_condition: bool | None = None,
    limit: int = 100,
    match_all: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    list_kwargs = {
        "target_drug_class": target_drug_class,
        "action": action,
        "q": q,
        "safety_tier": safety_tier,
        "needs_condition": needs_condition,
    }
    return _run_bulk_approve(
        list_ids_fn=list_draft_constraint_rule_ids,
        approve_fn=approve_constraint_rule,
        admin_user_id=admin_user_id,
        list_kwargs=list_kwargs,
        rule_ids=rule_ids,
        match_all=match_all,
        limit=limit,
        dry_run=dry_run,
        label="constraint rules",
    )


def bulk_approve_dose_rules(
    admin_user_id: str,
    *,
    rule_ids: list[int] | None = None,
    drug_class: str | None = None,
    calculation_type: str | None = None,
    safety_tier: str | None = None,
    q: str | None = None,
    limit: int = 100,
    match_all: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    list_kwargs = {
        "drug_class": drug_class,
        "calculation_type": calculation_type,
        "safety_tier": safety_tier,
        "q": q,
    }
    return _run_bulk_approve(
        list_ids_fn=list_draft_dose_rule_ids,
        approve_fn=approve_dose_rule,
        admin_user_id=admin_user_id,
        list_kwargs=list_kwargs,
        rule_ids=rule_ids,
        match_all=match_all,
        limit=limit,
        dry_run=dry_run,
        label="dose rules",
    )


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
    match_all: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    effective_tier = safety_tier
    if not rule_ids and not match_all and not safety_tier:
        effective_tier = "usable_rules"
    list_kwargs = {
        "severity": severity,
        "target": target,
        "safety_tier": effective_tier,
        "q": q,
        "extraction_method": extraction_method,
    }
    return _run_bulk_approve(
        list_ids_fn=list_draft_interaction_rule_ids,
        approve_fn=approve_interaction_rule,
        admin_user_id=admin_user_id,
        list_kwargs=list_kwargs,
        rule_ids=rule_ids,
        match_all=match_all,
        limit=limit,
        dry_run=dry_run,
        label="interaction rules",
    )


def bulk_approve_gdmt_policies(
    admin_user_id: str,
    *,
    rule_ids: list[int] | None = None,
    drug_class_key: str | None = None,
    safety_tier: str | None = None,
    q: str | None = None,
    limit: int = 100,
    match_all: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    list_kwargs = {
        "drug_class_key": drug_class_key,
        "safety_tier": safety_tier,
        "q": q,
    }
    return _run_bulk_approve(
        list_ids_fn=list_draft_gdmt_policy_ids,
        approve_fn=approve_gdmt_policy,
        admin_user_id=admin_user_id,
        list_kwargs=list_kwargs,
        rule_ids=rule_ids,
        match_all=match_all,
        limit=limit,
        dry_run=dry_run,
        label="GDMT policies",
    )


def bulk_approve_dose_safety_warnings(
    admin_user_id: str,
    *,
    rule_ids: list[int] | None = None,
    target: str | None = None,
    default_severity: str | None = None,
    safety_tier: str | None = None,
    q: str | None = None,
    limit: int = 100,
    match_all: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    list_kwargs = {
        "target": target,
        "default_severity": default_severity,
        "safety_tier": safety_tier,
        "q": q,
    }
    return _run_bulk_approve(
        list_ids_fn=list_draft_dose_safety_warning_ids,
        approve_fn=approve_dose_safety_warning,
        admin_user_id=admin_user_id,
        list_kwargs=list_kwargs,
        rule_ids=rule_ids,
        match_all=match_all,
        limit=limit,
        dry_run=dry_run,
        label="dose safety warnings",
    )
