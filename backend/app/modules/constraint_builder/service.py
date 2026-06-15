from typing import Any
from functools import lru_cache
from datetime import datetime, timedelta

from app.modules.datastores.postgres import (
    read_approved_constraint_rules,
)
from app.schemas.clinical import Constraint
from app.schemas.clinical_pipeline import NormalizedPatientProfile
from app.schemas.recommendation import RiskFlag


# Cache configuration
_CACHE_TIMESTAMP = None
_CACHE_TTL_SECONDS = 300  # 5 minutes


def _should_refresh_cache() -> bool:
    """Check if cache should be refreshed based on TTL."""
    global _CACHE_TIMESTAMP
    if _CACHE_TIMESTAMP is None:
        return True
    return datetime.now() - _CACHE_TIMESTAMP > timedelta(seconds=_CACHE_TTL_SECONDS)


def invalidate_constraint_cache() -> None:
    """Invalidate the constraint cache (call after DB updates)."""
    global _CACHE_TIMESTAMP
    _CACHE_TIMESTAMP = None
    # Clear the LRU cache
    load_constraint_rules.cache_clear()


def load_constraint_rules() -> list[dict[str, Any]]:
    """Load constraint rules from database (approved constraints and rules).
    
    Loads from:
    - Approved constraint_rules from Postgres (pipeline-generated or seeded).
    
    Results are cached. If the database is unavailable, it logs an error
    and returns an empty list, preventing constraints from being applied.
    """
    global _CACHE_TIMESTAMP
    
    try:
        # Load approved constraint rules from pipeline
        rules_from_db = read_approved_constraint_rules()
        _CACHE_TIMESTAMP = datetime.now()
        return rules_from_db
    except Exception as e:
        # Log but don't crash - return empty list for safety
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"CRITICAL: Could not load constraints from database. No constraints will be applied. Error: {e}")
        return []


def build_constraints(
    profile: NormalizedPatientProfile,
    risks: list[RiskFlag],
) -> list[Constraint]:
    """Build constraints from normalized patient profile and risk flags.
    
    Only uses approved constraints from the database.
    """
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
            Constraint(
                constraint_id=f"{profile.case_id}:{constraint_id}",
                case_id=profile.case_id,
                target_drug_class=rule.get("target_drug_class"),
                action=rule.get("action"),
                reason=rule.get("reason"),
                # constraint_type is not in the constraint_rules table
                constraint_type=rule.get("metadata", {}).get("constraint_type", "soft"),
                evidence_ref=rule.get("evidence_ref"),
            )
        )

    return constraints
