from app.modules.recommendation.drug_class_keys import (
    is_placeholder_drug_label,
    stabilize_recommendation_items,
)
from app.schemas.recommendation import MedicationRecommendation


def test_placeholder_labels_are_detected() -> None:
    assert is_placeholder_drug_label("Human-readable class label")
    assert is_placeholder_drug_label("Stable drug class label")
    assert not is_placeholder_drug_label("ACEi/ARB")


def test_stabilize_assigns_class_id_and_dedupes() -> None:
    items = [
        MedicationRecommendation(
            class_id="acei_arb",
            drug_class="ACEI/ARB",
            status="consider",
            rationale="one",
        ),
        MedicationRecommendation(
            class_id="mra",
            drug_class="MRA",
            status="continue",
            rationale="two",
        ),
        MedicationRecommendation(
            class_id="acei_arb",
            drug_class="ACE inhibitors and ARBs",
            status="avoid",
            rationale="duplicate class",
        ),
    ]
    out = stabilize_recommendation_items(items)
    class_ids = [item.class_id for item in out]
    assert "mra" in class_ids
    assert "acei_arb" in class_ids
    assert len(out) == 2
