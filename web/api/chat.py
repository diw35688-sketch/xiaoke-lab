import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent.core import ModelServiceError, run_agent, stream_agent
from database.crud import (
    add_message,
    create_conversation,
    delete_conversation,
    ensure_conversation,
    get_messages,
    get_recent_messages,
    latest_conversation,
    list_conversations,
    rename_conversation,
)
from realtime.routing import acknowledgement, requires_background_task
from tasks.task_manager import task_manager

router = APIRouter(prefix="/chat", tags=["聊天"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=64)


class ConversationCreatePayload(BaseModel):
    title: str | None = Field(default=None, max_length=80)


class ConversationRenamePayload(BaseModel):
    title: str = Field(min_length=1, max_length=80)


def _queue_if_needed(request, conversation_id):
    if not requires_background_task(request.message):
        return None
    task = task_manager.submit(conversation_id, request.message)
    return task, acknowledgement(task["id"])


@router.get("/conversations")
def conversations():
    """会话列表：标题、更新时间、消息数和最后一条消息。"""
    return {"items": list_conversations(limit=100)}


@router.post("/conversations")
def new_conversation(payload: ConversationCreatePayload | None = None):
    """创建空会话；第一条用户消息会自动生成标题。"""
    conversation_id = create_conversation(
        title=(payload.title if payload else None) or "新会话"
    )
    return {"conversation_id": conversation_id}


@router.patch("/conversations/{conversation_id}")
def rename_conversation_api(
    conversation_id: str,
    payload: ConversationRenamePayload,
):
    if not rename_conversation(conversation_id, payload.title):
        raise HTTPException(status_code=404, detail="会话不存在。")
    return {"ok": True, "conversation_id": conversation_id, "title": payload.title}


@router.delete("/conversations/{conversation_id}")
def delete_conversation_api(conversation_id: str):
    if not delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="会话不存在。")
    return {"ok": True, "conversation_id": conversation_id}


@router.get("/history")
def chat_history(conversation_id: str | None = None):
    """页面刷新或切换会话后恢复该会话的显示历史。"""
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
    """保留前端展示标记，供历史记录重建思考/工具卡片。"""
    return text


@router.post("/stream")
def chat_stream(request: ChatRequest):
    conversation_id = ensure_conversation(request.conversation_id)
    add_message(conversation_id, "user", request.message)
    queued = _queue_if_needed(request, conversation_id)

    def events():
        if queued:
            task, answer = queued
            payload = {
                "type": "task_queued",
                "answer": answer,
                "conversation_id": conversation_id,
                "task": task,
            }
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

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
