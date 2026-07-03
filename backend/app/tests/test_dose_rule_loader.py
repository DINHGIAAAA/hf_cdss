from app.modules.dose_calculator.rule_loader import _load_fallback_bundle, _rows_to_rules


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


def test_fallback_bundle_loads_bundled_rules() -> None:
    bundle = _load_fallback_bundle()
    assert bundle["rules"]
    assert any(rule["rule_id"] == "apixaban_af_dose_reduction" for rule in bundle["rules"])
