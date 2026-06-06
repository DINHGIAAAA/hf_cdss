import asyncio

from fastapi import APIRouter

from app.modules.graphrag.service import build_graphrag_context
from app.modules.datastores.postgres import write_audit_event
from app.modules.verification_agents.service import verify_recommendation
from app.schemas.graphrag import (
    GraphRAGContextRequest,
    GraphRAGContextResponse,
    VerificationRequest,
    VerificationResponse,
)


router = APIRouter()


@router.post("/graphrag/context", response_model=GraphRAGContextResponse)
def graphrag_context(payload: GraphRAGContextRequest) -> GraphRAGContextResponse:
    return build_graphrag_context(payload)


@router.post("/verify", response_model=VerificationResponse)
async def verify(payload: VerificationRequest) -> VerificationResponse:
    response = await verify_recommendation(payload)
    await asyncio.to_thread(
        write_audit_event,
        response.case_id,
        "verification_completed",
        {
            "patient": payload.patient.model_dump(mode="json"),
            "verification": response.model_dump(mode="json"),
        },
    )
    return response
