import json
import logging
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.modules.drug_normalization.service import format_constraint_target
from app.modules.evidence_linking.service import hydrate_constraint

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
_MINIMUM_RULES_PATH = Path(__file__).resolve().parent / "rules" / "constraints_v1.json"


def _should_refresh_cache() -> bool:
    global _CACHE_TIMESTAMP
    if _CACHE_TIMESTAMP is None or _cached_rules is None:
        return True
    return datetime.now() - _CACHE_TIMESTAMP > timedelta(seconds=_CACHE_TTL_SECONDS)


def invalidate_constraint_cache() -> None:
    """Invalidate the constraint cache (call after DB updates)."""
    global _CACHE_TIMESTAMP, _cached_rules
    _CACHE_TIMESTAMP = None
    _cached_rules = None


@lru_cache(maxsize=1)
def _minimum_safety_rules() -> list[dict[str, Any]]:
    """Hard safety rules used only when the database is unavailable and cache is empty."""
    if not _MINIMUM_RULES_PATH.is_file():
        return []

    payload = json.loads(_MINIMUM_RULES_PATH.read_text(encoding="utf-8"))
    rules: list[dict[str, Any]] = []
    for index, rule in enumerate(payload, start=1):
        if rule.get("action") != "avoid" and rule.get("constraint_type") != "hard":
            continue
        rules.append(
            {
                "id": -index,
                "constraint_id": rule["constraint_id"],
                "version": 1,
                "target_drug_class": rule.get("target_drug_class"),
                "action": rule.get("action"),
                "reason": rule.get("reason", ""),
                "risk_names": list(rule.get("risk_names") or []),
                "severity_any": list(rule.get("severity_any") or []),
                "evidence_ref": rule.get("evidence_ref"),
                "clinical_sources": list(rule.get("clinical_sources") or []),
                "metadata": {
                    "constraint_type": rule.get("constraint_type", "hard"),
                    "fallback_source": "constraints_v1.json",
                },
            }
        )
    return rules


def load_constraint_rules() -> list[dict[str, Any]]:
    """Load approved constraint rules from Postgres with TTL cache and safe fallbacks."""
    global _CACHE_TIMESTAMP, _cached_rules

    if not _should_refresh_cache() and _cached_rules is not None:
        return _cached_rules

    try:
        _cached_rules = read_approved_constraint_rules()
        _CACHE_TIMESTAMP = datetime.now()
        return _cached_rules
    except Exception as exc:
        logger.error(
            "CRITICAL: Could not load constraints from database: %s",
            exc,
            exc_info=True,
        )
        if _cached_rules is not None:
            logger.warning("Serving stale approved constraint cache after database error")
            return _cached_rules

        minimum = _minimum_safety_rules()
        if minimum:
            logger.critical(
                "Serving %s minimum hardcoded safety constraint(s) after database error",
                len(minimum),
            )
            return minimum

        logger.critical("No approved or fallback constraints available")
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
