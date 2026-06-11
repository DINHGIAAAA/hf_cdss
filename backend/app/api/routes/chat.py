from fastapi import APIRouter

from app.modules.chat.service import get_chat_history, process_chat
from app.schemas.chat import ChatHistoryResponse, ChatRequest, ChatResponse


router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    return await process_chat(payload)


@router.get("/chat/{conversation_id}/history", response_model=ChatHistoryResponse)
def chat_history(conversation_id: str) -> ChatHistoryResponse:
    messages, draft = get_chat_history(conversation_id)
    return ChatHistoryResponse(conversation_id=conversation_id, messages=messages, patient_draft=draft)
