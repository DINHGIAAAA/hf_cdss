import json
from pathlib import Path

from app.modules.clinical_normalization.service import normalize_patient
from app.modules.constraint_builder.service import build_constraints
from app.modules.risk_extraction.service import extract_risks
from app.schemas.patient import PatientProfile


def test_week2_cases_match_expected_risk_labels() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    eval_dir = repo_root / "data" / "heart_failure" / "evaluation"
    cases = json.loads((eval_dir / "synthetic_cases" / "week2_30_cases.json").read_text(encoding="utf-8"))
    labels = json.loads((eval_dir / "gold_labels" / "week2_expected_risks.json").read_text(encoding="utf-8"))
    expected_by_case = {item["case_id"]: set(item["expected_risks"]) for item in labels}

    assert len(cases) == 30
    assert len(labels) == 30

    for raw_case in cases:
        patient = PatientProfile.model_validate(raw_case)
        profile = normalize_patient(patient)
        actual = {risk.name for risk in extract_risks(profile)}

        assert expected_by_case[patient.case_id] <= actual


def test_week2_high_risk_cases_generate_constraints() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    cases = json.loads(
        (repo_root / "data" / "heart_failure" / "evaluation" / "synthetic_cases" / "week2_30_cases.json").read_text(
            encoding="utf-8"
        )
    )

    constrained_case_ids = set()
    for raw_case in cases:
        patient = PatientProfile.model_validate(raw_case)
        profile = normalize_patient(patient)
        risks = extract_risks(profile)
        constraints = build_constraints(profile, risks)
        if constraints:
            constrained_case_ids.add(patient.case_id)

    assert {"W2_CASE_005", "W2_CASE_012", "W2_CASE_019", "W2_CASE_029"} <= constrained_case_ids
