import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent.core import ModelServiceError, run_agent, stream_agent
from database.crud import add_message, ensure_conversation, get_messages, get_recent_messages, latest_conversation
from realtime.routing import acknowledgement, requires_background_task
from tasks.task_manager import task_manager

router = APIRouter(prefix="/chat", tags=["聊天"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=64)


def _queue_if_needed(request, conversation_id):
    if not requires_background_task(request.message):
        return None
    task = task_manager.submit(conversation_id, request.message)
    return task, acknowledgement(task["id"])



@router.get("/history")
def chat_history(conversation_id: str | None = None):
    """页面刷新后恢复当前对话的显示历史。

    - 传 conversation_id：读取该会话的最近 100 条消息。
    - 不传：读取最近一次会话；没有任何会话时返回空列表。
    """
    target = conversation_id or latest_conversation()
    if target is None:
        return {"conversation_id": None, "messages": []}
    return {"conversation_id": target, "messages": get_messages(target, limit=100)}

@router.post("")
def chat(request: ChatRequest):
    conversation_id = ensure_conversation(request.conversation_id)
    add_message(conversation_id, "user", request.message)
    queued = _queue_if_needed(request, conversation_id)
    if queued:
        task, answer = queued
        return {"answer": answer, "conversation_id": conversation_id, "background_task": task}
    try:
        answer = run_agent(get_recent_messages(conversation_id), conversation_id)
        add_message(conversation_id, "assistant", answer)
        return {"answer": answer, "conversation_id": conversation_id}
    except ModelServiceError as error:
        raise HTTPException(error.status_code, error.detail) from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error




def _clean_stream_text(text: str) -> str:
    """把前端用于渲染的 [[LABTHINK]] / [[LABCARD]] 标记从正文中剥离。

    这些标记只应该用于前端流式展示，不能写进 messages 表；
    否则刷新历史时会把原始标记显示给用户。
    """
    if text.startswith("[[LABTHINK]]") or text.startswith("[[LABCARD]]"):
        return ""
    return text
@router.post("/stream")
def chat_stream(request: ChatRequest):
    conversation_id = ensure_conversation(request.conversation_id)
    add_message(conversation_id, "user", request.message)
    queued = _queue_if_needed(request, conversation_id)

    def events():
        if queued:
            task, answer = queued
            payload = {"type": "task_queued", "answer": answer, "conversation_id": conversation_id, "task": task}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            return
        answer_parts = []
        try:
            for text in stream_agent(get_recent_messages(conversation_id), conversation_id):
                clean_text = _clean_stream_text(text)
                if clean_text:
                    answer_parts.append(clean_text)
                yield f"data: {json.dumps({'type': 'delta', 'text': text}, ensure_ascii=False)}\n\n"
            answer = "".join(answer_parts) or "模型没有返回文字内容。"
            add_message(conversation_id, "assistant", answer)
            yield f"data: {json.dumps({'type': 'done', 'answer': answer, 'conversation_id': conversation_id}, ensure_ascii=False)}\n\n"
        except ModelServiceError as error:
            yield f"data: {json.dumps({'type': 'error', 'detail': error.detail}, ensure_ascii=False)}\n\n"
        except Exception:
            yield f"data: {json.dumps({'type': 'error', 'detail': '流式回复中断，请重试。'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
