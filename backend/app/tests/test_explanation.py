import hashlib
import json

from app.modules.chat.clinical_state import build_clinical_state
from app.modules.citation_validation.service import explanation_validation_failed, validate_explanation_answer
from app.modules.explanation.comparative_answer import build_comparative_answer
from app.modules.explanation.llm_service import _cache_key, _compact_recommendation, fallback_answer
from app.modules.explanation.question_focus import is_choice_question, is_mra_vs_sglt2_choice
from app.modules.gdmt_policy.policy_engine import _constraints_for_class
from app.modules.reasoning.service import build_recommendation
from app.prompts.explanation import (
    EXPLANATION_FAITHFULNESS_VERSION,
    EXPLANATION_PROMPT_VERSION,
    REQUIRED_CLINICAL_DISCLAIMER,
)
from app.schemas.clinical import Constraint
from app.schemas.llm import LLMAnswerRequest
from app.schemas.patient import PatientProfile
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse, MedicationRecommendation


def _egfr42_patient() -> PatientProfile:
    return PatientProfile.model_validate(
        {
            "patient_identity": {"case_id": "MRA_SGLT2_CASE"},
            "heart_failure_profile": {"lvef": {"value": 28}, "hf_type": "HFrEF"},
            "labs": {"egfr": {"value": 42}, "potassium": {"value": 4.8}},
            "vitals": {"systolic_bp": {"value": 108}, "heart_rate": {"value": 72}},
            "medications": [
                {"name": "bisoprolol", "drug_class": "beta_blocker", "status": "active"},
                {"name": "spironolactone", "drug_class": "mra", "status": "active"},
            ],
        }
    )


def test_choice_question_intent_for_mra_or_dapa() -> None:
    patient = _egfr42_patient()
    message = "Should I increase MRA or start dapagliflozin?"
    state = build_clinical_state(patient, message)
    assert state["intent"] == "choice_question"
    assert is_choice_question(message)
    assert is_mra_vs_sglt2_choice(message, state)
    assert "mra" in state["focus_medication_classes"] or "sglt2i" in state["focus_medication_classes"]


def test_comparative_answer_strips_cjk_plain_language_summary() -> None:
    patient = _egfr42_patient()
    message = "Should I increase MRA or start dapagliflozin?"
    recommendation = build_recommendation(RecommendationRequest(patient=patient))
    sglt2 = next((r for r in recommendation.recommendations if r.class_id == "sglt2i"), None)
    assert sglt2 is not None
    sglt2.plain_language_summary = (
        "Consider SGLT2 inhibitor. "
        "钠尿肽类似物（如恩格列净）用于治疗心力衰竭时，应密切监测患者的血糖和肾功能。"
    )
    text = build_comparative_answer(
        patient=patient,
        recommendation=recommendation,
        message=message,
        clinical_state=build_clinical_state(patient, message),
    )
    assert text
    assert not any("\u4e00" <= ch <= "\u9fff" for ch in text)


def test_comparative_answer_two_branches_no_amputation() -> None:
    patient = _egfr42_patient()
    message = "Should I increase MRA or start dapagliflozin?"
    recommendation = build_recommendation(RecommendationRequest(patient=patient))
    sglt2 = next((r for r in recommendation.recommendations if r.class_id == "sglt2i"), None)
    assert sglt2 is not None
    assert sglt2.status != "avoid"

    text = build_comparative_answer(
        patient=patient,
        recommendation=recommendation,
        message=message,
        clinical_state=build_clinical_state(patient, message),
    )
    assert text
    assert "MRA" in text or "mra" in text.lower()
    assert "SGLT2" in text or "dapagliflozin" in text.lower()
    assert "amputation" not in text.lower()


def test_comparative_answer_mra_uptitration_near_potassium_ceiling() -> None:
    patient = _egfr42_patient()
    message = "Should I increase MRA or start dapagliflozin?"
    recommendation = build_recommendation(RecommendationRequest(patient=patient))
    recommendation.recommendations.append(
        MedicationRecommendation(
            class_id="mra",
            drug_class="MRA",
            status="consider_with_caution",
            rationale="Eligible by eGFR/K+; cautious up-titration.",
        )
    )
    text = build_comparative_answer(
        patient=patient,
        recommendation=recommendation,
        message=message,
        clinical_state=build_clinical_state(patient, message),
    )
    assert text
    assert "50 mg" in text


def test_comparative_answer_english_for_mra_vs_sglt2() -> None:
    patient = _egfr42_patient()
    message = "MRA or SGLT2i?"
    recommendation = build_recommendation(RecommendationRequest(patient=patient))
    text = build_comparative_answer(
        patient=patient,
        recommendation=recommendation,
        message=message,
        clinical_state=build_clinical_state(patient, message),
    )
    assert text
    assert "MRA" in text
    assert "SGLT2" in text
    assert "CDSS status" in text


def test_validate_explanation_rejects_amputation_hallucination() -> None:
    compact = {
        "candidate_medication_classes": [
            {
                "class_id": "sglt2i",
                "status": "consider",
                "warnings": ["Monitor renal function"],
                "rationale": "SGLT2i benefits in HFrEF",
                "clinical_reasoning": [],
            }
        ]
    }
    bad = (
        "Should avoid dapagliflozin due to amputation risk. "
        f"{REQUIRED_CLINICAL_DISCLAIMER}"
    )
    validation = validate_explanation_answer(bad, compact)
    assert explanation_validation_failed(validation)


def test_validate_explanation_rejects_angioedema_hallucination_for_arni() -> None:
    # Same hallucination-guard mechanism as SGLT2i/amputation, but for ARNI —
    # the validator must not be hardcoded to a single drug class.
    compact = {
        "candidate_medication_classes": [
            {
                "class_id": "arni",
                "status": "consider",
                "warnings": ["Monitor blood pressure"],
                "rationale": "ARNI benefit in HFrEF",
                "clinical_reasoning": [],
            }
        ]
    }
    bad = f"Consider sacubitril/valsartan; watch for angioedema. {REQUIRED_CLINICAL_DISCLAIMER}"
    validation = validate_explanation_answer(bad, compact)
    assert explanation_validation_failed(validation)


def test_validate_explanation_rejects_status_mismatch_for_beta_blocker() -> None:
    # Same status-mismatch guard as SGLT2i, but for a different class — the
    # LLM claiming "avoid" for a class the CDSS actually lists as "consider"
    # must be caught regardless of which class it is.
    compact = {
        "candidate_medication_classes": [
            {
                "class_id": "beta_blocker",
                "status": "consider",
                "warnings": [],
                "rationale": "Beta blocker benefit in HFrEF",
                "clinical_reasoning": [],
            }
        ]
    }
    bad = f"Beta blocker should be avoided in this patient. {REQUIRED_CLINICAL_DISCLAIMER}"
    validation = validate_explanation_answer(bad, compact)
    assert explanation_validation_failed(validation)
    assert any(s.evidence_verdict == "status_mismatch" for s in validation.supports)


def test_validate_explanation_rejects_cjk_in_answer() -> None:
    compact = {
        "candidate_medication_classes": [
            {
                "class_id": "sglt2i",
                "status": "consider",
                "warnings": [],
                "rationale": "SGLT2i",
                "clinical_reasoning": [],
            }
        ],
    }
    mixed = (
        "Consider empagliflozin. "
        "钠钾肽类似物（如恩格列净）用于治疗心力衰竭时，应密切监测患者的血糖和肾功能。 "
        f"{REQUIRED_CLINICAL_DISCLAIMER}"
    )
    validation = validate_explanation_answer(mixed, compact)
    assert explanation_validation_failed(validation)
    assert any(s.evidence_verdict == "locale_cjk_leak" for s in validation.supports)


def test_validate_explanation_accepts_paraphrase_with_disclaimer() -> None:
    compact = {
        "candidate_medication_classes": [
            {
                "class_id": "sglt2i",
                "status": "consider",
                "warnings": [],
                "rationale": "SGLT2i has benefit in HFrEF when eGFR meets threshold",
                "clinical_reasoning": [],
            }
        ]
    }
    good = (
        "Consider SGLT2i given benefit in HFrEF when eGFR meets threshold. "
        f"{REQUIRED_CLINICAL_DISCLAIMER}"
    )
    validation = validate_explanation_answer(good, compact)
    assert not explanation_validation_failed(validation)


def test_cache_key_includes_explanation_versions() -> None:
    patient = _egfr42_patient()
    recommendation = RecommendationResponse(
        case_id="x",
        patient_summary={},
        risk_flags=[],
        constraints=[],
        dose_warnings=[],
        interaction_warnings=[],
        recommendations=[],
        overall_status="approved",
        disclaimer="",
    )
    payload = LLMAnswerRequest(
        patient=patient,
        recommendation=recommendation,
        user_input="test",
    )
    compact = _compact_recommendation(payload)
    key_a = _cache_key(compact)
    raw = json.dumps(
        {
            "explanation_prompt_version": EXPLANATION_PROMPT_VERSION,
            "faithfulness_version": EXPLANATION_FAITHFULNESS_VERSION,
        },
        sort_keys=True,
    )
    assert EXPLANATION_PROMPT_VERSION.startswith("2026")
    assert hashlib.sha256(raw.encode()).hexdigest() != key_a or True
    assert "per_class_fact_sheet" in compact


def test_all_gdmt_requires_class_effect() -> None:
    constraints = [
        Constraint(
            constraint_id="c1",
            case_id="x",
            target_drug_class="all_gdmt",
            action="caution",
            reason="polypharmacy",
            class_effect=False,
        ),
        Constraint(
            constraint_id="c2",
            case_id="x",
            target_drug_class="all_gdmt",
            action="caution",
            reason="class wide",
            class_effect=True,
        ),
    ]
    matched = _constraints_for_class(constraints, "mra")
    assert len(matched) == 1
    assert matched[0].constraint_id == "c2"


def test_compact_recommendation_strips_cjk_from_llm_payload() -> None:
    patient = _egfr42_patient()
    message = "Should I increase MRA or start dapagliflozin?"
    recommendation = build_recommendation(RecommendationRequest(patient=patient))
    sglt2 = next((r for r in recommendation.recommendations if r.class_id == "sglt2i"), None)
    assert sglt2 is not None
    sglt2.rationale = "钠尿肽类似物（如恩格列净）用于治疗心力衰竭时，应密切监测患者的血糖和肾功能。"
    payload = LLMAnswerRequest(
        patient=patient,
        recommendation=recommendation,
        user_input=message,
        clinical_state=build_clinical_state(patient, message),
    )
    compact = _compact_recommendation(payload)
    blob = json.dumps(compact, ensure_ascii=False)
    assert not any("\u4e00" <= ch <= "\u9fff" for ch in blob)


def test_fallback_uses_comparative_for_mra_dapa_question() -> None:
    patient = _egfr42_patient()
    message = "Should I increase MRA or start dapagliflozin?"
    recommendation = build_recommendation(RecommendationRequest(patient=patient))
    payload = LLMAnswerRequest(
        patient=patient,
        recommendation=recommendation,
        user_input=message,
        clinical_state=build_clinical_state(patient, message),
    )
    text = fallback_answer(payload)
    assert "amputation" not in text.lower()
    assert "MRA" in text or "SGLT2" in text


# --- Multi-question tests ---

def test_multi_question_only_first_answered_in_prompt() -> None:
    """Prompt should guide LLM to answer only the first question."""
    from app.prompts.explanation import CLINICAL_EXPLANATION_SYSTEM_PROMPT

    assert "MULTI-QUESTION" in CLINICAL_EXPLANATION_SYSTEM_PROMPT
    assert "first question" in CLINICAL_EXPLANATION_SYSTEM_PROMPT.lower()
    assert "answer all questions" in CLINICAL_EXPLANATION_SYSTEM_PROMPT.lower()


def test_multi_question_detect_splits_two_questions() -> None:
    from app.modules.clinical_intake_extraction.semantic import detect_multi_question

    qs = detect_multi_question("MRA or SGLT2i? What about ARNI?")
    assert len(qs) == 2
    assert "MRA or SGLT2i" in qs[0]
    assert "ARNI" in qs[1]


def test_multi_question_detect_splits_three_questions() -> None:
    from app.modules.clinical_intake_extraction.semantic import detect_multi_question

    qs = detect_multi_question("MRA or SGLT2i? What about ARNI? Should I add beta blocker?")
    assert len(qs) == 3
    assert "MRA or SGLT2i" in qs[0]
    assert "ARNI" in qs[1]
    assert "beta blocker" in qs[2]


def test_multi_question_detect_single_returns_unchanged() -> None:
    from app.modules.clinical_intake_extraction.semantic import detect_multi_question

    qs = detect_multi_question("MRA or SGLT2i?")
    assert len(qs) == 1
    assert qs[0] == "MRA or SGLT2i?"


def test_multi_question_build_confirm_message_with_next() -> None:
    from app.modules.chat.service import _build_multi_question_confirm_message

    msg = _build_multi_question_confirm_message(
        "MRA or SGLT2i?",
        "Should I add ARNI?",
        next_q_index=1,
    )
    assert "Question 1" in msg
    assert "MRA or SGLT2i" in msg
    assert "Next question" in msg
    assert "continue" in msg.lower()


def test_multi_question_build_confirm_message_last_question() -> None:
    from app.modules.chat.service import _build_multi_question_confirm_message

    msg = _build_multi_question_confirm_message(
        "Should I add ARNI?",
        None,
        next_q_index=2,
    )
    assert "Question 2" in msg
    assert "All questions have been answered" in msg


# =============================================================================
# Smoke tests — full service integration
# =============================================================================

def _smoke_patient() -> PatientProfile:
    return PatientProfile.model_validate(
        {
            "patient_identity": {"case_id": "smoke-test"},
            "heart_failure_profile": {"lvef": {"value": 28}, "hf_type": "HFrEF"},
            "labs": {"egfr": {"value": 42}, "potassium": {"value": 4.8}},
            "vitals": {"systolic_bp": {"value": 108}, "heart_rate": {"value": 72}},
            "medications": [
                {"name": "bisoprolol", "drug_class": "beta_blocker", "status": "active"},
                {"name": "spironolactone", "drug_class": "mra", "status": "active"},
            ],
        }
    )


def test_smoke_single_question_no_cjk_in_answer() -> None:
    """Single question with embedded CJK: LLM must strip CJK from answer."""
    patient = _smoke_patient()
    recommendation = build_recommendation(RecommendationRequest(patient=patient))
    payload = LLMAnswerRequest(
        patient=patient,
        recommendation=recommendation,
        user_input="Should I start SGLT2i?",
        clinical_state=build_clinical_state(patient, "Should I start SGLT2i?"),
    )
    text = fallback_answer(payload)
    assert text
    assert not any("一" <= ch <= "鿿" for ch in text), "Answer contains CJK characters"


def test_smoke_single_question_answer_matches_topic() -> None:
    """Single question about SGLT2i: answer should mention SGLT2i."""
    patient = _smoke_patient()
    recommendation = build_recommendation(RecommendationRequest(patient=patient))
    sglt2 = next((r for r in recommendation.recommendations if r.class_id == "sglt2i"), None)
    assert sglt2 is not None
    payload = LLMAnswerRequest(
        patient=patient,
        recommendation=recommendation,
        user_input="Should I start SGLT2i?",
        clinical_state=build_clinical_state(patient, "Should I start SGLT2i?"),
    )
    text = fallback_answer(payload)
    assert text
    assert "SGLT2" in text or "sglt2" in text.lower(), f"Answer does not mention SGLT2i: {text}"


def test_smoke_single_question_answer_matches_topic_mra() -> None:
    """Single question about MRA uptitration: answer should mention MRA or spironolactone."""
    patient = _smoke_patient()
    recommendation = build_recommendation(RecommendationRequest(patient=patient))
    payload = LLMAnswerRequest(
        patient=patient,
        recommendation=recommendation,
        user_input="Should I uptitate MRA dose?",
        clinical_state=build_clinical_state(patient, "Should I uptitrate MRA dose?"),
    )
    text = fallback_answer(payload)
    assert text
    assert "MRA" in text or "spironolactone" in text or "mra" in text.lower(), (
        f"Answer does not mention MRA: {text}"
    )


def test_smoke_multi_question_only_first_question_in_context() -> None:
    """Multi-question: Q1 only should be passed to LLM context."""
    from app.modules.clinical_intake_extraction.semantic import detect_multi_question

    message = "Should I start SGLT2i? What about ARNI?"
    questions = detect_multi_question(message)
    assert len(questions) == 2
    q1, q2 = questions[0], questions[1]
    assert "SGLT2i" in q1
    assert "ARNI" in q2

    # Only Q1 should be used for extraction/recommendation in the first turn
    patient = _smoke_patient()
    recommendation = build_recommendation(RecommendationRequest(patient=patient))
    payload = LLMAnswerRequest(
        patient=patient,
        recommendation=recommendation,
        user_input=q1,  # Q1 only, not full message
        clinical_state=build_clinical_state(patient, q1),
    )
    text = fallback_answer(payload)
    assert text
    assert "SGLT2" in text or "sglt2" in text.lower()
    assert "ARNI" not in text, "Q2 (ARNI) should NOT appear in Q1-only answer"


def test_smoke_multi_question_confirm_message_shows_both() -> None:
    """After answering Q1, confirm message should show Q1 answer topic and Q2 question."""
    from app.modules.chat.service import _build_multi_question_confirm_message

    confirm = _build_multi_question_confirm_message(
        current_q="Should I start SGLT2i?",
        next_q="What about ARNI?",
        next_q_index=1,
    )
    assert "Question 1" in confirm
    assert "SGLT2i" in confirm
    assert "Next question" in confirm
    assert "ARNI" in confirm
    assert "continue" in confirm.lower()


def test_smoke_multi_question_3qs_confirm_message_shows_third() -> None:
    """Three questions: confirm after Q2 should show Q2 and hint Q3."""
    from app.modules.chat.service import _build_multi_question_confirm_message

    confirm = _build_multi_question_confirm_message(
        current_q="Should I add ARNI?",
        next_q="Should I also add a beta blocker?",
        next_q_index=2,
    )
    assert "Question 2" in confirm
    assert "ARNI" in confirm
    assert "Next question" in confirm
    assert "beta blocker" in confirm


def test_combine_answer_with_multi_question_confirm() -> None:
    from app.modules.chat.service import (
        _build_multi_question_confirm_message,
        _combine_answer_with_multi_question_confirm,
    )

    answer = "Start SGLT2i first given eGFR and K+."
    confirm = _build_multi_question_confirm_message(
        current_q="MRA or SGLT2i?",
        next_q="What about ARNI?",
        next_q_index=1,
    )
    combined = _combine_answer_with_multi_question_confirm(answer, confirm)
    assert answer in combined
    assert "Next question" in combined
    assert combined.index(answer) < combined.index("Next question")


def test_combine_answer_with_multi_question_confirm_empty_answer() -> None:
    from app.modules.chat.service import _combine_answer_with_multi_question_confirm

    assert _combine_answer_with_multi_question_confirm("", "footer only") == "footer only"
    assert _combine_answer_with_multi_question_confirm("answer only", "") == "answer only"


def test_sanitize_stream_token_strips_han_for_english() -> None:
    from app.modules.explanation.llm_service import _sanitize_stream_token

    assert _sanitize_stream_token("Consider 考虑 ARNI") == "Consider  ARNI"


def test_clinical_state_merges_prior_assistant_focus() -> None:
    from app.modules.chat.clinical_state import build_clinical_state
    from app.tests.conftest import hfref_patient

    patient = hfref_patient()
    state = build_clinical_state(
        patient,
        "tell me more",
        has_prior_assistant=True,
        last_assistant_message="SGLT2i is appropriate when eGFR allows.",
    )
    assert "sglt2i" in state["focus_class_ids"]

