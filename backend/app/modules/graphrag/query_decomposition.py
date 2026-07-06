"""Decompose complex clinical questions into facet-specific retrieval queries."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.modules.clinical_terms import CLINICAL_TERMS, DRUG_CLASS_TERMS, dedupe_strings, patient_lab_context_text
from app.schemas.graphrag import GraphRAGContextRequest
from app.schemas.patient import PatientProfile


DRUG_CLASS_ALIASES: dict[str, str] = {
    "mra": "mra",
    "arni": "arni",
    "acei": "acei",
    "ace inhibitor": "acei",
    "ace_inhibitor": "acei",
    "arb": "arb",
    "beta_blocker": "beta_blocker",
    "beta blocker": "beta_blocker",
    "beta": "beta_blocker",
    "sglt2i": "sglt2i",
    "sglt2": "sglt2i",
    "sglt2 inhibitor": "sglt2i",
}

DRUG_CLASS_LABELS: dict[str, str] = {
    "mra": "mineralocorticoid receptor antagonist",
    "arni": "ARNI sacubitril valsartan",
    "acei": "ACE inhibitor",
    "arb": "angiotensin receptor blocker",
    "beta_blocker": "beta blocker",
    "sglt2i": "SGLT2 inhibitor",
}


@dataclass(frozen=True)
class DrugClassFacet:
    drug_class: str
    medications: tuple[str, ...]


def normalize_drug_class(value: str | None) -> str:
    if not value:
        return ""
    key = value.strip().lower().replace("-", " ").replace("_", " ")
    key = " ".join(key.split())
    if key in DRUG_CLASS_ALIASES:
        return DRUG_CLASS_ALIASES[key]
    underscored = key.replace(" ", "_")
    return DRUG_CLASS_ALIASES.get(underscored, underscored)


def _infer_classes_from_medications(patient: PatientProfile) -> list[str]:
    classes: set[str] = set()
    for medication in patient.current_medications:
        medication_lower = medication.lower()
        for drug_class, terms in DRUG_CLASS_TERMS.items():
            if any(term in medication_lower for term in terms if len(term) >= 5):
                classes.add(drug_class)
    return sorted(classes)


def _medications_for_class(drug_class: str, patient: PatientProfile, clinical_state: dict) -> list[str]:
    names: set[str] = set()
    for medication in clinical_state.get("mentioned_medications") or []:
        if not isinstance(medication, dict):
            continue
        if normalize_drug_class(medication.get("drug_class")) == drug_class and medication.get("name"):
            names.add(str(medication["name"]))

    for medication in patient.medications:
        if medication.status == "active" and normalize_drug_class(medication.drug_class) == drug_class:
            names.add(medication.normalized_name or medication.name)

    class_terms = DRUG_CLASS_TERMS.get(drug_class, [])
    for medication in patient.current_medications:
        medication_lower = medication.lower()
        if any(term in medication_lower for term in class_terms if len(term) >= 5):
            names.add(medication)

    return sorted(name for name in names if name)[:3]


def collect_drug_class_facets(patient: PatientProfile, clinical_state: dict | None) -> list[DrugClassFacet]:
    state = clinical_state or {}
    raw_classes: list[str] = []
    for key in ("focus_medication_classes", "active_medication_classes"):
        raw_classes.extend(str(value) for value in state.get(key) or [] if value)
    for medication in state.get("mentioned_medications") or []:
        if isinstance(medication, dict) and medication.get("drug_class"):
            raw_classes.append(str(medication["drug_class"]))
    for medication in patient.medications:
        if medication.status == "active" and medication.drug_class:
            raw_classes.append(medication.drug_class)
    if not raw_classes:
        raw_classes = _infer_classes_from_medications(patient)

    facets: list[DrugClassFacet] = []
    seen: set[str] = set()
    for raw in raw_classes:
        drug_class = normalize_drug_class(raw)
        if not drug_class or drug_class in seen:
            continue
        seen.add(drug_class)
        facets.append(
            DrugClassFacet(
                drug_class=drug_class,
                medications=tuple(_medications_for_class(drug_class, patient, state)),
            )
        )
    return facets


def collect_condition_facets(patient: PatientProfile, clinical_state: dict | None) -> list[str]:
    state = clinical_state or {}
    conditions: set[str] = set()
    for value in state.get("conditions") or []:
        if value:
            conditions.add(str(value))
    for value in patient.comorbidities:
        if value:
            conditions.add(str(value))

    if patient.egfr is not None and patient.egfr < 60:
        conditions.add("renal impairment CKD")
    if patient.potassium is not None and patient.potassium >= 5.0:
        conditions.add("hyperkalemia")
    if patient.systolic_bp is not None and patient.systolic_bp < 100:
        conditions.add("hypotension")
    if patient.heart_rate is not None and patient.heart_rate < 60:
        conditions.add("bradycardia")

    return sorted(conditions)


def _condition_search_terms(condition: str) -> str:
    lower = condition.lower()
    for label, terms in CLINICAL_TERMS.items():
        if label in lower:
            return " ".join(terms[:6])
    return condition


def should_decompose_query(drug_facets: list[DrugClassFacet], conditions: list[str]) -> bool:
    if len(drug_facets) >= 2:
        return True
    if len(conditions) >= 2:
        return True
    return bool(drug_facets and conditions)


def build_drug_class_query(
    facet: DrugClassFacet,
    *,
    patient: PatientProfile,
    clinical_state: dict | None,
    baseline_query: str,
) -> str:
    state = clinical_state or {}
    label = DRUG_CLASS_LABELS.get(facet.drug_class, facet.drug_class.replace("_", " "))
    search_terms = " ".join(DRUG_CLASS_TERMS.get(facet.drug_class, [facet.drug_class])[:6])
    medication_names = " ".join(facet.medications)
    hf_type = state.get("hf_type") or "heart failure"
    intent = state.get("intent") or ""
    lab_context = patient_lab_context_text(patient)
    baseline = baseline_query.strip()[:240]
    return " ".join(
        part
        for part in [
            hf_type,
            label,
            medication_names,
            search_terms,
            lab_context,
            intent,
            baseline,
        ]
        if part
    ).strip()


def build_condition_query(
    condition: str,
    *,
    patient: PatientProfile,
    clinical_state: dict | None,
) -> str:
    state = clinical_state or {}
    hf_type = state.get("hf_type") or "heart failure"
    lab_context = patient_lab_context_text(patient)
    condition_terms = _condition_search_terms(condition)
    return " ".join(
        part
        for part in [
            hf_type,
            "comorbidity",
            condition,
            condition_terms,
            lab_context,
            "heart failure management contraindications monitoring",
        ]
        if part
    ).strip()


def decompose_retrieval_queries(
    request: GraphRAGContextRequest,
    *,
    baseline_query: str,
) -> list[str]:
    if not settings.graphrag_query_decomposition_enabled:
        return []

    drug_facets = collect_drug_class_facets(request.patient, request.clinical_state)
    conditions = collect_condition_facets(request.patient, request.clinical_state)
    if not should_decompose_query(drug_facets, conditions):
        return []

    queries: list[str] = []
    for facet in drug_facets:
        queries.append(
            build_drug_class_query(
                facet,
                patient=request.patient,
                clinical_state=request.clinical_state,
                baseline_query=baseline_query,
            )
        )
    for condition in conditions:
        queries.append(
            build_condition_query(
                condition,
                patient=request.patient,
                clinical_state=request.clinical_state,
            )
        )

    return dedupe_strings(queries, max_items=max(2, settings.graphrag_query_decomposition_max_queries))
