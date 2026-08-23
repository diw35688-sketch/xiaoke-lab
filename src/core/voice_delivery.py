"""Deterministic pre-TTS policy for short, controlled voice output."""

from __future__ import annotations

import re
from collections.abc import Sequence

from src.core.presentation_intent import MessageKind, PresentationIntent

MAX_VOICE_ITEMS = 2
MAX_VOICE_CHARS = 50
MAX_ITEM_CHARS = 25

_SPEAKABLE_KINDS = frozenset({
    MessageKind.WAKE_ACK,
    MessageKind.CLARIFICATION,
    MessageKind.CONFIRMATION_ACK,
    MessageKind.SAFETY_ALERT,
    MessageKind.SYSTEM_ISSUE,
    MessageKind.SESSION_CLOSING_SUMMARY,
})
_CODE_BLOCK = re.compile(r"```[\s\S]*?```")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_MARKDOWN = re.compile(r"[*_`#>|~\[\]{}]")
_SENTENCE = re.compile(r"[^。！？!?\n]+[。！？!?]?")


def constrain_voice_text(text: str, *, max_chars: int = MAX_ITEM_CHARS) -> str:
    """Remove non-speech content, choose the first sentence, and hard-truncate."""

    cleaned = _CODE_BLOCK.sub("", text)
    cleaned = _URL.sub("", cleaned)
    cleaned = _MARKDOWN.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    sentences = [part.strip() for part in _SENTENCE.findall(cleaned) if part.strip()]
    selected = sentences[0] if sentences else cleaned
    if len(selected) <= max_chars:
        return selected
    suffix = "？" if selected.endswith(("？", "?")) else "。"
    return selected[: max_chars - 1].rstrip("，,；;：:。！？!?") + suffix


def voice_text_for_intent(intent: PresentationIntent, text: str) -> str | None:
    """Return constrained speech or None when policy makes the intent silent."""

    if intent.kind not in _SPEAKABLE_KINDS:
        return None
    constrained = constrain_voice_text(text)
    return constrained or None


def apply_turn_budget(
    items: Sequence[tuple[PresentationIntent, str | None]],
) -> tuple[str | None, ...]:
    """Enforce at most two items, fifty chars, and one question per turn."""

    result: list[str | None] = []
    used_items = used_chars = used_questions = 0
    for intent, text in items:
        accepted: str | None = None
        is_question = intent.kind == MessageKind.CLARIFICATION
        if (
            text
            and used_items < MAX_VOICE_ITEMS
            and used_chars + len(text) <= MAX_VOICE_CHARS
            and (not is_question or used_questions == 0)
        ):
            accepted = text
            used_items += 1
            used_chars += len(text)
            used_questions += int(is_question)
        result.append(accepted)
    return tuple(result)
