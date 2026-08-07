import logging
from datetime import datetime, timedelta
from typing import Any

from app.modules.drug_normalization.service import format_constraint_target
from app.modules.evidence_linking.service import hydrate_constraint

from app.core.circuit_breaker import CircuitOpenError
from app.core.governance_db import load_with_governance_guard
from app.modules.datastores.postgres import (
    read_approved_constraint_rules,
)
from app.schemas.clinical import Constraint
from app.schemas.clinical_pipeline import NormalizedPatientProfile
from app.schemas.recommendation import RiskFlag


logger = logging.getLogger(__name__)

_CACHE_TIMESTAMP: datetime | None = None
_CACHE_TTL_SECONDS = 300  # 5 minutes
_cached_rules: list[dict[str, Any]] | None = None


def _should_refresh_cache() -> bool:
    global _CACHE_TIMESTAMP
    if _CACHE_TIMESTAMP is None or _cached_rules is None:
        return True
    return datetime.now() - _CACHE_TIMESTAMP > timedelta(seconds=_CACHE_TTL_SECONDS)


def invalidate_constraint_cache() -> None:
    """Drop cached rules entirely.

    Use after admin writes so the next load must hit Postgres. On DB failure there is
    no bundled fallback — only stale cache when available.
    """
    global _CACHE_TIMESTAMP, _cached_rules
    _CACHE_TIMESTAMP = None
    _cached_rules = None


def expire_constraint_cache() -> None:
    """Force the TTL window to elapse while keeping the last loaded rules in memory.

    Use in tests to verify refresh behaviour. If Postgres fails on the next load,
    ``load_constraint_rules`` may still serve the previous snapshot as stale cache.
    """
    global _CACHE_TIMESTAMP
    if _CACHE_TIMESTAMP is not None:
        _CACHE_TIMESTAMP = datetime.now() - timedelta(seconds=_CACHE_TTL_SECONDS + 1)


def load_constraint_rules() -> list[dict[str, Any]]:
    """Load approved constraint rules from Postgres with TTL cache.

    Draft rows (including needs_condition_refinement synced for admin review) are never
    returned here — runtime CDSS only evaluates approved constraints synced from the
    ingestion pipeline.
    """
    global _CACHE_TIMESTAMP, _cached_rules

    if not _should_refresh_cache() and _cached_rules is not None:
        return _cached_rules

    try:
        _cached_rules = load_with_governance_guard("constraints", read_approved_constraint_rules)
        _CACHE_TIMESTAMP = datetime.now()
        return _cached_rules
    except CircuitOpenError:
        logger.warning("Constraint circuit open; serving stale cache if available")
        if _cached_rules is not None:
            return _cached_rules
        return []
    except Exception as exc:
        logger.error(
            "CRITICAL: Could not load constraints from database: %s",
            exc,
            exc_info=True,
        )
        if _cached_rules is not None:
            logger.warning("Serving stale approved constraint cache after database error")
            return _cached_rules

        logger.critical("No approved constraints available (sync governance catalogs to Postgres)")
        return []


def build_constraints(
    profile: NormalizedPatientProfile,
    risks: list[RiskFlag],
) -> list[Constraint]:
    """Build constraints from normalized patient profile and risk flags."""
    constraints: list[Constraint] = []
    risk_pairs = {(risk.name, risk.severity) for risk in risks}

    for rule in load_constraint_rules():
        risk_names = rule.get("risk_names", [])
        severity_any = rule.get("severity_any", [])

        matched = any(
            (risk_name, severity) in risk_pairs
            for risk_name in risk_names
            for severity in severity_any
        )
        if not matched:
            continue

        constraint_id = rule.get("constraint_id")

        constraints.append(
            hydrate_constraint(
                Constraint(
                    constraint_id=f"{profile.case_id}:{constraint_id}",
                    case_id=profile.case_id,
                    target_drug_class=format_constraint_target(rule.get("target_drug_class"))
                    or rule.get("target_drug_class"),
                    action=rule.get("action"),
                    reason=rule.get("reason"),
                    constraint_type=rule.get("metadata", {}).get("constraint_type", "soft"),
                    evidence_ref=rule.get("evidence_ref"),
                ),
                rule.get("metadata") or {},
            )
        )

    return constraints
