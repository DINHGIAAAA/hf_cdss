from app.modules.clinical_normalization.service import normalize_patient
from app.modules.constraint_builder.service import build_constraints, load_constraint_rules
from app.modules.risk_extraction.service import extract_risks
from app.schemas.patient import PatientProfile


def _constraints(patient: PatientProfile) -> set[tuple[str, str]]:
    profile = normalize_patient(patient)
    risks = extract_risks(profile)
    return {(constraint.target_drug_class, constraint.action) for constraint in build_constraints(profile, risks)}


def test_load_constraint_rules() -> None:
    rules = load_constraint_rules()

    assert len(rules) >= 6
    assert {rule["constraint_type"] for rule in rules} >= {"hard", "soft", "dose", "monitoring"}


def test_mra_hard_constraint_for_high_renal_or_potassium_risk() -> None:
    constraints = _constraints(
        PatientProfile(case_id="CONS_001", lvef=30, egfr=25, potassium=4.8)
    )

    assert ("MRA", "avoid") in constraints


def test_raasi_caution_for_low_bp_or_hyperkalemia() -> None:
    constraints = _constraints(
        PatientProfile(case_id="CONS_002", lvef=30, egfr=80, potassium=5.2, systolic_bp=96)
    )

    assert ("ARNI/ACEi/ARB", "caution") in constraints


def test_beta_blocker_caution_for_bradycardia() -> None:
    constraints = _constraints(
        PatientProfile(case_id="CONS_003", lvef=30, heart_rate=55)
    )

    assert ("beta_blocker", "caution") in constraints


def test_no_constraints_for_clean_case() -> None:
    constraints = _constraints(
        PatientProfile(case_id="CONS_004", lvef=30, egfr=75, potassium=4.2, systolic_bp=118, heart_rate=72)
    )

    assert constraints == set()
