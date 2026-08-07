"""Tests for heuristic auto-judge (no LLM required)."""

from __future__ import annotations

from scraper.eval.auto_judge import aggregate_auto_metrics, heuristic_verdict, judge_claim


def test_rejects_author_noise():
    claim = {
        "claim_type": "population_constraint",
        "drug": "aspirin",
        "source_type": "guideline",
        "evidence": (
            "Williams Sr, MD, MACC, FAHA, Joseph Yeboah, MD, MS, FACC, FAHA, "
            "Boback Ziaeian, MD, PhD, FACC, FAHA and the American Association."
        ),
    }
    result = heuristic_verdict(claim)
    assert result["verdict"] == "reject"
    assert "heuristic_noise" in result["reasons"]


def test_accepts_clean_contraindication():
    claim = {
        "claim_type": "contraindication",
        "drug": "sacubitril_valsartan",
        "source_type": "drug_label",
        "evidence": "Do not administer ENTRESTO within 36 hours of switching from or to an ACE inhibitor.",
    }
    result = judge_claim(claim, use_llm=False)
    assert result["verdict"] == "accept"


def test_rejects_weak_see_contraindications():
    claim = {
        "claim_type": "contraindication",
        "drug": "dofetilide",
        "source_type": "drug_label",
        "evidence": "Patients with severe renal impairment were not included in clinical studies (see CONTRAINDICATIONS).",
    }
    result = judge_claim(claim, use_llm=False)
    assert result["verdict"] == "reject"
    assert "weak_span" in result["reasons"]


def test_normalize_overrides_junk_reject():
    from scraper.eval.auto_judge import _normalize_llm_result

    claim = {
        "claim_type": "contraindication",
        "drug": "enalapril",
        "evidence": "Enalapril maleate is contraindicated in combination with a neprilysin inhibitor.",
    }
    fixed = _normalize_llm_result(
        {"verdict": "reject", "reasons": ["contraindication"], "confidence": 0.9},
        claim,
    )
    assert fixed["verdict"] == "accept"


def test_aggregate_precision():
    rows = [
        {"verdict": "accept", "claim_type": "contraindication", "reasons": []},
        {"verdict": "reject", "claim_type": "contraindication", "reasons": ["heuristic_noise"]},
        {"verdict": "accept", "claim_type": "dose_recommendation", "reasons": []},
    ]
    metrics = aggregate_auto_metrics(rows)
    assert metrics["n"] == 3
    assert metrics["estimated_precision"] == 0.6667
    assert metrics["hard_types"]["n"] == 2
