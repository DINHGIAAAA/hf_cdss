from fastapi import APIRouter
from starlette.responses import StreamingResponse
import logging

from app.modules.chat.service import get_chat_history, process_chat, stream_chat
from app.schemas.chat import ChatHistoryResponse, ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    return await process_chat(payload)


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest) -> StreamingResponse:
    logger.info(f"chat/stream received: message='{payload.message}', confirmation_action='{payload.confirmation_action}'")
    return StreamingResponse(
        stream_chat(payload),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chat/{conversation_id}/history", response_model=ChatHistoryResponse)
def chat_history(conversation_id: str) -> ChatHistoryResponse:
    messages, draft = get_chat_history(conversation_id)
    return ChatHistoryResponse(conversation_id=conversation_id, messages=messages, patient_draft=draft)
