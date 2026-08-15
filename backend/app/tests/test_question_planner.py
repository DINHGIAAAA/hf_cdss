from app.modules.question_planner.service import (
    fallback_question_plan,
    plan_clinical_questions,
)
from app.schemas.patient import PatientProfile
import pytest


def _demo_patient() -> PatientProfile:
    return PatientProfile.model_validate(
        {
            "patient_identity": {"case_id": "plan-demo"},
            "demographics": {"age": 68, "sex": "male"},
            "heart_failure_profile": {"lvef": {"value": 28}},
            "labs": {
                "egfr": {"value": 42},
                "potassium": {"value": 4.8},
            },
            "vitals": {"systolic_bp": {"value": 108}, "heart_rate": {"value": 72}},
            "medications": [
                {"name": "ramipril", "status": "active"},
                {"name": "spironolactone", "status": "active"},
            ],
            "allergy_statements": [{"substance": "NKDA", "status": "active"}],
            "red_flags": [{"name": "stable", "status": "absent"}],
            "care_context": {"clinician_question": "GDMT review"},
        }
    )


def test_fallback_plan_splits_multi_question() -> None:
    message = "MRA or SGLT2i? What about ARNI? Should I add beta blocker?"
    plan = fallback_question_plan(message, patient=_demo_patient())
    assert plan.is_multi_question
    assert len(plan.questions) == 3
    assert "MRA" in plan.questions[0].text
    assert "ARNI" in plan.questions[1].text
    assert plan.questions[0].intent == "choice_question"
    assert "egfr" in plan.questions[0].required_data_fields


def test_fallback_plan_arni_requires_acei_washout() -> None:
    plan = fallback_question_plan("What about ARNI?", patient=_demo_patient())
    assert len(plan.questions) == 1
    assert "acei_last_dose_hours_ago" in plan.questions[0].required_data_fields


@pytest.mark.asyncio
async def test_plan_clinical_questions_uses_fallback_when_llm_disabled(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "question_planner_enabled", False)
    plan = await plan_clinical_questions(
        "MRA or SGLT2i? What about ARNI?",
        patient=_demo_patient(),
    )
    assert plan.source == "fallback"
    assert len(plan.questions) >= 2


def test_planner_prefers_rule_split_when_llm_under_splits() -> None:
    from app.modules.question_planner.service import _parse_llm_plan

    message = "What about ARNI? Should I add beta blocker?"
    fallback = fallback_question_plan(message, patient=_demo_patient())
    merged = _parse_llm_plan(
        {
            "reasoning": "single combined question",
            "is_multi_question": False,
            "questions": [
                {
                    "text": "Should I add a beta blocker to the patient's regimen?",
                    "intent": "start_medication",
                    "focus_class_ids": ["beta_blocker"],
                    "required_data_fields": ["egfr"],
                }
            ],
        },
        patient=_demo_patient(),
    )
    assert merged is not None
    assert len(fallback.questions) > len(merged.questions)


def test_is_multi_question_thread_single_question_is_false() -> None:
    from app.modules.chat.service import _is_multi_question_thread

    assert not _is_multi_question_thread({"answered": ["Q1"], "remaining": [], "total_questions": 1})
    assert _is_multi_question_thread({"answered": ["Q1"], "remaining": ["Q2"], "total_questions": 2})
    assert _is_multi_question_thread({"answered": ["Q1", "Q2"], "remaining": [], "total_questions": 2})


def test_planner_model_defaults_to_1_5b(monkeypatch) -> None:
    from app.core.config import settings
    from app.modules.question_planner.service import _planner_model

    monkeypatch.setattr(settings, "question_planner_model", "qwen2.5:1.5b")
    monkeypatch.setattr(settings, "llm_model", "qwen2.5:7b")
    assert _planner_model() == "qwen2.5:1.5b"


def test_looks_like_obvious_single_question() -> None:
    from app.modules.question_planner.service import looks_like_obvious_single_question

    assert looks_like_obvious_single_question("What about ARNI?") is True
    assert looks_like_obvious_single_question("What about ARNI? Should I add beta blocker?") is False


@pytest.mark.asyncio
async def test_plan_skips_llm_for_obvious_single_question(monkeypatch) -> None:
    from app.core.config import settings
    from app.modules.question_planner import service as qp_service

    monkeypatch.setattr(settings, "question_planner_enabled", True)
    called = {"llm": False}

    async def fake_llm(**_kwargs):
        called["llm"] = True
        return None

    monkeypatch.setattr(qp_service, "_call_llm_planner", fake_llm)
    plan = await plan_clinical_questions("What about ARNI?", patient=_demo_patient())
    assert plan.source == "fallback"
    assert called["llm"] is False
