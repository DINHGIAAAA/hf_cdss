import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.modules.datastores.postgres import write_audit_event
from app.modules.explanation.llm_service import build_llm_answer
from app.modules.missing_fields.service import build_missing_fields_prompt, check_missing_fields
from app.modules.reasoning.service import build_recommendation
from app.modules.verification_agents.service import verify_recommendation
from app.schemas.chat import ChatMessage, ChatRequest, ChatResponse, PatientDraft
from app.schemas.graphrag import VerificationRequest
from app.schemas.llm import LLMAnswerRequest
from app.schemas.patient import (
    CareContext,
    ClinicalValue,
    Condition,
    HeartFailureProfile,
    Labs,
    MedicationStatement,
    PatientIdentity,
    PatientProfile,
    RedFlag,
    Vitals,
)
from app.schemas.recommendation import RecommendationRequest


_drafts: dict[str, PatientDraft] = {}
_messages: dict[str, list[ChatMessage]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _message(conversation_id: str, role: str, content: str, metadata: dict[str, Any] | None = None) -> ChatMessage:
    return ChatMessage(
        message_id=str(uuid.uuid4()),
        conversation_id=conversation_id,
        role=role,
        content=content,
        created_at=_now(),
        metadata=metadata or {},
    )


def _append_message(message: ChatMessage) -> None:
    _messages.setdefault(message.conversation_id, []).append(message)


def _new_patient(conversation_id: str) -> PatientProfile:
    return PatientProfile(patient_identity=PatientIdentity(case_id=conversation_id))


def _num(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def _clinical_value(value: float | None, unit: str) -> ClinicalValue | None:
    return ClinicalValue(value=value, unit=unit) if value is not None else None


def _extract_patient_from_message(message: str, conversation_id: str) -> PatientProfile:
    lvef = _num(r"\b(?:lvef|ef)\s*[:=]?\s*(\d+(?:[.,]\d+)?)", message)
    egfr = _num(r"\b(?:egfr|e-gfr)\s*[:=]?\s*(\d+(?:[.,]\d+)?)", message)
    potassium = _num(r"\b(?:kali|potassium|serum k|k)\s*[:=]?\s*(\d+(?:[.,]\d+)?)", message)
    systolic_bp = _num(r"\b(?:sbp|huyet ap tam thu|systolic)\s*[:=]?\s*(\d+(?:[.,]\d+)?)", message)
    heart_rate = _num(r"\b(?:hr|heart rate|nhip tim)\s*[:=]?\s*(\d+(?:[.,]\d+)?)", message)

    conditions: list[Condition] = []
    for name, terms in {
        "CKD": ("ckd", "chronic kidney", "suy than"),
        "Diabetes": ("diabetes", "tieu duong", "dai thao duong"),
        "Atrial fibrillation": ("atrial fibrillation", "afib", "rung nhi"),
        "Hypertension": ("hypertension", "tang huyet ap"),
    }.items():
        if any(term in message.lower() for term in terms):
            conditions.append(Condition(name=name, status="active"))

    medications: list[MedicationStatement] = []
    for name, drug_class in {
        "spironolactone": "MRA",
        "eplerenone": "MRA",
        "metoprolol": "beta_blocker",
        "bisoprolol": "beta_blocker",
        "carvedilol": "beta_blocker",
        "lisinopril": "ACEi",
        "losartan": "ARB",
        "sacubitril valsartan": "ARNI",
        "dapagliflozin": "SGLT2i",
        "empagliflozin": "SGLT2i",
        "furosemide": "loop_diuretic",
    }.items():
        if name in message.lower():
            medications.append(MedicationStatement(name=name, drug_class=drug_class, status="active"))

    red_flags: list[RedFlag] = []
    for name, terms in {
        "cardiogenic_shock": ("shock", "soc tim", "cardiogenic shock"),
        "active_bleeding": ("active bleeding", "dang chay mau"),
        "acute_decompensated_hf": ("kho tho tang", "phu chan", "acute decompensated"),
    }.items():
        if any(term in message.lower() for term in terms):
            red_flags.append(RedFlag(name=name, status="present"))

    return PatientProfile(
        patient_identity=PatientIdentity(case_id=conversation_id),
        heart_failure_profile=HeartFailureProfile(lvef=_clinical_value(lvef, "%")),
        labs=Labs(
            egfr=_clinical_value(egfr, "mL/min/1.73m2"),
            potassium=_clinical_value(potassium, "mmol/L"),
        ),
        vitals=Vitals(
            systolic_bp=_clinical_value(systolic_bp, "mmHg"),
            heart_rate=_clinical_value(heart_rate, "bpm"),
        ),
        conditions=conditions,
        medications=medications,
        red_flags=red_flags,
        care_context=CareContext(clinician_question=message),
    )


def _prefer(existing: Any, incoming: Any) -> Any:
    return incoming if incoming not in (None, [], "") else existing


def _merge_patient(existing: PatientProfile, incoming: PatientProfile) -> PatientProfile:
    patient = existing.model_copy(deep=True)
    patient.patient_identity = incoming.patient_identity or patient.patient_identity
    patient.demographics.age = _prefer(patient.demographics.age, incoming.demographics.age)
    patient.demographics.sex = _prefer(patient.demographics.sex, incoming.demographics.sex)
    patient.heart_failure_profile.lvef = _prefer(
        patient.heart_failure_profile.lvef,
        incoming.heart_failure_profile.lvef,
    )
    patient.heart_failure_profile.nyha_class = _prefer(
        patient.heart_failure_profile.nyha_class,
        incoming.heart_failure_profile.nyha_class,
    )
    patient.labs.egfr = _prefer(patient.labs.egfr, incoming.labs.egfr)
    patient.labs.creatinine = _prefer(patient.labs.creatinine, incoming.labs.creatinine)
    patient.labs.potassium = _prefer(patient.labs.potassium, incoming.labs.potassium)
    patient.vitals.systolic_bp = _prefer(patient.vitals.systolic_bp, incoming.vitals.systolic_bp)
    patient.vitals.heart_rate = _prefer(patient.vitals.heart_rate, incoming.vitals.heart_rate)
    patient.conditions = _merge_named(patient.conditions, incoming.conditions, "name")
    patient.medications = _merge_named(patient.medications, incoming.medications, "name")
    patient.allergy_statements = _merge_named(patient.allergy_statements, incoming.allergy_statements, "substance")
    patient.red_flags = _merge_named(patient.red_flags, incoming.red_flags, "name")
    patient.care_context.clinician_question = _prefer(
        patient.care_context.clinician_question,
        incoming.care_context.clinician_question,
    )
    patient.care_context.decision_context = _prefer(
        patient.care_context.decision_context,
        incoming.care_context.decision_context,
    )
    return patient


def _merge_named(existing: list[Any], incoming: list[Any], attr: str) -> list[Any]:
    by_name = {str(getattr(item, attr)).lower(): item for item in existing}
    for item in incoming:
        by_name.setdefault(str(getattr(item, attr)).lower(), item)
    return list(by_name.values())


async def process_chat(request: ChatRequest) -> ChatResponse:
    conversation_id = request.conversation_id or str(uuid.uuid4())
    _append_message(_message(conversation_id, "user", request.message))

    current = _drafts.get(conversation_id)
    base_patient = current.patient if current else _new_patient(conversation_id)
    extracted_patient = _extract_patient_from_message(request.message, conversation_id)
    merged = _merge_patient(base_patient, extracted_patient)
    if request.patient:
        merged = _merge_patient(merged, request.patient)

    draft = PatientDraft(conversation_id=conversation_id, patient=merged, updated_at=_now())
    _drafts[conversation_id] = draft

    missing_check = check_missing_fields(merged)
    tool_outputs: list[dict[str, Any]] = [
        {"tool": "patient_draft_merge", "patient": merged.legacy_summary()},
        {"tool": "missing_field_checker", "result": missing_check.model_dump(mode="json")},
    ]

    if missing_check.missing_fields:
        content = build_missing_fields_prompt(missing_check)
        assistant_message = _message(conversation_id, "assistant", content, {"status": "needs_more_information"})
        _append_message(assistant_message)
        write_audit_event(
            merged.case_id,
            "chat_missing_fields",
            {"message": request.message, "missing_check": missing_check.model_dump(mode="json")},
        )
        return ChatResponse(
            conversation_id=conversation_id,
            status="needs_more_information",
            assistant_message=assistant_message,
            patient_draft=draft,
            missing_check=missing_check,
            tool_outputs=tool_outputs,
        )

    recommendation = build_recommendation(RecommendationRequest(patient=merged))
    verification = await verify_recommendation(VerificationRequest(patient=merged, recommendation=recommendation))
    llm_answer = build_llm_answer(
        LLMAnswerRequest(
            user_input=request.message,
            patient=merged,
            recommendation=recommendation,
            verification=verification,
            language=request.language,
        )
    )
    tool_outputs.extend(
        [
            {"tool": "recommendation", "result": recommendation.model_dump(mode="json")},
            {"tool": "verification", "result": verification.model_dump(mode="json")},
        ]
    )
    assistant_message = _message(
        conversation_id,
        "assistant",
        llm_answer.answer,
        {"status": "completed", "model": llm_answer.model, "used_llm": llm_answer.used_llm},
    )
    _append_message(assistant_message)
    write_audit_event(
        merged.case_id,
        "chat_recommendation_completed",
        {
            "message": request.message,
            "patient": merged.model_dump(mode="json"),
            "recommendation": recommendation.model_dump(mode="json"),
            "verification": verification.model_dump(mode="json"),
            "assistant": llm_answer.model_dump(mode="json"),
        },
    )
    return ChatResponse(
        conversation_id=conversation_id,
        status="completed",
        assistant_message=assistant_message,
        patient_draft=draft,
        missing_check=missing_check,
        recommendation=recommendation,
        verification=verification,
        llm_answer=llm_answer,
        tool_outputs=tool_outputs,
    )


def get_chat_history(conversation_id: str) -> tuple[list[ChatMessage], PatientDraft | None]:
    return _messages.get(conversation_id, []), _drafts.get(conversation_id)
