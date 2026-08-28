"""Pure Turn/Block contract for the future single conversation timeline.

The objects in this module only validate and carry data.  They do not save
records, execute tools, mutate a store, schedule playback, or invoke TTS.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from src.core.presentation_intent import MessagePriority


class InteractionMode(str, Enum):
    CHAT = "chat"
    EXPERIMENT = "experiment"


class ExperimentContext(str, Enum):
    NONE = "none"
    FREE = "free"
    PROTOCOL = "protocol"
    TEMPLATE = "template"


class InputSource(str, Enum):
    TEXT = "text"
    SINGLE_RECORDING = "single_recording"
    CONTINUOUS_CALL = "continuous_call"


class BlockType(str, Enum):
    USER_TEXT = "user_text"
    ASSISTANT_TEXT = "assistant_text"
    PROTOCOL_CARD = "protocol_card"
    STEP_CARD = "step_card"
    SAFETY_ALERT = "safety_alert"
    RECORD_CARD = "record_card"
    TOOL_CARD = "tool_card"
    CONFIRMATION_CARD = "confirmation_card"
    SYSTEM_STATUS = "system_status"
    VOICE = "voice"


class TurnReplayDisposition(str, Enum):
    NEW_REQUEST = "new_request"
    IDEMPOTENT_REPLAY = "idempotent_replay"
    CONFLICT = "conflict"


class TurnReplayReason(str, Enum):
    DIFFERENT_REQUEST = "different_request"
    EXACT_MATCH = "exact_match"
    MODE_VERSION_CHANGED = "mode_version_changed"
    REQUEST_CONTENT_CHANGED = "request_content_changed"


def _require_id(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串。")


def _freeze_payload(value: object, path: str) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        copied: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"{path} 的键必须是非空字符串。")
            copied[key] = _freeze_payload(item, f"{path}.{key}")
        return MappingProxyType(copied)
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_payload(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    raise TypeError(f"{path} 只允许 JSON 可表示的数据。")


def _to_wire_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _to_wire_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_to_wire_value(item) for item in value]
    return value


@dataclass(frozen=True)
class ConversationBlock:
    """One typed unit in a turn; VOICE points at visible source content."""

    block_id: str
    type: BlockType
    payload: Mapping[str, object]
    source_block_id: str | None = None
    intent_id: str | None = None
    priority: MessagePriority | None = None

    def __post_init__(self) -> None:
        _require_id(self.block_id, "block_id")
        if not isinstance(self.type, BlockType):
            raise TypeError("type 必须是 BlockType。")
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload 必须是 Mapping。")
        object.__setattr__(self, "payload", _freeze_payload(self.payload, "payload"))

        voice_identity = (self.source_block_id, self.intent_id, self.priority)
        if self.type == BlockType.VOICE:
            _require_id(self.source_block_id, "source_block_id")
            _require_id(self.intent_id, "intent_id")
            if not isinstance(self.priority, MessagePriority):
                raise TypeError("VOICE block 的 priority 必须是 MessagePriority。")
            if self.payload:
                raise ValueError("VOICE block 不复制屏幕内容，payload 必须为空。")
        elif any(value is not None for value in voice_identity):
            raise ValueError("只有 VOICE block 可以携带语音身份字段。")

    def to_wire(self) -> dict[str, object]:
        result: dict[str, object] = {
            "block_id": self.block_id,
            "type": self.type.value,
            "payload": _to_wire_value(self.payload),
        }
        if self.type == BlockType.VOICE:
            result.update(
                source_block_id=self.source_block_id,
                intent_id=self.intent_id,
                priority=self.priority.value,
            )
        return result


@dataclass(frozen=True)
class ConversationTurn:
    """One traceable user turn with an immutable mode/source snapshot."""

    conversation_id: str
    request_id: str
    turn_id: str
    interaction_mode: InteractionMode
    experiment_context: ExperimentContext
    mode_version: int
    input_source: InputSource
    blocks: tuple[ConversationBlock, ...]

    def __post_init__(self) -> None:
        _require_id(self.conversation_id, "conversation_id")
        _require_id(self.request_id, "request_id")
        _require_id(self.turn_id, "turn_id")
        if not isinstance(self.interaction_mode, InteractionMode):
            raise TypeError("interaction_mode 必须是 InteractionMode。")
        if not isinstance(self.experiment_context, ExperimentContext):
            raise TypeError("experiment_context 必须是 ExperimentContext。")
        if not isinstance(self.input_source, InputSource):
            raise TypeError("input_source 必须是 InputSource。")
        if not isinstance(self.mode_version, int) or isinstance(self.mode_version, bool):
            raise TypeError("mode_version 必须是正整数。")
        if self.mode_version <= 0:
            raise ValueError("mode_version 必须是正整数。")
        if not isinstance(self.blocks, tuple) or not self.blocks:
            raise ValueError("blocks 必须是非空 tuple。")
        if any(not isinstance(block, ConversationBlock) for block in self.blocks):
            raise TypeError("blocks 只能包含 ConversationBlock。")

        if self.interaction_mode == InteractionMode.CHAT:
            if self.experiment_context != ExperimentContext.NONE:
                raise ValueError("chat 模式的 experiment_context 必须是 none。")
        elif self.experiment_context == ExperimentContext.NONE:
            raise ValueError("experiment 模式必须选择 free、protocol 或 template 上下文。")

        block_ids = [block.block_id for block in self.blocks]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("同一 turn 内 block_id 必须唯一。")
        source_types = {
            block.block_id: block.type
            for block in self.blocks
            if block.type != BlockType.VOICE
        }
        intent_ids: set[str] = set()
        for block in self.blocks:
            if block.type != BlockType.VOICE:
                continue
            if block.source_block_id not in source_types:
                raise ValueError("VOICE source_block_id 必须引用本 turn 的非语音 block。")
            if block.intent_id in intent_ids:
                raise ValueError("同一 turn 内 VOICE intent_id 必须唯一。")
            intent_ids.add(block.intent_id)

    def to_wire(self) -> dict[str, object]:
        return {
            "conversation_id": self.conversation_id,
            "request_id": self.request_id,
            "turn_id": self.turn_id,
            "interaction_mode": self.interaction_mode.value,
            "experiment_context": self.experiment_context.value,
            "mode_version": self.mode_version,
            "input_source": self.input_source.value,
            "blocks": [block.to_wire() for block in self.blocks],
        }


@dataclass(frozen=True)
class TurnReplayCheck:
    """Pure evidence for a future store's idempotency decision."""

    disposition: TurnReplayDisposition
    reason: TurnReplayReason


def decide_turn_replay(
    existing: ConversationTurn,
    candidate: ConversationTurn,
) -> TurnReplayCheck:
    """Compare two immutable requests without reading or changing a store."""

    if not isinstance(existing, ConversationTurn) or not isinstance(
        candidate, ConversationTurn
    ):
        raise TypeError("existing 和 candidate 必须是 ConversationTurn。")
    existing_key = (existing.conversation_id, existing.request_id)
    candidate_key = (candidate.conversation_id, candidate.request_id)
    if existing_key != candidate_key:
        return TurnReplayCheck(
            TurnReplayDisposition.NEW_REQUEST,
            TurnReplayReason.DIFFERENT_REQUEST,
        )
    if existing == candidate:
        return TurnReplayCheck(
            TurnReplayDisposition.IDEMPOTENT_REPLAY,
            TurnReplayReason.EXACT_MATCH,
        )
    if existing.mode_version != candidate.mode_version:
        return TurnReplayCheck(
            TurnReplayDisposition.CONFLICT,
            TurnReplayReason.MODE_VERSION_CHANGED,
        )
    return TurnReplayCheck(
        TurnReplayDisposition.CONFLICT,
        TurnReplayReason.REQUEST_CONTENT_CHANGED,
    )
