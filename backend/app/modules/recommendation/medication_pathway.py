"""GDMT medication roadmap from labs + structured recommendations (not full drug catalog)."""

from __future__ import annotations

from typing import Any

from app.modules.graphrag.query_decomposition import normalize_drug_class
from app.modules.recommendation.drug_class_keys import CANONICAL_GDMT_CLASS_IDS
from app.schemas.medication_pathway import LabGateCheck, MedicationPathwayStep
from app.schemas.patient import PatientProfile
from app.schemas.recommendation import MedicationRecommendation, RecommendationResponse

# Typical HFrEF sequencing (diuretic often parallel; RAAS before BB before MRA/SGLT2 in many pathways).
PATHWAY_CLASS_ORDER: tuple[str, ...] = (
    "loop_diuretic",
    "acei_arb",
    "arni",
    "acei",
    "arb",
    "beta_blocker",
    "mra",
    "sglt2i",
    "raas",
)


def _plan_class_id(drug_class: str | None) -> str:
    normalized = normalize_drug_class((drug_class or "").replace("ACE INHIBITOR", "ace inhibitor"))
    if normalized in CANONICAL_GDMT_CLASS_IDS:
        return normalized
    lowered = (drug_class or "").lower()
    if "ace" in lowered and "inhibitor" in lowered:
        return "acei_arb"
    if "beta" in lowered and "block" in lowered:
        return "beta_blocker"
    if "sglt2" in lowered:
        return "sglt2i"
    if "mra" in lowered or "mineralocorticoid" in lowered:
        return "mra"
    if "loop" in lowered and "diuretic" in lowered:
        return "loop_diuretic"
    return normalized


def _dose_summary(plan: Any | None) -> str | None:
    if plan is None:
        return None
    dose = getattr(plan, "recommended_dose", None)
    if dose is None:
        return None
    label = getattr(dose, "label", None) or (
        f"{getattr(dose, 'value', '')} {getattr(dose, 'unit', 'mg')}".strip()
    )
    freq = getattr(dose, "frequency", None) or ""
    return f"{label} · {freq}".strip(" ·")


def _lab_gates(class_id: str, patient: PatientProfile) -> list[LabGateCheck]:
    egfr = patient.egfr
    potassium = patient.potassium
    sbp = patient.systolic_bp
    hr = patient.heart_rate
    checks: list[LabGateCheck] = []

    def add(lab: str, label: str, value: float | None, requirement: str, passed: bool | None) -> None:
        checks.append(
            LabGateCheck(
                lab=lab,
                label=label,
                value=str(value) if value is not None else None,
                requirement=requirement,
                passed=passed,
            )
        )

    if class_id in {"acei_arb", "arni", "acei", "arb", "raas"}:
        add("systolic_bp", "SBP", sbp, "≥ 100 mmHg before uptitration", sbp >= 100 if sbp is not None else None)
        add("potassium", "K+", potassium, "≤ 5.5 mmol/L", potassium <= 5.5 if potassium is not None else None)
        add("egfr", "eGFR", egfr, "≥ 20 mL/min/1.73m²", egfr >= 20 if egfr is not None else None)
    elif class_id == "beta_blocker":
        add("heart_rate", "HR", hr, "≥ 55 bpm", hr >= 55 if hr is not None else None)
        add("systolic_bp", "SBP", sbp, "≥ 95 mmHg", sbp >= 95 if sbp is not None else None)
    elif class_id == "mra":
        add("potassium", "K+", potassium, "≤ 5.0 mmol/L", potassium <= 5.0 if potassium is not None else None)
        add("egfr", "eGFR", egfr, "≥ 30 mL/min/1.73m²", egfr >= 30 if egfr is not None else None)
    elif class_id == "sglt2i":
        add("egfr", "eGFR", egfr, "≥ 20 mL/min/1.73m²", egfr >= 20 if egfr is not None else None)
    elif class_id == "loop_diuretic":
        add("potassium", "K+", potassium, "Monitor with diuretic", None)

    return checks


def _gates_pass(checks: list[LabGateCheck]) -> bool:
    for check in checks:
        if check.passed is False:
            return False
    return True


def _patient_drug_for_class(patient: PatientProfile, class_id: str) -> str | None:
    for med in patient.current_medications or []:
        lowered = med.lower()
        if class_id == "mra" and any(t in lowered for t in ("spironolactone", "eplerenone", "finerenone")):
            return med
        if class_id == "beta_blocker" and any(
            t in lowered for t in ("bisoprolol", "carvedilol", "metoprolol", "nebivolol")
        ):
            return med
        if class_id in {"acei_arb", "acei", "arb", "raas"} and any(
            t in lowered
            for t in ("ramipril", "enalapril", "lisinopril", "perindopril", "losartan", "valsartan", "candesartan")
        ):
            return med
        if class_id == "arni" and any(t in lowered for t in ("sacubitril", "entresto", "valsartan")):
            return med
        if class_id == "sglt2i" and any(t in lowered for t in ("dapagliflozin", "empagliflozin", "sglt")):
            return med
        if class_id == "loop_diuretic" and any(t in lowered for t in ("furosemide", "bumetanide", "torsemide")):
            return med
    return None


def _pathway_phase(
    item: MedicationRecommendation,
    *,
    gates_ok: bool,
    on_therapy: bool,
) -> str:
    if item.status == "avoid":
        return "blocked"
    if not gates_ok:
        return "hold"
    if item.status == "continue" or on_therapy:
        return "active"
    if item.status in {"consider", "consider_with_caution"}:
        return "next"
    return "hold"


def _action_line(item: MedicationRecommendation) -> str:
    for candidate in (item.action_items or [])[:1]:
        if candidate:
            return str(candidate)
    return (item.plain_language_summary or item.rationale or "").strip()


def _ordered_recommendations(recommendation: RecommendationResponse) -> list[MedicationRecommendation]:
    by_id = {item.class_id: item for item in recommendation.recommendations if item.class_id}
    ordered: list[MedicationRecommendation] = []
    seen: set[str] = set()

    for class_id in PATHWAY_CLASS_ORDER:
        if class_id in seen:
            continue
        item = by_id.get(class_id)
        if not item:
            continue
        if class_id in {"acei", "arb"} and "acei_arb" in by_id:
            continue
        if class_id == "acei_arb" and "arni" in by_id and by_id["arni"].status in {"consider", "consider_with_caution"}:
            continue
        ordered.append(item)
        seen.add(class_id)

    for item in recommendation.recommendations:
        if item.class_id and item.class_id not in seen and item.class_id in CANONICAL_GDMT_CLASS_IDS:
            ordered.append(item)
            seen.add(item.class_id)
    return ordered


def build_medication_pathway(
    patient: PatientProfile,
    recommendation: RecommendationResponse,
) -> list[MedicationPathwayStep]:
    dose_by_class: dict[str, Any] = {}
    for plan in recommendation.dose_plans or []:
        cid = _plan_class_id(plan.drug_class)
        if cid and cid not in dose_by_class:
            dose_by_class[cid] = plan

    steps: list[MedicationPathwayStep] = []
    for index, item in enumerate(_ordered_recommendations(recommendation), start=1):
        class_id = item.class_id or _plan_class_id(item.drug_class)
        if class_id not in CANONICAL_GDMT_CLASS_IDS:
            continue
        gates = _lab_gates(class_id, patient)
        gates_ok = _gates_pass(gates)
        patient_drug = _patient_drug_for_class(patient, class_id)
        plan = dose_by_class.get(class_id)
        if plan and not patient_drug:
            patient_drug = plan.drug_name
        phase = _pathway_phase(item, gates_ok=gates_ok, on_therapy=bool(patient_drug))
        steps.append(
            MedicationPathwayStep(
                step_order=index,
                class_id=class_id,
                drug_class=item.drug_class,
                pathway_phase=phase,
                recommendation_status=item.status,
                patient_drug=patient_drug,
                dose_summary=_dose_summary(plan),
                action=_action_line(item),
                lab_gates=gates,
            )
        )
    return steps
