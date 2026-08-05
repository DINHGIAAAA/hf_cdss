from app.modules.dose_calculation.governance_drug_adapter import approved_dose_rules_to_tables
from app.modules.dose_calculation.rule_loader import get_drug_by_key, invalidate_dose_tables_cache, load_dose_tables


def test_governance_adapter_maps_dual_criteria_reduction() -> None:
    row = {
        "dose_rule_id": "rule_apixaban_test",
        "drug_keys": ["apixaban"],
        "drug_class": "anticoagulant",
        "calculation_type": "dual_criteria_reduction",
        "rule_body": {
            "calculation_type": "dual_criteria_reduction",
            "drug_keys": ["apixaban"],
            "standard_dose": {"value": 5, "unit": "mg", "frequency": "twice daily"},
            "reduced_dose": {"value": 2.5, "unit": "mg", "frequency": "twice daily"},
            "reduction_criteria": [
                {"field": "age", "operator": "gte", "value": 80},
                {"field": "weight_kg", "operator": "lte", "value": 60},
            ],
            "reduction_min_matches": 2,
        },
    }
    tables = approved_dose_rules_to_tables([row], version="test", source="postgres")
    assert len(tables["drugs"]) == 1
    drug = tables["drugs"][0]
    assert drug["drug_key"] == "apixaban"
    assert drug["formulations"][0]["doses"][0]["dose_value"] == 5
    assert len(drug["multi_factor_adjustments"]) == 1
    assert drug["multi_factor_adjustments"][0]["min_matched"] == 2


def test_load_dose_tables_prefers_postgres_over_xml(monkeypatch) -> None:
    invalidate_dose_tables_cache()

    def _fake_postgres() -> dict:
        return approved_dose_rules_to_tables(
            [
                {
                    "dose_rule_id": "rule_spironolactone",
                    "drug_keys": ["spironolactone"],
                    "drug_class": "MRA",
                    "calculation_type": "fixed_dose",
                    "rule_body": {
                        "calculation_type": "fixed_dose",
                        "recommended_dose": {"value": 25, "unit": "mg", "frequency": "daily"},
                    },
                }
            ],
            version="postgres_approved_1",
            source="postgres_approved_dose_rules",
        )

    monkeypatch.setattr(
        "app.modules.dose_calculation.postgres_dose_loader.load_tables_from_postgres",
        _fake_postgres,
    )
    tables = load_dose_tables()
    assert tables["source"] == "postgres_approved_dose_rules"
    assert get_drug_by_key("spironolactone") is not None
    assert get_drug_by_key("spironolactone")["formulations"][0]["doses"][0]["dose_value"] == 25

    invalidate_dose_tables_cache()
