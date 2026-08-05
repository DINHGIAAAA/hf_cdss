"""Tests for GDMT policy claim extraction edge cases."""

from scraper.semantic.gdmt_policy_claim_extraction import extract_structured_gdmt_policies_from_section


def test_extract_handles_guidance_list_in_policy_body(monkeypatch) -> None:
    def fake_llm(*_args, **_kwargs):
        return {
            "gdmt_policies": [
                {
                    "drug_class_key": "MRA",
                    "display_label": "MRA",
                    "policy_body": {
                        "guidance": [{"actions": "Check potassium", "monitoring": "K+"}],
                        "hfref_default_status": "consider",
                    },
                    "confidence": 0.8,
                }
            ]
        }

    monkeypatch.setattr(
        "scraper.semantic.gdmt_policy_claim_extraction.call_llm_json",
        fake_llm,
    )
    record = {
        "document_id": "test_doc",
        "section": "GDMT recommendations",
        "source_type": "guideline",
        "text": "Guideline-directed medical therapy with MRA is recommended for HFrEF patients.",
    }
    claims = extract_structured_gdmt_policies_from_section(record)
    assert len(claims) == 1
    assert claims[0]["drug_class_key"] == "MRA"
    assert claims[0]["policy_body"]["guidance"]["actions"] == ["Check potassium"]
