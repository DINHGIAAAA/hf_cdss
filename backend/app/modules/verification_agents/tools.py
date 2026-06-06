import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from app.schemas.graphrag import AgentResult, GraphRAGContextResponse, VerificationRequest
from app.schemas.recommendation import RecommendationResponse


@dataclass
class AgentTool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[[dict[str, Any]], dict[str, Any]]

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _terms(value: str) -> set[str]:
    return {term for term in re.split(r"[^a-z0-9+]+", value.lower()) if len(term) >= 3}


def build_agent_tools(
    request: VerificationRequest,
    recommendation: RecommendationResponse,
    context: GraphRAGContextResponse,
    prior_results: list[AgentResult] | None = None,
) -> dict[str, AgentTool]:
    def inspect_safety(_: dict[str, Any]) -> dict[str, Any]:
        return {
            "risk_flags": [item.model_dump(mode="json") for item in recommendation.risk_flags],
            "constraints": [item.model_dump(mode="json") for item in recommendation.constraints],
            "recommendations": [
                {
                    "drug_class": item.drug_class,
                    "status": item.status,
                    "constraint_ids": item.constraint_ids,
                    "warnings": item.warnings,
                }
                for item in recommendation.recommendations
            ],
        }

    def inspect_missing(_: dict[str, Any]) -> dict[str, Any]:
        patient = request.patient.model_dump(mode="json")
        required = ["lvef", "egfr", "potassium", "systolic_bp", "heart_rate"]
        return {
            "missing_fields": [field for field in required if patient.get(field) is None],
            "missing_risk_flags": [
                risk.model_dump(mode="json")
                for risk in recommendation.risk_flags
                if risk.name.startswith("missing_")
            ],
        }

    def search_evidence(arguments: dict[str, Any]) -> dict[str, Any]:
        query_terms = _terms(str(arguments.get("query", "")))
        scored = []
        for chunk in context.evidence_chunks:
            score = len(query_terms & _terms(f"{chunk.document_id} {chunk.section} {chunk.text}"))
            scored.append((score, chunk))
        scored.sort(key=lambda item: (item[0], item[1].score), reverse=True)
        return {
            "retrieval_sources": context.retrieval_sources,
            "chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "section": chunk.section,
                    "text": chunk.text[:250],
                    "score": chunk.score,
                }
                for _, chunk in scored[:2]
            ],
        }

    def inspect_graph(_: dict[str, Any]) -> dict[str, Any]:
        return {
            "retrieval_sources": context.retrieval_sources,
            "facts": [item.model_dump(mode="json") for item in context.graph_facts[:3]],
        }

    def inspect_recommendation(_: dict[str, Any]) -> dict[str, Any]:
        return {
            "overall_status": recommendation.overall_status,
            "patient_summary": recommendation.patient_summary,
            "constraints": [item.model_dump(mode="json") for item in recommendation.constraints],
            "recommendations": [
                {
                    "drug_class": item.drug_class,
                    "status": item.status,
                    "rationale": item.rationale,
                    "constraint_ids": item.constraint_ids,
                }
                for item in recommendation.recommendations
            ],
        }

    def inspect_agent_results(_: dict[str, Any]) -> dict[str, Any]:
        return {
            "agent_results": [item.model_dump(mode="json") for item in prior_results or []],
            "severity_rule": "fail outranks warning; warning outranks pass",
        }

    empty_parameters = {"type": "object", "properties": {}, "additionalProperties": False}
    query_parameters = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Clinical evidence topic to inspect"}},
        "required": ["query"],
        "additionalProperties": False,
    }
    return {
        "inspect_safety_constraints": AgentTool(
            "inspect_safety_constraints",
            "Return structured risk flags, medication constraints, and recommendation statuses.",
            empty_parameters,
            inspect_safety,
        ),
        "inspect_missing_data": AgentTool(
            "inspect_missing_data",
            "Return missing core safety fields and missing-data risk flags.",
            empty_parameters,
            inspect_missing,
        ),
        "search_evidence": AgentTool(
            "search_evidence",
            "Search the already retrieved GraphRAG evidence chunks for a clinical topic.",
            query_parameters,
            search_evidence,
        ),
        "inspect_graph_facts": AgentTool(
            "inspect_graph_facts",
            "Return retrieved Neo4j graph facts relevant to the case.",
            empty_parameters,
            inspect_graph,
        ),
        "inspect_recommendation": AgentTool(
            "inspect_recommendation",
            "Return the complete structured recommendation.",
            empty_parameters,
            inspect_recommendation,
        ),
        "inspect_agent_results": AgentTool(
            "inspect_agent_results",
            "Return specialist verification results for final review.",
            empty_parameters,
            inspect_agent_results,
        ),
    }


AGENT_TOOL_NAMES = {
    "safety_agent": ["inspect_safety_constraints", "inspect_recommendation"],
    "missing_data_agent": ["inspect_missing_data", "inspect_recommendation"],
    "evidence_agent": ["search_evidence", "inspect_graph_facts"],
    "guideline_alignment_agent": ["search_evidence", "inspect_graph_facts", "inspect_recommendation"],
    "final_reviewer_agent": ["inspect_agent_results"],
}


def execute_tool(tool: AgentTool, raw_arguments: str | dict[str, Any] | None) -> str:
    if isinstance(raw_arguments, str):
        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError:
            arguments = {}
    else:
        arguments = raw_arguments or {}
    return json.dumps(tool.handler(arguments), ensure_ascii=False)
