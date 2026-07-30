from app.modules.dose_safety.evaluator import evaluate_dose_safety_warnings
from app.modules.dose_safety.rule_loader import load_executable_dose_safety_warnings
from app.tests.conftest import hfref_patient
from app.tests.fixtures.governance_test_data import sample_dose_safety_warnings


def test_sample_dose_safety_warnings_match_evaluator_behavior() -> None:
    rules = sample_dose_safety_warnings()
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


def test_load_executable_dose_safety_warnings_empty_without_postgres(monkeypatch) -> None:
    from app.modules.dose_safety import rule_loader
    import app.modules.datastores.dose_safety_warnings_postgres as dose_safety_postgres

    rule_loader.invalidate_dose_safety_warnings_cache()
    monkeypatch.setattr(
        dose_safety_postgres,
        "read_approved_dose_safety_warnings",
        lambda: (_ for _ in ()).throw(RuntimeError("postgres unavailable")),
    )
    rules = load_executable_dose_safety_warnings()
    assert rules == []
