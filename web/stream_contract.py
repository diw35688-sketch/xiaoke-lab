# -*- coding: utf-8 -*-
"""`/chat/stream` 的屏幕/语音分离事件合同。

本模块只定义和校验 SSE payload，不负责调用模型、选择业务文案或播放 TTS。
`screen_delta` 永远只上屏；`voice_delivery` 既可表达通过内容政策的候选，
也可承载 PlaybackScheduler 已签发的 READY/DEFERRED/DROP 运行时决定。
"""

from __future__ import annotations

from typing import Iterable

from src.core.presentation_delivery import VoiceDeliveryItem
from tool_presentation import ToolVoiceDeliveryBatch


def screen_delta_event(text: str) -> dict:
    """构造只允许上屏的流式正文事件。"""

    if not isinstance(text, str) or not text:
        raise ValueError("screen_delta 的 text 必须是非空字符串。")
    return {"type": "screen_delta", "text": text}


def agent_chunk_event(text: str) -> dict:
    """Map one agent chunk to its SSE contract during the control-marker migration.

    Ordinary assistant text is explicitly screen-only.  Legacy LABTHINK and
    LABCARD markers remain on the old delta channel until they receive their own
    structured event contracts; this function never grants them voice access.
    """

    if not isinstance(text, str) or not text:
        raise ValueError("agent chunk 必须是非空字符串。")
    if text.startswith("[[LABTHINK]]") or text.startswith("[[LABCARD]]"):
        return {"type": "delta", "text": text}
    return screen_delta_event(text)


def agent_output_event(output: str | ToolVoiceDeliveryBatch) -> dict:
    """Map one typed agent stream output to its SSE payload."""

    if isinstance(output, ToolVoiceDeliveryBatch):
        return voice_delivery_event(output.items)
    if isinstance(output, str):
        return agent_chunk_event(output)
    raise TypeError("agent stream output 类型不受支持。")


def voice_delivery_event(
    items: Iterable[VoiceDeliveryItem],
    *,
    authorization: str = "CONTENT_ELIGIBLE",
    reason: str | None = None,
) -> dict:
    """构造语音事件，并在 Web 边界校验授权枚举。

    这里不再对文本长度做“截断/丢弃”处理：长回复应该完整说完，
    不能因为 50 字/2 条等预算把话剪到一半。内容预算应在更早的策略层决定，
    而不是在 Web 边界把已经生成的语音内容扔掉。
    """

    batch = tuple(items)
    if not batch:
        raise ValueError("voice_delivery 至少需要一条语音。")

    allowed_authorizations = {
        "CONTENT_ELIGIBLE", "READY", "DEFERRED", "DROP", "PREEMPT"
    }
    if authorization not in allowed_authorizations:
        raise ValueError("voice_delivery authorization 不受支持。")
    event = {
        "type": "voice_delivery",
        "authorization": authorization,
        "items": [item.as_dict() for item in batch],
    }
    if reason is not None:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("voice_delivery reason 必须是非空字符串或 None。")
        event["reason"] = reason
    return event
