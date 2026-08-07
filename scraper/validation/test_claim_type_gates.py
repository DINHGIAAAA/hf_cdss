"""Tests for balanced dose/renal claim quality gates."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scraper.validation.claim_type_gates import (
    is_actionable_dose_evidence,
    is_actionable_renal_evidence,
    passes_claim_type_gate,
)


def test_dose_accepts_hf_titration() -> None:
    ev = "For heart failure, start metoprolol succinate at 12.5 to 25 mg once daily."
    assert is_actionable_dose_evidence(ev) is True
    assert passes_claim_type_gate("dose_recommendation", ev) is True


def test_dose_rejects_missed_dose() -> None:
    ev = "Inform patients to take a missed dose as soon as possible."
    assert is_actionable_dose_evidence(ev) is False


def test_renal_accepts_numeric_egfr() -> None:
    ev = "Do not initiate when eGFR is less than 30 mL/min/1.73 m2."
    assert is_actionable_renal_evidence(ev) is True


def test_renal_accepts_action_without_number() -> None:
    ev = "Avoid use in patients with severe renal impairment requiring dialysis."
    assert is_actionable_renal_evidence(ev) is True


def test_renal_rejects_pk_demographics() -> None:
    ev = "No clinically significant difference in pharmacokinetics was observed in geriatric patients."
    assert is_actionable_renal_evidence(ev) is False


def test_renal_accepts_gfr_with_trailing_cross_ref() -> None:
    ev = (
        "Avoid use of aliskiren in patients with renal impairment (GFR <60 mL/min) "
        "[see Warnings and Precautions (5.4)]."
    )
    assert is_actionable_renal_evidence(ev) is True
