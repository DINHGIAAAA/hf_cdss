from app.modules.dose_calculator.rule_loader import (
    _rows_to_rules,
    invalidate_dose_rules_cache,
    load_dose_rules_bundle,
)


def test_rows_to_rules_merges_db_metadata() -> None:
    rows = [
        {
            "dose_rule_id": "apixaban_af_dose_reduction",
            "version": 2,
            "status": "approved",
            "drug_keys": ["apixaban"],
            "drug_class": "anticoagulant",
            "calculation_type": "dual_criteria_reduction",
            "rule_body": {
                "standard_dose": {"value": 5, "unit": "mg", "frequency": "twice daily"},
                "reduced_dose": {"value": 2.5, "unit": "mg", "frequency": "twice daily"},
            },
        }
    ]
    rules = _rows_to_rules(rows)
    assert rules[0]["rule_id"] == "apixaban_af_dose_reduction"
    assert rules[0]["_db_version"] == 2


def test_fallback_bundle_loads_bundled_rules(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.modules.dose_calculator.rule_loader.read_approved_dose_rules",
        lambda: [],
    )
    invalidate_dose_rules_cache()
    bundle = load_dose_rules_bundle()
    assert bundle["rules"]
    assert any(rule["rule_id"] == "apixaban_af_dose_reduction" for rule in bundle["rules"])
