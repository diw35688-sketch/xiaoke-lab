"""Deterministic pre-TTS policy for short, controlled voice output."""

from __future__ import annotations

import re
from collections.abc import Sequence

from src.core.presentation_intent import MessageKind, PresentationIntent

MAX_VOICE_ITEMS = 1000
MAX_VOICE_CHARS = 100000
MAX_ITEM_CHARS = 100000

_SPEAKABLE_KINDS = frozenset({
    MessageKind.WAKE_ACK,
    MessageKind.CLARIFICATION,
    MessageKind.CONFIRMATION_ACK,
    MessageKind.SAFETY_ALERT,
    MessageKind.SYSTEM_ISSUE,
    MessageKind.SESSION_CLOSING_SUMMARY,
    MessageKind.ASSISTANT_REPLY,
})
_CODE_BLOCK = re.compile(r"```[\s\S]*?```")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_MARKDOWN = re.compile(r"[*_`#>|~\[\]{}]")
_SENTENCE = re.compile(r"[^。！？!?\n]+[。！？!?]?")


def constrain_voice_text(text: str, *, max_chars: int = MAX_ITEM_CHARS) -> str:
    """Remove non-speech content, keep the full reply.

    语音文本就是实际回复内容；只去掉不适合朗读的代码块/URL/多余空白，
    不再截断成第一句或短片段。要限制长度应限制模型输出，而不是播放时剪语音。
    """

    cleaned = _CODE_BLOCK.sub("", text)
    cleaned = _URL.sub("", cleaned)
    cleaned = _MARKDOWN.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars]


def voice_text_for_intent(
    intent: PresentationIntent,
    text: str,
    *,
    speak_record_ack: bool = False,
) -> str | None:
    """Return constrained speech or None when policy makes the intent silent."""

    successful_record_ack = (
        intent.kind == MessageKind.RECORD_ACK
        and intent.args.get("result") in {"recorded", "recorded_no_step"}
    )
    speakable = intent.kind in _SPEAKABLE_KINDS or (
        speak_record_ack and successful_record_ack
    )
    if not speakable:
        return None
    constrained = constrain_voice_text(text)
    return constrained or None


def apply_turn_budget(
    items: Sequence[tuple[PresentationIntent, str | None]],
) -> tuple[str | None, ...]:
    """Pass through all speakable text without dropping or truncating it.

    长回复完整交给语音播放；不做 50 字剪裁或“只留第一句”。
    """

    result: list[str | None] = []
    for _intent, text in items:
        result.append(text if text else None)
    return tuple(result)
