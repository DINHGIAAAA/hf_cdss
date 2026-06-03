import json
from pathlib import Path
from typing import Any

from app.schemas.clinical import Constraint
from app.schemas.clinical_pipeline import NormalizedPatientProfile
from app.schemas.recommendation import RiskFlag


RULES_PATH = Path(__file__).parent / "rules" / "constraints_v1.json"


def load_constraint_rules() -> list[dict[str, Any]]:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


def build_constraints(
    profile: NormalizedPatientProfile,
    risks: list[RiskFlag],
) -> list[Constraint]:
    constraints: list[Constraint] = []
    risk_pairs = {(risk.name, risk.severity) for risk in risks}

    for rule in load_constraint_rules():
        matched = any(
            (risk_name, severity) in risk_pairs
            for risk_name in rule["risk_names"]
            for severity in rule["severity_any"]
        )
        if not matched:
            continue

        constraints.append(
            Constraint(
                constraint_id=f"{profile.case_id}:{rule['constraint_id']}",
                case_id=profile.case_id,
                target_drug_class=rule["target_drug_class"],
                action=rule["action"],
                reason=rule["reason"],
                evidence_ref=rule["evidence_ref"],
            )
        )

    return constraints
