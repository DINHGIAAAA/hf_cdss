"""Deterministic answers for binary medication-class choice questions (e.g. MRA vs SGLT2i)."""

from __future__ import annotations

from app.modules.clinical_normalization.service import normalize_patient
from app.modules.explanation.card_summarizer import (
    _contains_cjk,
    _needs_locale_fallback,
    deterministic_card_summary,
)
from app.modules.explanation.question_focus import is_mra_vs_sglt2_choice
from app.modules.recommendation.drug_class_keys import display_label_for_class_id
from app.modules.recommendation.medication_pathway import _gates_pass, _lab_gates
from app.prompts.explanation import REQUIRED_CLINICAL_DISCLAIMER
from app.schemas.patient import PatientProfile
from app.schemas.recommendation import MedicationRecommendation, RecommendationResponse

_COPY = {
    "intro": (
        "This question compares two independent directions — MRA and SGLT2 inhibitors do not share the same "
        "warnings or contraindications. Summary from CDSS data and current lab thresholds:"
    ),
    "closing": (
        "You may prioritize one branch or pursue both depending on GDMT goals, tolerability, and electrolyte/"
        "renal monitoring plans; do not transfer a warning for one specific drug to another in the same class "
        "unless the payload states it."
    ),
    "status": "**{label}** — CDSS status: `{status}`.",
    "gate_met": "{label}: met ({req})",
    "gate_not_met": "{label}: not met ({req})",
    "gate_verify": "{label}: verify ({req})",
    "gates_header": "Clinical thresholds: ",
    "avoid": "Defer or avoid until contraindications are addressed.",
    "proceed": (
        "Given current eGFR/K+/BP thresholds, the next step can be discussed if it fits treatment goals."
    ),
    "mra_uptitrate_near_k": (
        "On MRA (e.g. spironolactone 25 mg/day): consider gradual up-titration toward target dose "
        "(often 50 mg/day) if K+ and renal function are stable; current K+ is near 5.0 mmol/L — "
        "recheck electrolytes and creatinine at ~1 and 4 weeks after dose changes."
    ),
    "mra_uptitrate": "On MRA: consider up-titration toward guideline target if tolerated and labs allow.",
    "review": "Review contraindications and monitoring before up-titrating or starting.",
    "disclaimer": REQUIRED_CLINICAL_DISCLAIMER,
}


def _item_for_class(recommendation: RecommendationResponse, class_id: str) -> MedicationRecommendation | None:
    for item in recommendation.recommendations:
        if (item.class_id or "").lower() == class_id:
            return item
    return None


def _locale_safe_summary(item: MedicationRecommendation) -> str:
    """Use the deterministic summary when card LLM text is CJK or otherwise unusable."""
    chunks = [
        str(item.plain_language_summary or "").strip(),
        str(item.rationale or "").strip(),
    ]
    combined = " ".join(c for c in chunks if c)
    if not combined or _needs_locale_fallback(combined):
        return deterministic_card_summary(item)
    plain = str(item.plain_language_summary or "").strip()
    if plain and not _needs_locale_fallback(plain):
        return plain
    return deterministic_card_summary(item)


def _comparative_branch(
    *,
    label: str,
    item: MedicationRecommendation | None,
    patient: PatientProfile,
    class_id: str,
    include_summary: bool = True,
) -> str:
    copy = _COPY

    gates = _lab_gates(class_id, patient)
    gates_ok = _gates_pass(gates)
    gate_lines: list[str] = []
    for check in gates:
        if check.passed is True:
            gate_lines.append(copy["gate_met"].format(label=check.label, req=check.requirement))
        elif check.passed is False:
            gate_lines.append(copy["gate_not_met"].format(label=check.label, req=check.requirement))
        else:
            gate_lines.append(copy["gate_verify"].format(label=check.label, req=check.requirement))

    status = (item.status if item else "review") or "review"
    parts = [copy["status"].format(label=label, status=status)]
    if item and include_summary:
        summary = _locale_safe_summary(item)
        if summary:
            parts.append(summary)
    if gate_lines:
        parts.append(copy["gates_header"] + "; ".join(gate_lines) + ".")
    if status == "avoid":
        parts.append(copy["avoid"])
    elif gates_ok and status in {"consider", "consider_with_caution", "continue"}:
        parts.append(copy["proceed"])
        if class_id == "mra":
            norm = normalize_patient(patient)
            potassium = norm.observations.get("potassium")
            try:
                k_val = float(potassium) if potassium is not None else None
            except (TypeError, ValueError):
                k_val = None
            on_mra = any(
                (m.drug_class or "").lower() == "mra" or "spironolactone" in (m.name or "").lower()
                for m in (patient.medications or [])
                if (m.status or "active").lower() == "active"
            )
            if on_mra and k_val is not None and 4.5 <= k_val < 5.0:
                parts.append(copy["mra_uptitrate_near_k"])
            elif on_mra:
                parts.append(copy["mra_uptitrate"])
    else:
        parts.append(copy["review"])
    return " ".join(parts)


def build_comparative_answer(
    *,
    patient: PatientProfile,
    recommendation: RecommendationResponse,
    message: str,
    clinical_state: dict | None = None,
) -> str | None:
    if not is_mra_vs_sglt2_choice(message, clinical_state):
        return None

    copy = _COPY

    mra_item = _item_for_class(recommendation, "mra")
    sglt2_item = _item_for_class(recommendation, "sglt2i")
    mra_label = display_label_for_class_id("mra", "MRA")
    sglt2_label = display_label_for_class_id("sglt2i", "SGLT2 inhibitor")

    def assemble(*, include_summary: bool) -> str:
        mra_branch = _comparative_branch(
            label=mra_label,
            item=mra_item,
            patient=patient,
            class_id="mra",
            include_summary=include_summary,
        )
        sglt2_branch = _comparative_branch(
            label=sglt2_label,
            item=sglt2_item,
            patient=patient,
            class_id="sglt2i",
            include_summary=include_summary,
        )
        return "\n\n".join([copy["intro"], mra_branch, sglt2_branch, copy["closing"], copy["disclaimer"]])

    body = assemble(include_summary=True)
    if _contains_cjk(body):
        body = assemble(include_summary=False)
    return body
