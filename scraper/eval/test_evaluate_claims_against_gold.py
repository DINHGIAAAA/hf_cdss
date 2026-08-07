"""Unit tests for gold claim evaluation matching."""

from __future__ import annotations

from scraper.eval.evaluate_claims_against_gold import compute_metrics, match_predictions_to_gold


def test_positive_match_and_noise_trap():
    gold = [
        {
            "gold_id": "g1",
            "label": "should_extract",
            "claim_type": "contraindication",
            "drug": "entresto",
            "evidence": "Do not administer ENTRESTO within 36 hours of an ACE inhibitor.",
            "document_id": "entresto",
            "safety_tier": "hard_block",
        },
        {
            "gold_id": "g2",
            "label": "invalid_extraction",
            "claim_type": None,
            "drug": None,
            "evidence": "Keywords: guidelines; aspirin; atrial fibrillation.",
            "document_id": "guide_x",
            "safety_tier": "informational",
        },
    ]
    preds = [
        {
            "claim_id": "c1",
            "claim_type": "contraindication",
            "drug": "entresto",
            "evidence": "Do not administer ENTRESTO within 36 hours of switching from an ACE inhibitor.",
            "document_id": "entresto",
            "claim": "Do not administer ENTRESTO within 36 hours of switching from an ACE inhibitor.",
        },
        {
            "claim_id": "c2",
            "claim_type": "population_constraint",
            "drug": "aspirin",
            "evidence": "Keywords: guidelines; aspirin; atrial fibrillation.",
            "document_id": "guide_x",
            "claim": "Keywords: guidelines; aspirin; atrial fibrillation.",
        },
    ]
    results = match_predictions_to_gold(gold, preds, min_similarity=0.4)
    metrics = compute_metrics(results)
    assert metrics["overall"]["tp"] == 1
    assert metrics["overall"]["fp"] == 1
    assert metrics["noise_trap_hits"] == 1
    assert results[0].matched is True
