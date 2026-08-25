import json
import uuid
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent.core import ModelServiceError, refine_chat_answer, run_agent, stream_agent
from database.crud import add_message, ensure_conversation, get_messages, get_recent_messages, latest_conversation
from realtime.routing import acknowledgement, requires_background_task
from stream_contract import agent_output_event, screen_delta_event
from tool_presentation import ToolVoiceDeliveryBatch
from src.core.conversation_turn import ExperimentContext, InteractionMode
from src.core.presentation_delivery import VoiceDeliveryItem, bind_voice_items
from src.core.presentation_intent import (
    MessageKind,
    MessagePriority,
)
from playback_runtime import web_playback_service
from mode_snapshot import ModeSnapshotFields
from output_policy import OutputStrategy, select_output_policy
from src.core.spoken_output import build_spoken_block_plan, select_spoken_output_policy
from tasks.task_manager import task_manager

router = APIRouter(prefix="/chat", tags=["聊天"])


class ChatRequest(ModeSnapshotFields):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=64)


def _queue_if_needed(request, conversation_id):
    if not requires_background_task(request.message):
        return None
    task = task_manager.submit(conversation_id, request.message)
    return task, acknowledgement(task["id"])


def _require_chat_policy(request: ChatRequest):
    policy = select_output_policy(
        request.interaction_mode, request.experiment_context
    )
    if policy.strategy != OutputStrategy.CHAT:
        raise HTTPException(
            status_code=409,
            detail="实验记录模式必须进入记录策略，不能交给自由聊天处理。",
        )
    return policy


def _build_chat_spoken_delivery(answer: str, turn_id: str) -> VoiceDeliveryItem:
    """Bind ordinary Chat screen text and TTS to one exact visible Block."""

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
    )


def _prepare_chat_spoken_delivery(
    answer: str, turn_id: str
) -> tuple[str, VoiceDeliveryItem]:
    """Return one publishable Chat answer, regenerating instead of truncating."""

    try:
        return answer, _build_chat_spoken_delivery(answer, turn_id)
    except ValueError as error:
        if "超过估算上限" not in str(error):
            raise
    refined = refine_chat_answer(answer, max_chars=50)
    return refined, _build_chat_spoken_delivery(refined, turn_id)



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
    _require_chat_policy(request)
    conversation_id = ensure_conversation(request.conversation_id)
    add_message(conversation_id, "user", request.message)
    queued = _queue_if_needed(request, conversation_id)
    if queued:
        task, answer = queued
        return {"answer": answer, "conversation_id": conversation_id, "background_task": task}
    try:
        answer = run_agent(
            get_recent_messages(conversation_id), conversation_id,
            request.interaction_mode,
        )
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
    _require_chat_policy(request)
    conversation_id = ensure_conversation(request.conversation_id)
    add_message(conversation_id, "user", request.message)
    queued = _queue_if_needed(request, conversation_id)
    spoken_turn_id = request.turn_id or f"conversation:{conversation_id}"
    assistant_block_id = f"{spoken_turn_id}:spoken"

    def events():
        if queued:
            task, answer = queued
            payload = {"type": "task_queued", "answer": answer, "conversation_id": conversation_id, "task": task}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            return
        answer_parts = []
        tool_voice_items = []
        try:
            for output in stream_agent(
                get_recent_messages(conversation_id), conversation_id,
                request.interaction_mode,
            ):
                payload = agent_output_event(output)
                if isinstance(output, ToolVoiceDeliveryBatch):
                    tool_voice_items.extend(output.items)
                    continue
                text = output
                clean_text = _clean_stream_text(text)
                if clean_text:
                    answer_parts.append(clean_text)
                else:
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            answer = "".join(answer_parts) or "模型没有返回文字内容。"
            # 普通 Chat 先完整验证可见正文，再发布唯一 screen Block；语音只从
            # 同一正文派生。这样模型超预算时不会先显示长文再偷偷少读。
            reply_item = None
            if not tool_voice_items and answer_parts:
                answer, reply_item = _prepare_chat_spoken_delivery(
                    answer, spoken_turn_id
                )
            yield f"data: {json.dumps(screen_delta_event(answer), ensure_ascii=False)}\n\n"
            if tool_voice_items:
                for authorized in web_playback_service.authorize(
                    bind_voice_items(tool_voice_items, assistant_block_id),
                    conversation_id=conversation_id,
                ):
                    yield f"data: {json.dumps(authorized, ensure_ascii=False)}\n\n"
            elif reply_item is not None:
                for authorized in web_playback_service.authorize(
                    (reply_item,), conversation_id=conversation_id
                ):
                    yield f"data: {json.dumps(authorized, ensure_ascii=False)}\n\n"
            add_message(conversation_id, "assistant", answer)
            yield f"data: {json.dumps({'type': 'done', 'answer': answer, 'conversation_id': conversation_id}, ensure_ascii=False)}\n\n"
        except ModelServiceError as error:
            yield f"data: {json.dumps({'type': 'error', 'detail': error.detail}, ensure_ascii=False)}\n\n"
        except ValueError as error:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(error)}, ensure_ascii=False)}\n\n"
        except Exception:
            yield f"data: {json.dumps({'type': 'error', 'detail': '流式回复中断，请重试。'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
