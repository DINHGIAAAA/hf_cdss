import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.semantic.gdmt_policy_builder import gdmt_policies_from_claims


def test_gdmt_policies_from_claims_includes_bundled_baseline() -> None:
    policies = gdmt_policies_from_claims([])
    assert len(policies) == 4
    keys = {item["drug_class_key"] for item in policies}
    assert keys == {"ARNI/ACEi/ARB", "beta_blocker", "MRA", "SGLT2i"}


def test_gdmt_policies_from_claims_merges_pipeline_claim() -> None:
    claim = {
        "claim_type": "structured_gdmt_policy",
        "drug_class_key": "MRA",
        "display_label": "Mineralocorticoid receptor antagonist",
        "sort_order": 3,
        "policy_body": {
            "guidance": {
                "reasoning_base": ["Updated MRA guidance from pipeline."],
                "actions": ["Check potassium before initiation."],
                "monitoring": ["Potassium"],
            }
        },
        "evidence_ref": "claim:test_mra",
    }
    policies = gdmt_policies_from_claims([claim])
    mra = next(item for item in policies if item["drug_class_key"] == "MRA")
    guidance = mra["policy_body"]["guidance"]
    assert "Updated MRA guidance from pipeline." in guidance["reasoning_base"]
    assert "Check potassium before initiation." in guidance["actions"]
