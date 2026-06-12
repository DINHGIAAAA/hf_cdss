from typing import Any

from app.modules.constraint_builder.service import load_constraint_rules
from app.modules.graphrag.service import retrieve_graph_facts
from app.modules.reasoning.service import GDMT_CLASSES
from app.schemas.graphrag import GraphFact
from app.schemas.knowledge_graph import DrugClassInfo, KGRecommendation


ALIASES = {
    "ARNI/ACEi/ARB": ["arni", "acei", "arb", "raas", "sacubitril", "valsartan", "lisinopril", "losartan"],
    "beta_blocker": ["beta blocker", "metoprolol", "bisoprolol", "carvedilol", "bradycardia"],
    "MRA": ["mra", "mineralocorticoid receptor antagonist", "spironolactone", "eplerenone", "potassium"],
    "SGLT2i": ["sglt2", "sglt2 inhibitor", "dapagliflozin", "empagliflozin", "renal"],
}


def _constraint_matches(rule: dict[str, Any], drug_class: str) -> bool:
    target = rule.get("target_drug_class")
    return target in {drug_class, "all_gdmt"}


def list_drug_classes() -> list[DrugClassInfo]:
    constraints = load_constraint_rules()
    return [
        DrugClassInfo(
            drug_class=drug_class,
            label=label,
            aliases=ALIASES.get(drug_class, []),
            constraint_count=sum(1 for rule in constraints if _constraint_matches(rule, drug_class)),
        )
        for drug_class, label in GDMT_CLASSES.items()
    ]


def recommendations_for_hf_type(hf_type: str) -> tuple[list[KGRecommendation], list[GraphFact]]:
    normalized_hf_type = hf_type.strip() or "unknown"
    is_hfref = normalized_hf_type.lower() == "hfref"
    recommendations = [
        KGRecommendation(
            hf_type=normalized_hf_type,
            drug_class=drug_class,
            label=label,
            recommendation="guideline_directed" if is_hfref else "review_phenotype",
            rationale=(
                f"{label} is a core guideline-directed therapy class for HFrEF."
                if is_hfref
                else f"{label} requires phenotype-specific review for {normalized_hf_type}."
            ),
            evidence_refs=["kg:gdmt_classes", "week3_pipeline:constraint_rules_v1"],
        )
        for drug_class, label in GDMT_CLASSES.items()
    ]
    terms = [normalized_hf_type, "heart failure", "gdmt", *[item.label for item in recommendations]]
    facts = retrieve_graph_facts(terms, top_k=8)
    return recommendations, facts


def constraints_for_drug_class(drug_class: str) -> tuple[list[dict[str, Any]], list[GraphFact]]:
    normalized = _resolve_drug_class(drug_class)
    constraints = [rule for rule in load_constraint_rules() if _constraint_matches(rule, normalized)]
    terms = [normalized, GDMT_CLASSES.get(normalized, normalized), "constraint", "contraindication", "monitoring"]
    return constraints, retrieve_graph_facts(terms, top_k=8)


def interactions_for_drug(drug: str | None = None, top_k: int = 10) -> list[GraphFact]:
    terms = ["drug_interaction", "interaction"]
    if drug:
        terms.append(drug)
    facts = retrieve_graph_facts(terms, top_k=max(1, min(top_k, 20)))
    return [
        fact
        for fact in facts
        if "interaction" in str(fact.metadata.get("claim_type", "")).lower()
        or "interaction" in fact.relationship_type.lower()
        or "interaction" in fact.target_id.lower()
    ][:top_k]


def _resolve_drug_class(value: str) -> str:
    normalized = value.strip().lower()
    for drug_class, aliases in ALIASES.items():
        candidates = {drug_class.lower(), GDMT_CLASSES[drug_class].lower(), *(alias.lower() for alias in aliases)}
        if normalized in candidates:
            return drug_class
    return value

