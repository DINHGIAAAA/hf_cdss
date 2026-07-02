import json
from pathlib import Path

import pytest

from app.modules.clinical_normalization.service import normalize_patient
from app.modules.constraint_builder import service as constraint_service
from app.modules.constraint_builder.service import build_constraints, expire_constraint_cache, load_constraint_rules
from app.modules.risk_extraction.service import extract_risks
from app.schemas.patient import PatientProfile

_CONSTRAINTS_FIXTURE = Path(__file__).resolve().parents[1] / "modules" / "constraint_builder" / "rules" / "constraints_v1.json"


def _rules_fixture() -> list[dict]:
    payload = json.loads(_CONSTRAINTS_FIXTURE.read_text(encoding="utf-8"))
    rules: list[dict] = []
    for index, rule in enumerate(payload, start=1):
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


def _constraints(patient: PatientProfile, monkeypatch: pytest.MonkeyPatch | None = None) -> set[tuple[str, str]]:
    if monkeypatch is not None:
        monkeypatch.setattr(constraint_service, "load_constraint_rules", lambda: _rules_fixture())
    profile = normalize_patient(patient)
    risks = extract_risks(profile)
    return {(constraint.target_drug_class, constraint.action) for constraint in build_constraints(profile, risks)}


def test_load_constraint_rules() -> None:
    rules = load_constraint_rules()

    assert isinstance(rules, list)
    assert all("constraint_id" in rule for rule in rules)
    if rules:
        constraint_types = {
            rule.get("metadata", {}).get("constraint_type") or rule.get("constraint_type")
            for rule in rules
        }
        assert constraint_types


def test_load_constraint_rules_uses_ttl_cache(monkeypatch) -> None:
    constraint_service.invalidate_constraint_cache()
    calls = {"count": 0}

    def fake_read():
        calls["count"] += 1
        return [{"constraint_id": "CACHE_TEST", "metadata": {}}]

    monkeypatch.setattr(constraint_service, "read_approved_constraint_rules", fake_read)

    first = load_constraint_rules()
    second = load_constraint_rules()

    assert first == second
    assert calls["count"] == 1

    expire_constraint_cache()
    third = load_constraint_rules()

    assert third == first
    assert calls["count"] == 2


def test_load_constraint_rules_serves_stale_cache_on_db_error(monkeypatch) -> None:
    constraint_service.invalidate_constraint_cache()
    monkeypatch.setattr(
        constraint_service,
        "read_approved_constraint_rules",
        lambda: [{"constraint_id": "FRESH", "metadata": {}}],
    )
    load_constraint_rules()

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(constraint_service, "read_approved_constraint_rules", boom)
    expire_constraint_cache()

    rules = load_constraint_rules()

    assert rules[0]["constraint_id"] == "FRESH"


def test_load_constraint_rules_falls_back_to_minimum_hard_rules(monkeypatch) -> None:
    constraint_service.invalidate_constraint_cache()

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(constraint_service, "read_approved_constraint_rules", boom)

    rules = load_constraint_rules()

    assert rules
    assert all(rule.get("action") == "avoid" or rule.get("metadata", {}).get("constraint_type") == "hard" for rule in rules)


def test_mra_hard_constraint_for_high_renal_or_potassium_risk(monkeypatch) -> None:
    constraints = _constraints(
        PatientProfile(case_id="CONS_001", lvef=30, egfr=25, potassium=4.8),
        monkeypatch,
    )

    assert ("MRA", "avoid") in constraints


def test_raasi_caution_for_low_bp_or_hyperkalemia(monkeypatch) -> None:
    constraints = _constraints(
        PatientProfile(case_id="CONS_002", lvef=30, egfr=80, potassium=5.2, systolic_bp=96),
        monkeypatch,
    )

    assert ("ARNI/ACEi/ARB", "caution") in constraints


def test_beta_blocker_caution_for_bradycardia(monkeypatch) -> None:
    constraints = _constraints(
        PatientProfile(case_id="CONS_003", lvef=30, heart_rate=55),
        monkeypatch,
    )

    assert ("beta_blocker", "caution") in constraints


def test_no_constraints_for_clean_case(monkeypatch) -> None:
    constraints = _constraints(
        PatientProfile(case_id="CONS_004", lvef=30, egfr=75, potassium=4.2, systolic_bp=118, heart_rate=72),
        monkeypatch,
    )

    assert constraints == set()
