import json
from pathlib import Path

from app.schemas.patient import PatientProfile


def test_day1_sample_cases_have_ten_valid_profiles() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    cases_path = repo_root / "data" / "heart_failure" / "evaluation" / "synthetic_cases" / "day1_sample_cases.json"

    cases = json.loads(cases_path.read_text(encoding="utf-8"))

    assert len(cases) == 10
    assert len({case["case_id"] for case in cases}) == 10
    for case in cases:
        PatientProfile.model_validate(case)
