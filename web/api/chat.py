import json
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import settings_store
from agent.core import ModelServiceError, refine_chat_answer
from api.auth import require_user
from database.crud import (
    conversation_exists,
    create_conversation,
    delete_conversation,
    get_messages,
    latest_conversation,
    list_conversations,
    rename_conversation,
)
from stream_contract import screen_delta_event
from src.core.conversation_turn import ExperimentContext, InteractionMode
from src.core.conversation_turn import InputSource
from src.core.turn_input import TurnInput
from src.core.presentation_delivery import VoiceDeliveryItem
from src.core.presentation_intent import MessageKind, MessagePriority
from src.core.spoken_output import build_spoken_block_plan, select_spoken_output_policy
from database.turn_store import TurnRequestConflictError
from playback_runtime import web_playback_service
from mode_snapshot import ModeSnapshotFields

router = APIRouter(prefix="/chat", tags=["聊天"])


class ChatRequest(ModeSnapshotFields):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=64)


class ConversationCreatePayload(BaseModel):
    title: str | None = Field(default=None, max_length=80)


class ConversationRenamePayload(BaseModel):
    title: str = Field(min_length=1, max_length=80)





@router.get("/conversations")
def conversations(user=Depends(require_user)):
    """会话列表：只返回当前登录用户自己的会话。"""
    return {"items": list_conversations(user["id"], limit=100)}


@router.post("/conversations")
def new_conversation(payload: ConversationCreatePayload | None = None,
                     user=Depends(require_user)):
    """创建空会话；第一条用户消息会自动生成标题。"""
    conversation_id = create_conversation(
        user["id"], title=(payload.title if payload else None) or "新会话"
    )
    return {"conversation_id": conversation_id}


@router.patch("/conversations/{conversation_id}")
def rename_conversation_api(
    conversation_id: str,
    payload: ConversationRenamePayload,
    user=Depends(require_user),
):
    # 不是自己的会话一律按「不存在」处理，不泄露它是否真的存在。
    if not rename_conversation(conversation_id, payload.title, user["id"]):
        raise HTTPException(status_code=404, detail="会话不存在。")
    return {"ok": True, "conversation_id": conversation_id, "title": payload.title}


@router.delete("/conversations/{conversation_id}")
def delete_conversation_api(conversation_id: str, user=Depends(require_user)):
    if not delete_conversation(conversation_id, user["id"]):
        raise HTTPException(status_code=404, detail="会话不存在。")
    return {"ok": True, "conversation_id": conversation_id}


def _build_chat_spoken_delivery(answer: str, turn_id: str) -> VoiceDeliveryItem:
    """Compatibility export for the former Chat producer's pure contract."""

    policy = select_spoken_output_policy(
        InteractionMode.CHAT, ExperimentContext.NONE
    )
    plan = build_spoken_block_plan(
        turn_id=turn_id,
        text=answer,
        intent_id=f"chat-reply-{uuid.uuid4().hex}",
        priority=MessagePriority.REVIEW,
        policy=policy,
    )
    return VoiceDeliveryItem(
        intent_id=plan.voice_block.intent_id or "",
        kind=MessageKind.ASSISTANT_REPLY,
        priority=plan.voice_block.priority or MessagePriority.REVIEW,
        voice_text=plan.voice_text,
        source_block_id=plan.source_block.block_id,
        max_chars=policy.estimated_max_chars or len(plan.voice_text),
        speech_rate=settings_store.current().tts_speed,
    )


def _prepare_chat_spoken_delivery(
    answer: str, turn_id: str
) -> tuple[str, VoiceDeliveryItem]:
    """Legacy voice delivery builder for the /chat compatibility adapter."""

    try:
        return answer, _build_chat_spoken_delivery(answer, turn_id)
    except ValueError as error:
        if "超过估算上限" not in str(error):
            raise
    refined = refine_chat_answer(answer, max_chars=50)
    return refined, _build_chat_spoken_delivery(refined, turn_id)


@router.get("/history")
def chat_history(conversation_id: str | None = None,
                 user=Depends(require_user)):
    """页面刷新后恢复当前对话的显示历史。

    - 传 conversation_id：读取该会话的最近 100 条消息。
    - 不传：读取最近一次会话；没有任何会话时返回空列表。
    """
    target = conversation_id or latest_conversation(user["id"])
    if target is not None and not conversation_exists(target, user["id"]):
        # 本地存着已删除、或属于别人的会话 ID 时，回到自己最近的有效会话。
        target = latest_conversation(user["id"])
    if target is None:
        return {"conversation_id": None, "messages": []}
    return {"conversation_id": target, "messages": get_messages(target, limit=100)}


@router.post("")
def chat(request: ChatRequest):
    try:
        completed, conversation_id = _submit_legacy_chat(request)
        answer = _assistant_text(completed.result)
        return {"answer": answer, "conversation_id": conversation_id}
    except ModelServiceError as error:
        raise HTTPException(error.status_code, error.detail) from error
    except TurnRequestConflictError as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(400, str(error)) from error


@router.post("/stream")
def chat_stream(request: ChatRequest):

    def events():
        try:
            completed, conversation_id = _submit_legacy_chat(request)
            answer = _assistant_text(completed.result)
            yield f"data: {json.dumps(screen_delta_event(answer), ensure_ascii=False)}\n\n"
            if not completed.replayed:
                for authorized in web_playback_service.authorize(
                    completed.voice_items, conversation_id=conversation_id
                ):
                    yield f"data: {json.dumps(authorized, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'answer': answer, 'conversation_id': conversation_id}, ensure_ascii=False)}\n\n"
        except ModelServiceError as error:
            yield f"data: {json.dumps({'type': 'error', 'detail': error.detail}, ensure_ascii=False)}\n\n"
        except TurnRequestConflictError as error:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(error)}, ensure_ascii=False)}\n\n"
        except ValueError as error:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(error)}, ensure_ascii=False)}\n\n"
        except Exception:
            yield f"data: {json.dumps({'type': 'error', 'detail': '流式回复中断，请重试。'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _resolve_legacy_lab_session_id() -> str:
    """Legacy /chat 没有 lab_session_id：优先读音频 agent 的当前会话，否则生成一个。"""
    try:
        root = Path(__file__).resolve().parent.parent / "_qwen-audio-agent"
        value = (root / "current-lab-session-id.txt").read_text(encoding="utf-8").strip()
        if value:
            return value
    except Exception:
        pass
    return f"lab-{uuid.uuid4().hex}"


def _resolve_legacy_experiment_context() -> ExperimentContext:
    """Legacy /chat 没有上下文：有激活方案就用方案实验，否则自由记录。"""
    try:
        import domain
        state = domain.session()
        if state is not None and state.selection.has_protocol:
            return ExperimentContext.PROTOCOL
    except Exception:
        pass
    return ExperimentContext.FREE


def _submit_legacy_chat(request: ChatRequest):
    """Compatibility adapter: old /chat HTTP shape → unified experiment Turn."""

    from api.turn import turn_application_service

    conversation_id = request.conversation_id or str(uuid.uuid4())
    request_id = request.request_id or f"legacy-chat-{uuid.uuid4().hex}"
    turn_id = request.turn_id or f"turn-{request_id}"
    turn = TurnInput(
        conversation_id, request_id, turn_id, _resolve_legacy_lab_session_id(),
        InteractionMode.EXPERIMENT, _resolve_legacy_experiment_context(),
        request.mode_version, InputSource.TEXT, request.message.strip(), None,
    )
    return turn_application_service.submit(turn).future.result(), conversation_id


def _assistant_text(result):
    for block in result.get("turn", {}).get("blocks", []):
        if block.get("type") == "assistant_text":
            return str(block.get("payload", {}).get("text") or "")
    return "模型没有返回文字内容。"
