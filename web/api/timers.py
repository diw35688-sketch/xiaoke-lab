# -*- coding: utf-8 -*-
"""实验计时器接口：创建、查询、取消、计时结束通知AI；前端轮询到点弹窗。"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import lab_tools
from api.auth import require_user

router = APIRouter(prefix="/timers", tags=["计时器"])


class TimerCreatePayload(BaseModel):
    duration_seconds: int = Field(gt=0, le=86400)
    label: str | None = Field(default=None, max_length=80)


class TimerAcceptPayload(BaseModel):
    label: str | None = Field(default=None, max_length=80)
    duration_seconds: int | None = Field(default=None, gt=0, le=86400)


@router.get("/active")
def active_timers(user=Depends(require_user)):
    return {"items": lab_tools.list_active_timers()}


@router.post("")
def create_timer(payload: TimerCreatePayload, user=Depends(require_user)):
    timer = lab_tools.create_timer(
        payload.duration_seconds, label=(payload.label or "").strip() or None
    )
    return {"ok": True, "timer": timer}


@router.post("/{timer_id}/accept")
def accept_timer(timer_id: str, payload: TimerAcceptPayload, user=Depends(require_user)):
    try:
        timer = lab_tools.accept_pending_timer(
            timer_id,
            label=(payload.label or "").strip() or None,
            duration_seconds=payload.duration_seconds,
        )
    except ValueError as error:
        raise HTTPException(status_code=404 if "没有找到" in str(error) else 400, detail=str(error)) from error
    return {"ok": True, "timer": timer}


@router.delete("/{timer_id}")
def cancel_timer(timer_id: str, user=Depends(require_user)):
    if not lab_tools.cancel_timer(timer_id):
        raise HTTPException(status_code=404, detail="计时器不存在。")
    return {"ok": True}


class TimerNotifyPayload(BaseModel):
    label: str | None = Field(default=None, max_length=80)
    duration_seconds: int | None = Field(default=None, gt=0)


@router.post("/{timer_id}/notify-ai")
def notify_ai(timer_id: str, payload: TimerNotifyPayload, user=Depends(require_user)):
    """计时结束后通知 AI 系统，让 AI 知道计时完成并可以推进下一步。

    优先通过语音网关注入（AI 会语音播报），无语音会话时走文字通道。
    """
    import json as _json
    import logging
    import urllib.request

    from database import user_store
    from database.crud import add_message, conversation_exists, get_messages, latest_conversation

    log = logging.getLogger(__name__)
    users = user_store.list_users()
    if not users:
        raise HTTPException(status_code=400, detail="还没有账号。")
    user_id = users[0]["id"]

    label = (payload.label or "").strip() or "计时器"
    duration_seconds = payload.duration_seconds or 0
    if duration_seconds >= 60:
        duration_text = f"{duration_seconds // 60}分钟"
    else:
        duration_text = f"{duration_seconds}秒"

    content = f"[计时结束] {label}（{duration_text}）的计时已经结束。"

    # 找到当前会话（优先使用语音会话）
    conversation_id = ""
    try:
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent.parent / "realtime"
        conversation_id = (root / "current-conversation-id.txt").read_text(encoding="utf-8").strip()
    except Exception:
        pass

    if not conversation_id or not conversation_exists(conversation_id, user_id):
        conversation_id = latest_conversation(user_id)
    if not conversation_id:
        raise HTTPException(status_code=400, detail="没有可用的会话。")

    # 强去重：60 秒内相同内容不重复提交
    try:
        recent = get_messages(conversation_id, limit=10)
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(seconds=60)
        for item in recent:
            if (
                item.get("role") == "user"
                and str(item.get("content") or "").strip() == content
                and item.get("created_at", "") >= str(cutoff)
            ):
                return {"ok": True, "deduplicated": True, "conversation_id": conversation_id}
    except Exception:
        pass

    # 策略 1：尝试通过语音网关注入（AI 语音播报）
    gateway_ok = False
    try:
        data = _json.dumps({"text": content}).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:3101/api/announce",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = _json.loads(resp.read().decode("utf-8"))
            gateway_ok = result.get("ok") is True
    except Exception as e:
        log.debug("Gateway announce failed (expected if no voice): %s", e)

    if gateway_ok:
        # 语音通道已处理，仅写入记录用于历史展示
        add_message(conversation_id, "user", content)
        return {"ok": True, "via": "voice", "conversation_id": conversation_id}

    # 策略 2：无语音会话，走文字通道（不加重复消息——turn 流程会自动写入）
    try:
        from api.chat import _submit_legacy_chat, ChatRequest

        request = ChatRequest(
            message=content,
            conversation_id=conversation_id,
            interaction_mode="experiment",
        )
        _submit_legacy_chat(request)
    except Exception as e:
        log.warning("Timer AI text notification failed: %s", e)
        # 确保消息至少落库
        add_message(conversation_id, "user", content)

    return {"ok": True, "via": "text", "conversation_id": conversation_id}
