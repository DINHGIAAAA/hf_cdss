import json
from pathlib import Path

from app.modules.dose_safety.evaluator import evaluate_dose_safety_warnings
from app.modules.dose_safety.rule_loader import load_executable_dose_safety_warnings
from app.tests.conftest import hfref_patient


RULES_PATH = Path(__file__).resolve().parents[1] / "modules" / "dose_safety" / "rules" / "hf_dose_safety_warnings_v1.json"


def test_bundled_dose_safety_warnings_match_week7_behavior() -> None:
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))["warnings"]
    patient = hfref_patient(
        case_id="CASE_EVAL",
        potassium=5.6,
        current_medications=["digoxin", "spironolactone", "furosemide"],
    )
    warnings = evaluate_dose_safety_warnings(patient, rules)
    warning_ids = {item.warning_id for item in warnings}
    assert "dose_digoxin_renal_review" in warning_ids
    assert "dose_mra_renal_potassium_review" in warning_ids
    assert "dose_loop_diuretic_lab_monitoring" in warning_ids
    assert any(item.severity == "critical" for item in warnings)


def test_load_executable_dose_safety_warnings_uses_bundled_fallback() -> None:
    rules = load_executable_dose_safety_warnings()
    assert len(rules) >= 4
    assert any(rule.get("dose_safety_warning_id") == "dose_digoxin_renal_review" for rule in rules)
