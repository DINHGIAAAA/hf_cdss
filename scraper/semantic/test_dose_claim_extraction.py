"""Unit tests for dose-relevant section filtering."""

from __future__ import annotations

from scraper.semantic.dose_claim_extraction import is_dose_relevant_section


def test_drug_label_clinical_studies_section_is_not_dose_relevant():
    # Regression: "CLINICAL STUDIES / ATRIAL FIBRILLATION" mentions "warfarin"
    # throughout while describing trial efficacy, not dosing — feeding it to
    # the LLM extractor produced hallucinated dose criteria in production.
    record = {
        "source_type": "drug_label",
        "section": "CLINICAL STUDIES / ATRIAL FIBRILLATION",
        "text": (
            "In five randomized trials comparing warfarin to placebo or no "
            "treatment, warfarin reduced the risk of stroke in patients with "
            "nonvalvular atrial fibrillation. Warfarin was superior to "
            "placebo across all five trials."
        ),
    }
    assert is_dose_relevant_section(record) is False


def test_drug_label_dosage_section_is_dose_relevant():
    record = {
        "source_type": "drug_label",
        "section": "DOSAGE AND ADMINISTRATION",
        "text": "The recommended starting dose is 2 mg once daily.",
    }
    assert is_dose_relevant_section(record) is True


def test_non_label_source_keeps_drug_name_fallback():
    # Guideline text has no clean FDA section title to lean on, so the bare
    # drug-name-mention fallback still applies there.
    record = {
        "source_type": "guideline_html",
        "section": "Anticoagulation recommendations",
        "text": "Warfarin is recommended for patients with mechanical valves.",
    }
    assert is_dose_relevant_section(record) is True
