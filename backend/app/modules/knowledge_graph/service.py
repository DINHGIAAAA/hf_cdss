from typing import Any

from app.modules.constraint_builder.service import load_constraint_rules
from app.modules.graphrag.service import retrieve_graph_facts
from app.modules.gdmt_policy.policy_engine import policy_aliases
from app.modules.gdmt_policy.policy_loader import load_executable_gdmt_policies
from app.schemas.graphrag import GraphFact
from app.schemas.knowledge_graph import DrugClassInfo, KGRecommendation


def _policies_by_key() -> dict[str, dict[str, Any]]:
    return {str(item.get("drug_class_key")): item for item in load_executable_gdmt_policies()}


def _constraint_matches(rule: dict[str, Any], drug_class: str) -> bool:
    target = rule.get("target_drug_class")
    return target in {drug_class, "all_gdmt"}


def list_drug_classes() -> list[DrugClassInfo]:
    constraints = load_constraint_rules()
    policies = load_executable_gdmt_policies()
    return [
        DrugClassInfo(
            drug_class=str(policy.get("drug_class_key")),
            label=str(policy.get("display_label")),
            aliases=policy_aliases(policy),
            constraint_count=sum(
                1 for rule in constraints if _constraint_matches(rule, str(policy.get("drug_class_key")))
            ),
        )
        for policy in policies
    ]


def recommendations_for_hf_type(hf_type: str) -> tuple[list[KGRecommendation], list[GraphFact]]:
    normalized_hf_type = hf_type.strip() or "unknown"
    is_hfref = normalized_hf_type.lower() == "hfref"
    policies = load_executable_gdmt_policies()
    recommendations = [
        KGRecommendation(
            hf_type=normalized_hf_type,
            drug_class=str(policy.get("drug_class_key")),
            label=str(policy.get("display_label")),
            recommendation="guideline_directed" if is_hfref else "review_phenotype",
            rationale=(
                f"{policy.get('display_label')} is a core guideline-directed therapy class for HFrEF."
                if is_hfref
                else f"{policy.get('display_label')} requires phenotype-specific review for {normalized_hf_type}."
            ),
            evidence_refs=["kg:gdmt_policies", "week3_pipeline:gdmt_policy_v1"],
        )
        for policy in policies
    ]
    terms = [normalized_hf_type, "heart failure", "gdmt", *[item.label for item in recommendations]]
    facts = retrieve_graph_facts(terms, top_k=8)
    return recommendations, facts


def constraints_for_drug_class(drug_class: str) -> tuple[list[dict[str, Any]], list[GraphFact]]:
    normalized = _resolve_drug_class(drug_class)
    constraints = [rule for rule in load_constraint_rules() if _constraint_matches(rule, normalized)]
    policy = _policies_by_key().get(normalized, {})
    label = policy.get("display_label", normalized)
    terms = [normalized, label, "constraint", "contraindication", "monitoring"]
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
    for policy in load_executable_gdmt_policies():
        drug_class = str(policy.get("drug_class_key"))
        label = str(policy.get("display_label"))
        candidates = {drug_class.lower(), label.lower(), *(alias.lower() for alias in policy_aliases(policy))}
        if normalized in candidates:
            return drug_class
    return value

