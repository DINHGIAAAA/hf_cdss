"""Load governance catalog rows for backend tests (not production runtime)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_FIXTURES_DIR = Path(__file__).resolve().parent


def _read_fixture(name: str) -> Any:
    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8-sig"))


def approved_constraint_rules_rows() -> list[dict[str, Any]]:
    """Postgres-shaped approved constraint rows mirroring legacy constraints_v1.json."""
    rules: list[dict[str, Any]] = []
    for index, rule in enumerate(_read_fixture("constraints_sample.json"), start=1):
        rules.append(
            {
                "id": index,
                "constraint_id": rule["constraint_id"],
                "version": 1,
                "target_drug_class": rule.get("target_drug_class"),
                "action": rule.get("action"),
                "reason": rule.get("reason", ""),
                "risk_names": list(rule.get("risk_names") or []),
                "severity_any": list(rule.get("severity_any") or []),
                "evidence_ref": rule.get("evidence_ref"),
                "clinical_sources": list(rule.get("clinical_sources") or []),
                "metadata": {"constraint_type": rule.get("constraint_type", "soft")},
            }
        )
    return rules


def sample_dose_safety_warnings() -> list[dict[str, Any]]:
    payload = _read_fixture("dose_safety_sample.json")
    return list(payload.get("warnings") or [])
