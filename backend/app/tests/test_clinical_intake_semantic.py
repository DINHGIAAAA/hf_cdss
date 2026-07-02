from app.core.config import settings
from app.modules.clinical_intake_extraction.semantic import (
    CatalogEntry,
    aggregate_conversation_context,
    semantic_catalog_matches,
    semantic_extract_patient,
)
from app.modules.clinical_intake_extraction.service import extract_patient_from_message


def test_aggregate_conversation_context_keeps_relevant_prior_turns(monkeypatch) -> None:
    monkeypatch.setattr(settings, "clinical_intake_semantic_enabled", True)
    monkeypatch.setattr(settings, "clinical_intake_history_enabled", True)
    monkeypatch.setattr(settings, "clinical_intake_history_relevance_threshold", 0.5)

    scores = {
        "EF 30 eGFR 55": 0.9,
        "Can danh gia GDMT": 0.8,
        "Benh nhan di du lich": 0.1,
        "Theo doi HA tai nha": 0.15,
    }

    def fake_embed_query(text: str) -> list[float]:
        score = scores.get(text, 0.2)
        return [score, 1.0 - score]

    monkeypatch.setattr(
        "app.modules.clinical_intake_extraction.semantic.embed_query",
        fake_embed_query,
    )

    aggregated = aggregate_conversation_context(
        "Can danh gia GDMT",
        ["EF 30 eGFR 55", "Benh nhan di du lich", "Theo doi HA tai nha"],
    )

    assert "[Current] Can danh gia GDMT" in aggregated
    assert "EF 30 eGFR 55" in aggregated
    assert "Benh nhan di du lich" not in aggregated


def test_semantic_catalog_match_adds_medication(monkeypatch) -> None:
    monkeypatch.setattr(settings, "clinical_intake_semantic_enabled", True)
    monkeypatch.setattr(settings, "clinical_intake_semantic_threshold", 0.4)

    entry = CatalogEntry(
        kind="medication",
        canonical_name="sacubitril/valsartan",
        label="sacubitril/valsartan; entresto",
        drug_class="arni",
        aliases=("entresto", "sacubitril valsartan"),
    )

    monkeypatch.setattr(
        "app.modules.clinical_intake_extraction.semantic._catalog_vectors",
        lambda: ([entry], [[1.0, 0.0]]),
    )
    monkeypatch.setattr(
        "app.modules.clinical_intake_extraction.semantic.embed_query",
        lambda text: [0.95, 0.05],
    )

    matches = semantic_catalog_matches("Patient is on Entresto 49/51 bid")
    assert matches
    assert matches[0].entry.canonical_name == "sacubitril/valsartan"

    patient = semantic_extract_patient("Patient is on Entresto 49/51 bid", "SEM_CASE")
    assert patient is not None
    assert "sacubitril/valsartan" in patient.current_medications
    assert patient.medications[0].source.source_type == "semantic_clinical_intake"


def test_extract_patient_uses_conversation_history_for_split_vitals(monkeypatch) -> None:
    monkeypatch.setattr(settings, "clinical_intake_semantic_enabled", False)
    monkeypatch.setattr(settings, "clinical_intake_history_enabled", True)
    monkeypatch.setattr(
        "app.modules.clinical_intake_extraction.service._call_llm_extractor",
        lambda message: None,
    )

    patient = extract_patient_from_message(
        "Can danh gia GDMT cho benh nhan HFrEF.",
        "HISTORY_CASE",
        conversation_history=["EF 30 eGFR 55 K 4.8 BP 110/70 HR 68"],
    )

    assert patient.lvef == 30
    assert patient.egfr == 55
    assert patient.potassium == 4.8
    assert patient.systolic_bp == 110
    assert patient.heart_rate == 68


def test_semantic_match_respects_negation(monkeypatch) -> None:
    monkeypatch.setattr(settings, "clinical_intake_semantic_enabled", True)
    monkeypatch.setattr(settings, "clinical_intake_semantic_threshold", 0.4)

    entry = CatalogEntry(
        kind="medication",
        canonical_name="spironolactone",
        label="spironolactone; aldactone",
        drug_class="mra",
        aliases=("spironolactone", "aldactone"),
    )
    monkeypatch.setattr(
        "app.modules.clinical_intake_extraction.semantic._catalog_vectors",
        lambda: ([entry], [[1.0]]),
    )
    monkeypatch.setattr(
        "app.modules.clinical_intake_extraction.semantic.embed_query",
        lambda text: [1.0],
    )

    matches = semantic_catalog_matches("No spironolactone, stable patient")
    assert matches == []
