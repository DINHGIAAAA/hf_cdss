import asyncio
import hashlib
import json
import logging
import threading
import time

from app.core.config import settings
from app.modules.citation_validation.service import apply_citation_guardrails, validate_citations
from app.modules.evidence_linking.service import attach_linked_evidence
from app.modules.graphrag.service import build_graphrag_context, build_graphrag_context_async
from app.modules.reasoning.service import build_recommendation
from app.modules.verification_agents.llm_runtime import run_llm_agent
from app.modules.verification_agents.tools import AGENT_TOOL_NAMES, build_agent_tools
from app.schemas.graphrag import (
    AgentResult,
    CitationValidation,
    GraphRAGContextRequest,
    GraphRAGContextResponse,
    VerificationRequest,
    VerificationResponse,
)
from app.schemas.patient import PatientProfile
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse


logger = logging.getLogger(__name__)
VERDICT_SEVERITY = {"pass": 0, "warning": 1, "fail": 2}
_verification_cache: dict[str, tuple[float, VerificationResponse]] = {}
_cache_lock = threading.Lock()


def _evidence_refs(response: RecommendationResponse) -> list[str]:
    refs: set[str] = set()
    for item in response.recommendations:
        refs.update(item.evidence)
        refs.update(item.constraint_ids)
    for constraint in response.constraints:
        if constraint.evidence_ref:
            refs.add(constraint.evidence_ref)
    return sorted(refs)


def safety_agent(response: RecommendationResponse) -> AgentResult:
    hard_constraints = [constraint for constraint in response.constraints if constraint.action == "avoid"]
    if hard_constraints:
        return AgentResult(
            agent_name="safety_agent",
            verdict="fail",
            message=f"{len(hard_constraints)} hard avoid constraint(s) detected; final recommendation should be blocked or deferred.",
            evidence_refs=[constraint.evidence_ref or constraint.constraint_id for constraint in hard_constraints],
        )

    caution_constraints = [constraint for constraint in response.constraints if constraint.action == "caution"]
    if caution_constraints:
        return AgentResult(
            agent_name="safety_agent",
            verdict="warning",
            message=f"{len(caution_constraints)} caution constraint(s) require clinician review.",
            evidence_refs=[constraint.evidence_ref or constraint.constraint_id for constraint in caution_constraints],
        )

    return AgentResult(
        agent_name="safety_agent",
        verdict="pass",
        message="No avoid or caution medication constraints were detected.",
        evidence_refs=_evidence_refs(response),
    )


def missing_data_agent(response: RecommendationResponse) -> AgentResult:
    missing = [risk for risk in response.risk_flags if risk.name.startswith("missing_")]
    if missing:
        return AgentResult(
            agent_name="missing_data_agent",
            verdict="warning",
            message="Missing safety fields were detected before confident medication selection.",
            evidence_refs=[risk.name for risk in missing],
        )

    return AgentResult(
        agent_name="missing_data_agent",
        verdict="pass",
        message="Core safety fields were present in the parsed patient profile.",
        evidence_refs=[],
    )


def evidence_agent(
    request: VerificationRequest,
    response: RecommendationResponse,
    context: GraphRAGContextResponse | None = None,
) -> AgentResult:
    context = context or build_graphrag_context(GraphRAGContextRequest(patient=request.patient, top_k=8))
    evidence_count = len(context.evidence_chunks) + len(context.graph_facts)
    if evidence_count == 0:
        return AgentResult(
            agent_name="evidence_agent",
            verdict="fail",
            message="No graph facts or evidence chunks were retrieved for this case.",
            evidence_refs=[],
        )

    return AgentResult(
        agent_name="evidence_agent",
        verdict="pass",
        message=f"GraphRAG retrieved {len(context.graph_facts)} graph fact(s) and {len(context.evidence_chunks)} text evidence chunk(s).",
        evidence_refs=[item.chunk_id for item in context.evidence_chunks[:3]]
        + [item.fact_id for item in context.graph_facts[:3]],
    )


def guideline_alignment_agent(response: RecommendationResponse) -> AgentResult:
    refs = _evidence_refs(response)
    if refs:
        return AgentResult(
            agent_name="guideline_alignment_agent",
            verdict="pass",
            message="Recommendation contains structured rule or pipeline evidence references.",
            evidence_refs=refs[:8],
        )

    return AgentResult(
        agent_name="guideline_alignment_agent",
        verdict="warning",
        message="Recommendation has no structured evidence references.",
        evidence_refs=[],
    )


def citation_validator_agent(
    response: RecommendationResponse,
    context: GraphRAGContextResponse,
    *,
    patient: PatientProfile | None = None,
    citation_validation: CitationValidation | None = None,
) -> AgentResult:
    validation = citation_validation or validate_citations(response, context, patient=patient)
    missing = [item for item in validation.supports if item.evidence_status == "missing"]
    weak = [item for item in validation.supports if item.evidence_status == "weak"]
    refs = [ref for item in validation.supports for ref in item.evidence_refs][:8]
    rec_status = validation.recommendation_status or validation.status
    safety_status = validation.safety_status
    detail = f" Recommendations={rec_status}"
    if safety_status:
        detail += f"; safety={safety_status}"
    if missing:
        return AgentResult(
            agent_name="citation_validator_agent",
            verdict="warning",
            message=(
                f"{len(missing)} recommendation or safety item(s) have no supporting retrieved citation."
                f"{detail}."
            ),
            evidence_refs=refs,
            tools_used=["validate_citations"],
        )
    if weak:
        return AgentResult(
            agent_name="citation_validator_agent",
            verdict="warning",
            message=f"{len(weak)} recommendation or safety item(s) have weak citation coverage.{detail}.",
            evidence_refs=refs,
            tools_used=["validate_citations"],
        )
    return AgentResult(
        agent_name="citation_validator_agent",
        verdict="pass",
        message=f"All recommendation and safety items have retrieved citation support.{detail}.",
        evidence_refs=refs,
        tools_used=["validate_citations"],
    )


def final_reviewer_agent(agent_results: list[AgentResult]) -> AgentResult:
    if any(result.verdict == "fail" for result in agent_results):
        verdict = "fail"
        message = "At least one verification agent failed; clinician review is required before use."
    elif any(result.verdict == "warning" for result in agent_results):
        verdict = "warning"
        message = "No agent failed, but warnings remain and should be reviewed by a clinician."
    else:
        verdict = "pass"
        message = "All verification agents passed for this MVP check."

    return AgentResult(
        agent_name="final_reviewer_agent",
        verdict=verdict,
        message=message,
        evidence_refs=[],
    )


def _case_payload(
    agent_name: str,
    request: VerificationRequest,
    response: RecommendationResponse,
    context: GraphRAGContextResponse,
) -> dict:
    retrieval = {
        "sources": context.retrieval_sources,
        "graph_facts": len(context.graph_facts),
        "evidence_chunks": len(context.evidence_chunks),
    }
    if agent_name == "evidence_agent":
        return {
            "patient_summary": response.patient_summary,
            "recommendation_statuses": [
                {"drug_class": item.drug_class, "status": item.status}
                for item in response.recommendations
            ],
            "retrieval": retrieval,
            "evidence_pack": {
                "chunks": [
                    {
                        "chunk_id": chunk.chunk_id,
                        "document_id": chunk.document_id,
                        "section": chunk.section,
                        "text": chunk.text[:220],
                        "score": chunk.score,
                    }
                    for chunk in context.evidence_chunks[:2]
                ],
                "graph_facts": [fact.model_dump(mode="json") for fact in context.graph_facts[:2]],
            },
        }
    if agent_name == "guideline_alignment_agent":
        return {
            "overall_status": response.overall_status,
            "constraints": [item.model_dump(mode="json") for item in response.constraints],
            "recommendations": [
                {
                    "drug_class": item.drug_class,
                    "status": item.status,
                    "rationale": item.rationale,
                }
                for item in response.recommendations
            ],
            "retrieval": retrieval,
            "guideline_pack": {
                "evidence_refs": _evidence_refs(response)[:6],
                "chunks": [
                    {
                        "chunk_id": chunk.chunk_id,
                        "document_id": chunk.document_id,
                        "section": chunk.section,
                        "text": chunk.text[:180],
                    }
                    for chunk in context.evidence_chunks[:2]
                ],
            },
        }
    return {
        "patient_summary": response.patient_summary,
        "risk_flags": [item.model_dump(mode="json") for item in response.risk_flags],
        "constraints": [item.model_dump(mode="json") for item in response.constraints],
        "recommendation_statuses": [
            {
                "drug_class": item.drug_class,
                "status": item.status,
            }
            for item in response.recommendations
        ],
        "retrieval": retrieval,
    }


def _guardrail_result(llm_result: AgentResult, fallback: AgentResult) -> AgentResult:
    if VERDICT_SEVERITY[llm_result.verdict] >= VERDICT_SEVERITY[fallback.verdict]:
        return llm_result
    return AgentResult(
        agent_name=llm_result.agent_name,
        verdict=fallback.verdict,
        message=f"{llm_result.message} Deterministic safety guardrail preserved: {fallback.message}",
        evidence_refs=sorted(set(llm_result.evidence_refs + fallback.evidence_refs)),
        execution_mode="llm_agent_with_rule_guardrail",
        model=llm_result.model,
        tools_used=llm_result.tools_used,
    )


def _final_reviewer_guardrail(llm_result: AgentResult, fallback: AgentResult) -> AgentResult:
    if llm_result.verdict == fallback.verdict:
        return llm_result
    return AgentResult(
        agent_name=llm_result.agent_name,
        verdict=fallback.verdict,
        message=f"{llm_result.message} Final severity normalized to specialist results: {fallback.message}",
        evidence_refs=sorted(set(llm_result.evidence_refs + fallback.evidence_refs)),
        execution_mode="llm_agent_with_rule_guardrail",
        model=llm_result.model,
        tools_used=llm_result.tools_used,
    )


async def _run_agent_or_fallback(
    agent_name: str,
    fallback: AgentResult,
    request: VerificationRequest,
    response: RecommendationResponse,
    context: GraphRAGContextResponse,
    prior_results: list[AgentResult] | None = None,
) -> AgentResult:
    if settings.verification_agent_mode.lower().strip() not in {"llm", "hybrid"}:
        return fallback

    tools = build_agent_tools(request, response, context, prior_results)
    allowed_tools = (
        [tools[name] for name in AGENT_TOOL_NAMES[agent_name]]
        if settings.verification_agent_tool_mode.lower().strip() == "tool_calling"
        else []
    )
    try:
        llm_result = await run_llm_agent(
            agent_name,
            _case_payload(agent_name, request, response, context),
            allowed_tools,
        )
        if agent_name == "final_reviewer_agent":
            return _final_reviewer_guardrail(llm_result, fallback)
        return _guardrail_result(llm_result, fallback)
    except Exception as exc:
        logger.warning("%s LLM execution failed; using deterministic fallback: %s", agent_name, exc)
        return fallback.model_copy(
            update={
                "execution_mode": "rule_based_fallback",
                "model": settings.verification_agent_model or settings.llm_model,
            }
        )


def _llm_agent_names() -> set[str]:
    return {
        name.strip()
        for name in settings.verification_agent_llm_agents.split(",")
        if name.strip()
    }


def _cache_key(request: VerificationRequest) -> str:
    payload = {
        "request": request.model_dump(mode="json"),
        "mode": settings.verification_agent_mode,
        "model": settings.verification_agent_model or settings.llm_model,
        "agents": sorted(_llm_agent_names()),
        "tool_mode": settings.verification_agent_tool_mode,
        "top_k": settings.verification_retrieval_top_k,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _read_cache(key: str) -> VerificationResponse | None:
    if not settings.verification_cache_enabled:
        return None
    with _cache_lock:
        cached = _verification_cache.get(key)
        if not cached or cached[0] <= time.monotonic():
            _verification_cache.pop(key, None)
            return None
        return cached[1].model_copy(deep=True)


def _write_cache(key: str, response: VerificationResponse) -> None:
    if not settings.verification_cache_enabled:
        return
    with _cache_lock:
        if len(_verification_cache) >= settings.verification_cache_max_entries:
            oldest_key = min(_verification_cache, key=lambda item: _verification_cache[item][0])
            _verification_cache.pop(oldest_key, None)
        _verification_cache[key] = (
            time.monotonic() + settings.verification_cache_ttl_seconds,
            response.model_copy(deep=True),
        )


async def verify_recommendation(
    request: VerificationRequest,
    *,
    prefetched_context: GraphRAGContextResponse | None = None,
) -> VerificationResponse:
    cache_key = _cache_key(request)
    cached = _read_cache(cache_key)
    if cached:
        return cached

    response = request.recommendation or build_recommendation(RecommendationRequest(patient=request.patient))
    if prefetched_context is not None:
        context = prefetched_context
    else:
        context = await build_graphrag_context_async(
            GraphRAGContextRequest(
                patient=request.patient,
                query=(
                    request.query
                    or request.patient.care_context.clinician_question
                    or request.patient.care_context.decision_context
                ),
                top_k=max(1, min(settings.verification_retrieval_top_k, 16)),
                conversation_history=request.conversation_history,
                clinical_state=request.clinical_state,
            )
        )

    citation_validation = validate_citations(response, context, patient=request.patient)

    fallbacks: list[tuple[str, AgentResult]] = [
        ("safety_agent", safety_agent(response)),
        ("missing_data_agent", missing_data_agent(response)),
        ("evidence_agent", evidence_agent(request, response, context)),
        ("guideline_alignment_agent", guideline_alignment_agent(response)),
        (
            "citation_validator_agent",
            citation_validator_agent(
                response,
                context,
                patient=request.patient,
                citation_validation=citation_validation,
            ),
        ),
    ]

    llm_agents = _llm_agent_names()
    tasks = [
        _run_agent_or_fallback(agent_name, fallback, request, response, context)
        if agent_name in llm_agents
        else asyncio.sleep(0, result=fallback)
        for agent_name, fallback in fallbacks
    ]
    agent_results = list(await asyncio.gather(*tasks))

    final_fallback = final_reviewer_agent(agent_results)
    if "final_reviewer_agent" in llm_agents:
        final_result = await _run_agent_or_fallback(
            "final_reviewer_agent", final_fallback, request, response, context, agent_results
        )
    else:
        final_result = final_fallback
    agent_results.append(final_result)

    enriched_response, prioritized_context = attach_linked_evidence(response, context, citation_validation)
    _ = apply_citation_guardrails(enriched_response, citation_validation)

    result = VerificationResponse(
        case_id=request.patient.case_id,
        context=prioritized_context,
        agent_results=agent_results,
        final_verdict=agent_results[-1].verdict,
        citation_validation=citation_validation,
    )
    _write_cache(cache_key, result)
    return result
