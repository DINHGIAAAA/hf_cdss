import pytest

from app.modules.explanation.card_summarizer import (
    apply_deterministic_summaries,
    attach_plain_language_summaries,
    deterministic_card_summary,
    merge_summaries,
    parse_summary_map,
)
from app.modules.explanation.llm_service import _compact_recommendation, fallback_answer
from app.prompts.explanation import CLINICAL_EXPLANATION_SYSTEM_PROMPT
from app.schemas.llm import LLMAnswerRequest
from app.schemas.patient import PatientProfile
from app.schemas.recommendation import MedicationRecommendation, RecommendationResponse


def _item(**overrides) -> MedicationRecommendation:
    base = {
        "drug_class": "RAAS inhibition / ARNI",
        "status": "consider",
        "rationale": "No clear current ARNI/ACEi/ARB therapy detected.",
        "clinical_reasoning": [
            "Core disease-modifying therapy for HFrEF",
            "This patient context is LVEF 30% eGFR 55 K+ 4.2 mmol/L SBP 118 mmHg",
        ],
        "action_items": ["If clinically stable, consider low-dose initiation."],
        "monitoring": ["Creatinine/eGFR and potassium within 1-2 weeks"],
        "warnings": [],
    }
    base.update(overrides)
    return MedicationRecommendation(**base)


def _recommendation(items: list[MedicationRecommendation] | None = None) -> RecommendationResponse:
    return RecommendationResponse(
        case_id="CASE1",
        patient_summary={"hf_type": "HFrEF"},
        risk_flags=[],
        recommendations=items or [_item()],
        overall_status="consider",
        disclaimer="demo",
    )


def test_deterministic_card_summary_vietnamese() -> None:
    text = deterministic_card_summary(_item(), language="vi")
    assert "chưa thấy" in text.lower() or "cân nhắc" in text.lower()
    assert "ARNI" in text or "RAAS" in text
    assert "No clear current" not in text


def test_deterministic_card_details_vietnamese() -> None:
    from app.modules.explanation.card_summarizer import deterministic_card_details

    details = deterministic_card_details(_item(), language="vi")
    assert details.reasoning
    assert all("disease-modifying" not in line.lower() for line in details.reasoning)
    assert details.next_steps
    assert all(_looks_like_vietnamese_or_plain(line) for line in details.next_steps)


def _looks_like_vietnamese_or_plain(line: str) -> bool:
    lowered = line.lower()
    return "clinically stable" not in lowered and "consider low-dose" not in lowered


def test_parse_summary_map_ignores_unknown_classes() -> None:
    raw = json_dumps(
        {
            "summaries": [
                {"drug_class": "RAAS inhibition / ARNI", "summary": "Có thể cân nhắc ARNI."},
                {"drug_class": "Invented class", "summary": "should ignore"},
                {"drug_class": "Evidence-based beta blocker", "summary": ""},
            ]
        }
    )
    mapping = parse_summary_map(raw, ["RAAS inhibition / ARNI", "Evidence-based beta blocker"])
    assert mapping == {"RAAS inhibition / ARNI": "Có thể cân nhắc ARNI."}


def test_merge_summaries_falls_back_per_item() -> None:
    rec = _recommendation(
        [
            _item(),
            _item(drug_class="Evidence-based beta blocker", rationale="No beta blocker detected."),
        ]
    )
    merged = merge_summaries(rec, {"RAAS inhibition / ARNI": "Tóm tắt LLM cho ARNI."}, language="vi")
    assert merged.recommendations[0].plain_language_summary == "Tóm tắt LLM cho ARNI."
    assert merged.recommendations[1].plain_language_summary
    assert "beta blocker" in merged.recommendations[1].plain_language_summary.lower()


@pytest.mark.asyncio
async def test_attach_summaries_uses_fallback_when_llm_disabled(monkeypatch) -> None:
    from app.modules.explanation import card_summarizer

    monkeypatch.setattr(card_summarizer, "llm_chat_completions_enabled", lambda: False)
    result = await attach_plain_language_summaries(_recommendation(), language="vi")
    assert result.recommendations[0].plain_language_summary
    assert "ARNI" in result.recommendations[0].plain_language_summary or "RAAS" in result.recommendations[0].plain_language_summary


@pytest.mark.asyncio
async def test_attach_summaries_maps_llm_json(monkeypatch) -> None:
    from app.modules.explanation import card_summarizer

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json_dumps(
                                {
                                    "summaries": [
                                        {
                                            "drug_class": "RAAS inhibition / ARNI",
                                            "summary": "Có thể cân nhắc khởi trị ARNI liều thấp.",
                                        }
                                    ]
                                }
                            )
                        }
                    }
                ]
            }

    class FakeClient:
        async def post(self, *args, **kwargs):
            return FakeResponse()

    async def _none(*_args, **_kwargs):
        return None

    monkeypatch.setattr(card_summarizer, "llm_chat_completions_enabled", lambda: True)
    monkeypatch.setattr(card_summarizer, "get_async_client", lambda *args, **kwargs: FakeClient())
    monkeypatch.setattr(card_summarizer, "_read_cache", _none)
    monkeypatch.setattr(card_summarizer, "_write_cache", _none)

    result = await attach_plain_language_summaries(_recommendation(), language="vi")
    assert result.recommendations[0].plain_language_summary == "Có thể cân nhắc khởi trị ARNI liều thấp."


def test_compact_recommendation_includes_plain_language_summary() -> None:
    patient = PatientProfile(case_id="PL_CASE", lvef=30, egfr=55, potassium=4.2, systolic_bp=118, heart_rate=72)
    rec = apply_deterministic_summaries(_recommendation(), language="vi")
    payload = LLMAnswerRequest(
        user_input="Tóm tắt khuyến nghị",
        patient=patient,
        recommendation=rec,
        language="vi",
    )
    compact = _compact_recommendation(payload)
    assert compact["candidate_medication_classes"][0]["plain_language_summary"]


def test_fallback_answer_prefers_plain_language_summary() -> None:
    patient = PatientProfile(case_id="PL_FB", lvef=30, egfr=55, potassium=4.2, systolic_bp=118, heart_rate=72)
    item = _item(plain_language_summary="Có thể cân nhắc khởi trị ARNI.")
    rec = _recommendation([item])
    text = fallback_answer(
        LLMAnswerRequest(user_input="x", patient=patient, recommendation=rec, language="vi")
    )
    assert "Có thể cân nhắc khởi trị ARNI." in text


def test_explanation_prompt_keeps_contract() -> None:
    assert "Kết luận" in CLINICAL_EXPLANATION_SYSTEM_PROMPT
    assert "plain_language_summary" in CLINICAL_EXPLANATION_SYSTEM_PROMPT
    assert "soft-pedal" in CLINICAL_EXPLANATION_SYSTEM_PROMPT
    assert "Quyết định điều trị cuối cùng" in CLINICAL_EXPLANATION_SYSTEM_PROMPT


def json_dumps(value: dict) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)
