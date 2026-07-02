from app.core.config import settings
from app.modules.explanation import llm_service
from app.modules.explanation.llm_service import _compact_recommendation
from app.schemas.llm import LLMAnswerRequest
from app.tests.conftest import api_path


def test_llm_answer_falls_back_when_ollama_unavailable(client) -> None:
    patient = {
        "case_id": "LLM_CASE",
        "lvef": 28,
        "egfr": 48,
        "potassium": 4.9,
        "systolic_bp": 88,
        "heart_rate": 54,
        "comorbidities": ["Atrial fibrillation"],
        "current_medications": ["metoprolol", "furosemide", "apixaban"],
        "allergies": [],
    }
    recommendation = client.post(api_path("/recommend"), json={"patient": patient}).json()
    verification = client.post(api_path("/verify"), json={"patient": patient, "recommendation": recommendation}).json()

    response = client.post(
        api_path("/llm/answer"),
        json={
            "user_input": "Patient has low blood pressure and bradycardia.",
            "patient": patient,
            "recommendation": recommendation,
            "verification": verification,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["case_id"] == "LLM_CASE"
    assert payload["answer"]
    assert "structured CDSS output" in payload["safety_note"]


def test_llm_answer_uses_cache_for_repeated_payload(monkeypatch, client) -> None:
    patient = {
        "case_id": "LLM_CACHE_CASE",
        "lvef": 28,
        "egfr": 48,
        "potassium": 4.9,
        "systolic_bp": 88,
        "heart_rate": 54,
        "comorbidities": ["Atrial fibrillation"],
        "current_medications": ["metoprolol", "furosemide", "apixaban"],
        "allergies": [],
    }
    recommendation = client.post(api_path("/recommend"), json={"patient": patient}).json()
    verification = client.post(api_path("/verify"), json={"patient": patient, "recommendation": recommendation}).json()
    body = {
        "user_input": "Patient has low blood pressure and bradycardia.",
        "patient": patient,
        "recommendation": recommendation,
        "verification": verification,
    }

    monkeypatch.setattr(settings, "llm_api_type", "chat_completions")
    monkeypatch.setattr(settings, "llm_base_url", "http://llm.test/v1")
    monkeypatch.setattr(settings, "llm_model", "cache-test-model")
    monkeypatch.setattr(settings, "llm_cache_enabled", True)
    if hasattr(llm_service.redis_client, "_values"):
        llm_service.redis_client._values.clear()
    calls = {"count": 0}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "Cached clinical explanation."}}]}

    class FakeClient:
        async def post(self, *args, **kwargs):
            calls["count"] += 1
            return FakeResponse()

    monkeypatch.setattr(llm_service, "get_async_client", lambda *args, **kwargs: FakeClient())

    first = client.post(api_path("/llm/answer"), json=body)
    second = client.post(api_path("/llm/answer"), json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["answer"] == "Cached clinical explanation."
    assert second.json()["answer"] == "Cached clinical explanation."
    assert calls["count"] == 1


def test_compact_recommendation_includes_conversation_context(client) -> None:
    patient = {
        "case_id": "CTX_CASE",
        "lvef": 28,
        "egfr": 48,
        "potassium": 4.9,
        "systolic_bp": 88,
        "heart_rate": 54,
        "comorbidities": ["Atrial fibrillation"],
        "current_medications": ["metoprolol"],
        "allergies": ["NKDA"],
    }
    recommendation = client.post(api_path("/recommend"), json={"patient": patient}).json()
    verification = client.post(api_path("/verify"), json={"patient": patient, "recommendation": recommendation}).json()

    compact = _compact_recommendation(
        LLMAnswerRequest(
            user_input="Co tang lieu duoc khong?",
            conversation_context="[Previous] EF 30 eGFR 55\n[Current] Co tang lieu duoc khong?",
            clinical_state={"intent": "dose_adjustment", "hf_type": "HFrEF"},
            patient=patient,
            recommendation=recommendation,
            verification=verification,
        )
    )

    assert compact["conversation_context"].startswith("[Previous]")
    assert compact["clinical_state"]["intent"] == "dose_adjustment"
    assert compact["response_language"] == "vi"
