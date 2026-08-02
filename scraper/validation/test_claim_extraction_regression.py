"""Regression tests from auto_eval_20260731T082704Z reject patterns."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.process.create_claims import classify_claim, create_claim_regex, is_weak_span
from scraper.validation.claim_type_gates import (
    is_actionable_contraindication_evidence,
    is_actionable_guideline_evidence,
    is_actionable_hyperkalemia_evidence,
    is_actionable_renal_evidence,
    is_trial_pk_noise_span,
    passes_claim_type_gate_for_claim,
)


def test_rejects_spl_not_prescribed_boilerplate() -> None:
    ev = "Do not use tadalafil tablets for a condition for which it was not prescribed."
    assert is_actionable_contraindication_evidence(ev) is False
    assert classify_claim(ev, "drug_label") is None


def test_rejects_device_contraindication() -> None:
    ev = (
        "Do not use the on-body Infusor within 12 inches of mobile phones, "
        "tablets, computers or wireless accessories."
    )
    assert is_actionable_contraindication_evidence(ev) is False


def test_accepts_real_contraindication() -> None:
    ev = "Bosentan is contraindicated in patients who are hypersensitive to bosentan or any component of the product."
    assert is_actionable_contraindication_evidence(ev) is True
    assert classify_claim(ev, "drug_label") == "contraindication"


def test_rejects_credence_trial_as_renal() -> None:
    ev = (
        "Canagliflozin and Renal Events in Diabetes (CREDENCE), a placebo-controlled trial "
        "among 4,401 adults with type 2 diabetes, eGFR range 30–90 mL/min/1.73 m2."
    )
    assert is_actionable_renal_evidence(ev) is False
    assert classify_claim(ev, "drug_label") is None


def test_rejects_placebo_arm_as_dose() -> None:
    ev = "In these studies, a total of 6285 patients were randomized and treated, 3282 with MULTAQ 400 mg twice daily, and 2875 with placebo."
    assert is_trial_pk_noise_span(ev) is True
    assert classify_claim(ev, "drug_label") is None


def test_rejects_carvedilol_ae_laundry_hyperkalemia() -> None:
    ev = (
        "Metabolic and Nutritional Hyperuricemia, hypoglycemia, hyponatremia, "
        "hyperkalemia, creatinine increased."
    )
    assert is_actionable_hyperkalemia_evidence(ev) is False


def test_accepts_finerenone_potassium_threshold() -> None:
    ev = "If repeated serum potassium measurements are ≥5.5 mEq/L, restart Kerendia at 10 mg once daily when serum potassium < 5.0 mEq/L."
    assert is_actionable_hyperkalemia_evidence(ev) is True


def test_rejects_pad_guideline_without_hf_cue() -> None:
    ev = (
        "In patients with CLTI, surgical, endovascular, or hybrid revascularization "
        "techniques are recommended, when feasible, to minimize tissue loss."
    )
    assert is_actionable_guideline_evidence(ev, "acc_aha_2024_pad_guideline_pdf") is False


def test_accepts_hf_gdmt_guideline() -> None:
    ev = (
        "In patients with HFrEF, guideline-directed medical therapy with an ARNI, "
        "beta blocker, MRA, and SGLT2 inhibitor is recommended to reduce morbidity and mortality."
    )
    assert is_actionable_guideline_evidence(ev, "aha_acc_hfsa_2022_hf_guideline") is True


def test_classify_rejects_cross_ref_adr() -> None:
    ev = "See CLINICAL PHARMACOLOGY , Clinical Studies in Adolescent Patients ; ADVERSE REACTIONS , Adolescent Patients."
    assert is_weak_span(ev) is True


def test_passes_claim_gate_rejects_imaging_mra_drug_field() -> None:
    claim = {
        "claim_type": "contraindication",
        "drug": "mra",
        "document_id": "acc_aha_2024_pad_guideline_pdf",
        "evidence": (
            "Contrast-enhanced MRA uses gadolinium, certain formulations of which are "
            "contraindicated in patients with severe renal dysfunction."
        ),
    }
    assert passes_claim_type_gate_for_claim(claim) is False


def test_regex_claim_entresto_washout() -> None:
    record = {
        "document_id": "entresto_label",
        "source_type": "drug_label",
        "section": "CONTRAINDICATIONS",
        "text": "Do not administer ENTRESTO within 36 hours of switching from or to an ACE inhibitor.",
        "metadata": {"drug": "sacubitril_valsartan", "source_id": "entresto_label"},
    }
    claim = create_claim_regex(record, record["text"], 1)
    assert claim is not None
    assert claim["claim_type"] == "contraindication"
