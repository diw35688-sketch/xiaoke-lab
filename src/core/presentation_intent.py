"""呈现意图合同：描述系统想表达什么，不包含最终展示文案。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from types import MappingProxyType
from typing import Mapping


class MessageKind(str, Enum):
    """消息表达的业务含义，而不是界面颜色或控件类型。"""

    WAKE_ACK = "wake_ack"
    PROGRAM_STATUS = "program_status"
    TRANSCRIPT = "transcript"
    RECORD_ACK = "record_ack"
    CONFIRMATION_ACK = "confirmation_ack"
    NO_ACTION_FEEDBACK = "no_action_feedback"
    CLARIFICATION = "clarification"
    CLARIFICATION_DEFERRED = "clarification_deferred"
    CLARIFICATION_REVIEW = "clarification_review"
    SAFETY_ALERT = "safety_alert"
    SYSTEM_ISSUE = "system_issue"
    STAGE_SUMMARY = "stage_summary"
    SESSION_CLOSING_SUMMARY = "session_closing_summary"
    ASSISTANT_REPLY = "assistant_reply"
    DEBUG = "debug"


class MessagePriority(IntEnum):
    """数值越小，越应该优先交给用户。"""

    CRITICAL = 0
    DIRECT_ACK = 10
    ACTIVE_QUESTION = 20
    REVIEW = 30
    SUMMARY = 40
    ROUTINE = 50
    DEBUG = 100


class ScreenTarget(str, Enum):
    """前端的语义区域；具体颜色和布局仍由前端决定。"""

    DIALOGUE = "dialogue"
    CURRENT_QUESTION = "current_question"
    RECORD_TIMELINE = "record_timeline"
    STATUS = "status"
    ALERT = "alert"
    SUMMARY = "summary"


@dataclass(frozen=True)
class PresentationIntent:
    """交给呈现层的不可变语义意图。"""

    intent_id: str
    kind: MessageKind
    args: Mapping[str, object]
    priority: MessagePriority
    screen_target: ScreenTarget
    source_segment_id: int | None = None
    clarification_id: str | None = None

    def __post_init__(self) -> None:
        if not self.intent_id.strip():
            raise ValueError("intent_id 不能为空。")
        if self.kind == MessageKind.DEBUG:
            raise ValueError("DEBUG 信息必须走 logging，不能成为呈现意图。")
        if self.source_segment_id is not None and self.source_segment_id <= 0:
            raise ValueError("source_segment_id 必须大于 0。")

        copied_args = dict(self.args)
        if any(not isinstance(key, str) or not key.strip() for key in copied_args):
            raise ValueError("args 的键必须是非空字符串。")

        object.__setattr__(
            self,
            "args",
            MappingProxyType(copied_args),
        )
