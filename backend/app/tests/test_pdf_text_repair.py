from scraper.transform.extract_important_sections import GUIDELINE_TOPICS, guideline_matches
from scraper.transform.text_normalization import repair_pdf_flow_text


def test_repair_pdf_flow_glues_common_medical_words() -> None:
    raw = (
        "Monitor eGFR30 and potassium in patientswithHFrEFand CKD. "
        "Start at 25mg daily when SBP is 110mmHg. "
        "Avoid peoplewithCKD orCKD progression. Level is 5.5mmol/Lis high."
    )
    fixed = repair_pdf_flow_text(raw)

    assert "patients with" in fixed
    assert "HFrEF and" in fixed
    assert "with CKD" in fixed or "or CKD" in fixed
    assert "eGFR 30" in fixed
    assert "25 mg" in fixed
    assert "110 mmHg" in fixed
    assert "mmol/L is" in fixed
    # Must not break camel-free clinical acronyms
    assert "H Fr EF" not in fixed
    assert "HFrEF" in fixed


def test_repair_pdf_flow_preserves_hfref_token() -> None:
    assert repair_pdf_flow_text("Initiate GDMT in HFrEF patients.") == "Initiate GDMT in HFrEF patients."


def test_guideline_topics_match_dosing_and_monitoring() -> None:
    assert "dosing" in GUIDELINE_TOPICS
    assert "monitoring" in GUIDELINE_TOPICS
    assert "drug interactions" in GUIDELINE_TOPICS
    assert "warnings" in GUIDELINE_TOPICS

    dosing = guideline_matches(
        {
            "section": "Pharmacologic Therapy",
            "text": "Target dose titration of beta blockers should be individualized.",
        }
    )
    assert "dosing" in dosing

    monitoring = guideline_matches(
        {
            "section": "Follow-up",
            "text": "Laboratory monitoring of renal function is recommended after initiation.",
        }
    )
    assert "monitoring" in monitoring

    interactions = guideline_matches(
        {
            "section": "Safety",
            "text": "Clinically relevant drug-drug interactions may occur with concomitant use.",
        }
    )
    assert "drug interactions" in interactions
