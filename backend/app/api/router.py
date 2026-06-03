from fastapi import APIRouter

from app.api.routes import clinical_pipeline, health, recommendation


api_router = APIRouter()
api_router.include_router(health.router, tags=["system"])
api_router.include_router(clinical_pipeline.router, tags=["clinical-pipeline"])
api_router.include_router(recommendation.router, tags=["recommendation"])
