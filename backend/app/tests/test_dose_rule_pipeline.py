import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.process.classify_dose_rules import classify_dose_rules, dose_rule_tier
from scraper.semantic.dose_rule_builder import build_dose_rule_from_claim, dose_rules_from_claims


def _structured_apixaban_claim() -> dict:
    return {
        "claim_id": "dose_claim_test_apixaban",
        "claim_type": "structured_dose_rule",
        "document_id": "apixaban",
        "source_type": "drug_label",
        "drug": "apixaban",
        "drug_class": "anticoagulant",
        "drug_keys": ["apixaban"],
        "calculation_type": "dual_criteria_reduction",
        "standard_dose": {"value": 5, "unit": "mg", "frequency": "twice daily"},
        "reduced_dose": {"value": 2.5, "unit": "mg", "frequency": "twice daily"},
        "reduction_criteria": [
            {"field": "age", "operator": "gte", "value": 80, "label": "age >= 80 years"},
            {"field": "weight_kg", "operator": "lte", "value": 60, "label": "weight <= 60 kg"},
            {"field": "creatinine", "operator": "gte", "value": 1.5, "label": "serum creatinine >= 1.5 mg/dL"},
        ],
        "reduction_min_matches": 2,
        "evidence": "Reduce dose to 2.5 mg twice daily when at least two of age >=80, weight <=60 kg, or creatinine >=1.5 mg/dL are present.",
        "confidence": 0.92,
        "metadata": {"extraction_method": "llm_structured_dose"},
    }


def test_build_dose_rule_from_structured_claim() -> None:
    rule = build_dose_rule_from_claim(_structured_apixaban_claim())
    assert rule is not None
    assert rule["calculation_type"] == "dual_criteria_reduction"
    assert rule["standard_dose"]["value"] == 5
    assert len(rule["reduction_criteria"]) == 3


def test_classify_structured_dose_rule_as_usable() -> None:
    rule = build_dose_rule_from_claim(_structured_apixaban_claim())
    assert rule is not None
    classified = classify_dose_rules([rule])[0]
    assert classified["safety_tier"] == "usable_rules"


def test_reject_incomplete_structured_dose_rule() -> None:
    claim = _structured_apixaban_claim()
    claim.pop("standard_dose")
    rule = build_dose_rule_from_claim(claim)
    assert rule is None


def test_dose_rule_tier_marks_low_confidence_for_refinement() -> None:
    rule = build_dose_rule_from_claim(_structured_apixaban_claim())
    assert rule is not None
    rule["source_confidence"] = 0.55
    assert dose_rule_tier(rule) == "needs_refinement"


def test_dose_rules_from_claims_deduplicates() -> None:
    claim = _structured_apixaban_claim()
    rules = dose_rules_from_claims([claim, dict(claim)])
    assert len(rules) == 1
