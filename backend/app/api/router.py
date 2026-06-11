from fastapi import APIRouter

from app.api.routes import audit, chat, clinical_pipeline, evidence, graphrag, health, llm, medication_safety, recommendation


api_router = APIRouter()
api_router.include_router(health.router, tags=["system"])
api_router.include_router(clinical_pipeline.router, tags=["clinical-pipeline"])
api_router.include_router(recommendation.router, tags=["recommendation"])
api_router.include_router(medication_safety.router, tags=["medication-safety"])
api_router.include_router(evidence.router, tags=["evidence"])
api_router.include_router(graphrag.router, tags=["graphrag"])
api_router.include_router(llm.router, tags=["llm"])
api_router.include_router(audit.router, tags=["audit"])
api_router.include_router(chat.router, tags=["chat"])
