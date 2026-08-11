from datetime import datetime, timezone

from app.core.config import settings
from app.modules.chat import service as chat_service
from app.modules.chat.clinical_state import build_clinical_state
from app.modules.clinical_intake_extraction.semantic import aggregate_conversation_context
from app.schemas.chat import ChatMessage
from app.schemas.patient import PatientProfile


def _minimal_patient() -> PatientProfile:
    return PatientProfile.model_validate(
        {
            "patient_identity": {"case_id": "follow_up_case"},
            "heart_failure_profile": {"lvef": {"value": 28}},
            "labs": {"egfr": {"value": 42}, "potassium": {"value": 4.8}},
            "vitals": {"systolic_bp": {"value": 108}, "heart_rate": {"value": 72}},
        }
    )


def test_follow_up_intent_requires_prior_assistant_message() -> None:
    patient = _minimal_patient()
    message = "SGLT2i chi tiet hon duoc khong?"
    assert build_clinical_state(patient, message, has_prior_assistant=False)["intent"] != "follow_up_detail"
    assert (
        build_clinical_state(patient, message, has_prior_assistant=True)["intent"] == "follow_up_detail"
    )


def test_conversation_context_includes_last_assistant_on_follow_up(monkeypatch) -> None:
    monkeypatch.setattr(settings, "clinical_intake_semantic_enabled", False)
    monkeypatch.setattr(settings, "clinical_intake_history_enabled", True)

    conversation_id = "conv-follow-up-ctx"
    prior_answer = "MRA trang thai review. SGLT2i trang thai consider."
    chat_service._messages[conversation_id] = [
        ChatMessage(
            message_id="u1",
            conversation_id=conversation_id,
            role="user",
            content="Co nen tang MRA hoac bat dau dapagliflozin?",
            created_at=datetime.now(timezone.utc),
        ),
        ChatMessage(
            message_id="a1",
            conversation_id=conversation_id,
            role="assistant",
            content=prior_answer,
            created_at=datetime.now(timezone.utc),
        ),
        ChatMessage(
            message_id="u2",
            conversation_id=conversation_id,
            role="user",
            content="SGLT2i chi tiet hon duoc khong?",
            created_at=datetime.now(timezone.utc),
        ),
    ]
    clinical_state = {"intent": "follow_up_detail", "focus_medication_classes": ["sglt2i"]}
    context = chat_service._conversation_context_for_llm(
        "SGLT2i chi tiet hon duoc khong?",
        conversation_id,
        clinical_state=clinical_state,
    )
    assert "[Your previous answer]" in context
    assert prior_answer in context
    assert "[Current] SGLT2i chi tiet hon duoc khong?" in context


def test_aggregate_conversation_context_previous_answer_only(monkeypatch) -> None:
    monkeypatch.setattr(settings, "clinical_intake_history_enabled", True)
    monkeypatch.setattr(settings, "clinical_intake_semantic_enabled", False)

    text = aggregate_conversation_context(
        "Giai thich them ve SGLT2i",
        [],
        last_assistant_message="Ban da noi consider cho SGLT2i.",
    )
    assert "[Your previous answer]" in text
    assert "consider cho SGLT2i" in text
    assert "[Current] Giai thich them ve SGLT2i" in text


def test_follow_up_focus_includes_prior_assistant_class() -> None:
    """User asks about SGLT2i deeper; prior assistant text mentioned MRA —
    focus_medication_classes should contain both, so LLM can route context."""
    patient = _minimal_patient()
    state = build_clinical_state(
        patient,
        "SGLT2i chi tiet hon duoc khong?",
        has_prior_assistant=True,
        last_assistant_message="MRA trang thai review cho can than K+.",
    )
    assert state["focus_medication_classes"] == ["mra", "sglt2i"]


def test_follow_up_focus_omits_assistant_when_no_prior() -> None:
    """Without has_prior_assistant, do not leak prior focus into state."""
    patient = _minimal_patient()
    state = build_clinical_state(
        patient,
        "SGLT2i chi tiet hon duoc khong?",
        has_prior_assistant=False,
        last_assistant_message="MRA trang thai review cho can than K+.",
    )
    assert "mra" not in state["focus_medication_classes"]
    assert "sglt2i" in state["focus_medication_classes"]


def test_detect_multi_question_splits_correctly() -> None:
    from app.modules.clinical_intake_extraction.semantic import detect_multi_question

    qs = detect_multi_question("MRA or SGLT2i? What about ARNI?")
    assert len(qs) == 2
    assert "MRA or SGLT2i" in qs[0]
    assert "ARNI" in qs[1]


def test_detect_multi_question_single_returns_unchanged() -> None:
    from app.modules.clinical_intake_extraction.semantic import detect_multi_question

    qs = detect_multi_question("MRA or SGLT2i?")
    assert len(qs) == 1
    assert qs[0] == "MRA or SGLT2i?"


def test_embed_documents_caches_per_text(monkeypatch) -> None:
    """Repeated prior messages should hit the per-text cache, not re-embed.

    ``embed_documents`` now routes each text through ``_embed_query_cached``,
    which carries an ``lru_cache``. We replace ``_embed_query_cached`` with a
    real ``lru_cache``-wrapped stub so the cache behavior is observable in
    a deterministic way without Ollama.
    """
    import app.modules.semantic_retrieval.service as retrieval_service
    from functools import lru_cache

    monkeypatch.setattr(settings, "clinical_intake_history_enabled", True)
    monkeypatch.setattr(settings, "clinical_intake_semantic_enabled", True)

    @lru_cache(maxsize=128)
    def fake_cached(normalized: str) -> tuple[float, ...]:
        return (0.0, 0.0)

    fake_cached.cache_clear()
    monkeypatch.setattr(retrieval_service, "_embed_query_cached", fake_cached)

    prior = ["MRA status review", "SGLT2i consider"]
    aggregate_conversation_context("Dapagliflozin chi tiet hon?", prior)
    info_after_first = fake_cached.cache_info()
    aggregate_conversation_context("Dapagliflozin chi tiet hon?", prior)
    info_after_second = fake_cached.cache_info()

    # Each prior text was embedded once, then every subsequent call hits cache.
    new_misses = info_after_second.misses - info_after_first.misses
    new_hits = info_after_second.hits - info_after_first.hits
    assert new_misses == 0, f"expected 0 misses on second call, got {new_misses}"
    assert new_hits >= len(prior), (
        f"expected >= {len(prior)} cache hits, got {new_hits}"
    )
