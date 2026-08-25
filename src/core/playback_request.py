"""Immutable request contract at the content/playback boundary.

This module carries business importance and lifecycle metadata.  It does not
inspect live conversation state, decide whether playback is allowed, or invoke
TTS.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from src.core.presentation_delivery import VoiceDeliveryItem
from src.core.presentation_intent import MessageKind, MessagePriority
from src.core.voice_delivery import MAX_ITEM_CHARS


@dataclass(frozen=True)
class PlaybackRequest:
    """A voice-qualified item enriched with scheduling lifecycle metadata."""

    intent_id: str
    kind: MessageKind
    priority: MessagePriority
    voice_text: str
    created_at: datetime
    ttl: timedelta
    source_block_id: str | None = None
    supersession_key: str | None = None
    max_chars: int = MAX_ITEM_CHARS
    speech_rate: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.intent_id, str) or not self.intent_id.strip():
            raise ValueError("intent_id 不能为空。")
        if not isinstance(self.kind, MessageKind):
            raise TypeError("kind 必须是 MessageKind。")
        if not isinstance(self.priority, MessagePriority):
            raise TypeError("priority 必须是 MessagePriority。")
        if not isinstance(self.voice_text, str) or not self.voice_text.strip():
            raise ValueError("voice_text 必须是非空字符串。")
        if not isinstance(self.max_chars, int) or isinstance(self.max_chars, bool):
            raise TypeError("max_chars 必须是正整数。")
        if self.max_chars <= 0:
            raise ValueError("max_chars 必须是正整数。")
        if len(self.voice_text) > self.max_chars:
            raise ValueError(f"voice_text 不能超过 {self.max_chars} 字。")
        if not isinstance(self.speech_rate, (int, float)) or isinstance(self.speech_rate, bool):
            raise TypeError("speech_rate 必须是数字。")
        if not 0.5 <= float(self.speech_rate) <= 2.0:
            raise ValueError("speech_rate 必须在 0.5 到 2.0 之间。")
        object.__setattr__(self, "speech_rate", float(self.speech_rate))
        source_block_id = self.source_block_id or f"intent:{self.intent_id}"
        if not isinstance(source_block_id, str) or not source_block_id.strip():
            raise ValueError("source_block_id 必须是非空字符串。")
        object.__setattr__(self, "source_block_id", source_block_id)
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at 必须是 datetime。")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at 必须包含时区。")
        if not isinstance(self.ttl, timedelta):
            raise TypeError("ttl 必须是 timedelta。")
        if self.ttl <= timedelta(0):
            raise ValueError("ttl 必须大于 0。")
        if self.supersession_key is not None and (
            not isinstance(self.supersession_key, str)
            or not self.supersession_key.strip()
        ):
            raise ValueError("supersession_key 必须是非空字符串或 None。")

    @property
    def expires_at(self) -> datetime:
        """Return the deterministic expiry boundary; no clock is read here."""

        return self.created_at + self.ttl

    @classmethod
    def from_delivery_item(
        cls,
        item: VoiceDeliveryItem,
        *,
        created_at: datetime,
        ttl: timedelta,
        supersession_key: str | None = None,
    ) -> "PlaybackRequest":
        """Add lifecycle metadata where a qualified item enters playback."""

        if not isinstance(item, VoiceDeliveryItem):
            raise TypeError("item 必须是 VoiceDeliveryItem。")
        return cls(
            intent_id=item.intent_id,
            kind=item.kind,
            priority=item.priority,
            voice_text=item.voice_text,
            source_block_id=item.source_block_id,
            created_at=created_at,
            ttl=ttl,
            supersession_key=supersession_key,
            max_chars=item.max_chars,
            speech_rate=item.speech_rate,
        )
