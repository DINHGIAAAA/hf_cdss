from fastapi import APIRouter
from starlette.responses import StreamingResponse
import json
import logging

from app.modules.chat.service import get_chat_history, process_chat, stream_chat
from app.schemas.chat import ChatHistoryResponse, ChatRequest, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    return await process_chat(payload)


async def _stream_chat_guarded(payload: ChatRequest):
    # Without this, an exception raised mid-generator (e.g. during confirm/merge
    # handling) truncates the SSE stream with no "done" or "error" event, and the
    # client silently shows a blank assistant bubble forever.
    try:
        async for chunk in stream_chat(payload):
            yield chunk
    except Exception as exc:  # noqa: BLE001
        logger.exception("chat/stream failed for conversation_id=%s", payload.conversation_id)
        yield f"event: error\ndata: {json.dumps({'message': str(exc) or type(exc).__name__})}\n\n"


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest) -> StreamingResponse:
    logger.info(f"chat/stream received: message='{payload.message}', confirmation_action='{payload.confirmation_action}'")
    return StreamingResponse(
        _stream_chat_guarded(payload),
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
