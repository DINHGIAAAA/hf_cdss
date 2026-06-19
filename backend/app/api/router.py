from fastapi import APIRouter

from app.api.routes import (
    audit,
    auth,
    chat,
    clinical_pipeline,
    evidence,
    graphrag,
    health,
    knowledge_graph,
    llm,
    medication_safety,
    metrics,
    recommendation,
    retrieval,
)
from app.api.routes.admin import constraint_rules_router


api_router = APIRouter()
api_router.include_router(health.router, tags=["system"])
api_router.include_router(clinical_pipeline.router, tags=["clinical-pipeline"])
api_router.include_router(clinical_pipeline.legacy_router, tags=["clinical-pipeline"])
api_router.include_router(recommendation.router, tags=["recommendation"])
api_router.include_router(medication_safety.router, tags=["medication-safety"])
api_router.include_router(evidence.router, tags=["evidence"])
api_router.include_router(knowledge_graph.router, tags=["knowledge-graph"])
api_router.include_router(retrieval.router, tags=["retrieval"])
api_router.include_router(graphrag.router, tags=["graphrag"])
api_router.include_router(llm.router, tags=["llm"])
api_router.include_router(audit.router, tags=["audit"])
api_router.include_router(chat.router, tags=["chat"])
api_router.include_router(metrics.router, tags=["metrics"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(constraint_rules_router, prefix="/admin", tags=["admin"])
