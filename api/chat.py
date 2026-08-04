from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from agent.core import ModelServiceError, run_agent
from database.crud import add_message, ensure_conversation, get_recent_messages

router = APIRouter(prefix="/chat", tags=["聊天"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=64)


@router.post("")
def chat(request: ChatRequest):
    conversation_id = ensure_conversation(request.conversation_id)
    add_message(conversation_id, "user", request.message)
    try:
        answer = run_agent(get_recent_messages(conversation_id), conversation_id)
        add_message(conversation_id, "assistant", answer)
        return {"answer": answer, "conversation_id": conversation_id}
    except ModelServiceError as error:
        raise HTTPException(error.status_code, error.detail) from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
