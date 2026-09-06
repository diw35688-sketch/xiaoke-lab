import json
from typing import Any

from .schemas import (
    ExperimentEntities,
    ExperimentEvent,
    ExperimentEventType,
    ExperimentSummary,
    LLMAnalysisResult,
)


class LLMOutputValidationError(ValueError):
    """模型输出不满足稳定业务协议。"""


ANALYSIS_FIELDS = {
    "events", "should_ask_follow_up", "follow_up_question", "assistant_reply"
}
EVENT_FIELDS = {
    "event_type", "raw_text", "normalized_text", "entities", "missing_fields",
    "needs_confirmation", "confirmation_reason"
}
ENTITY_FIELDS = {
    "action", "object", "instrument", "amount_value", "amount_unit",
    "concentration", "temperature", "duration", "condition", "observation"
}
SUMMARY_FIELDS = {
    "summary", "completed_steps", "key_observations", "anomalies",
    "unresolved_questions"
}


def _load_object(content: str) -> dict[str, Any]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as error:
        raise LLMOutputValidationError("输出不是合法 JSON") from error
    if not isinstance(data, dict):
        raise LLMOutputValidationError("JSON 顶层必须是对象")
    return data


def _require_exact_fields(data: dict, expected: set[str], location: str) -> None:
    actual = set(data)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise LLMOutputValidationError(
            f"{location} 字段不匹配；缺少={missing}，额外={extra}"
        )


def _nullable_string(value: Any, field_name: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise LLMOutputValidationError(f"{field_name} 必须是字符串或 null")
    return value


def parse_analysis(
    content: str,
    *,
    expected_raw_text: str,
    session_id: str,
    segment_id: int,
) -> LLMAnalysisResult:
    data = _load_object(content)
    _require_exact_fields(data, ANALYSIS_FIELDS, "顶层")
    if not isinstance(data["events"], list) or not data["events"]:
        raise LLMOutputValidationError("events 必须是非空数组")
    if not isinstance(data["should_ask_follow_up"], bool):
        raise LLMOutputValidationError("should_ask_follow_up 必须是布尔值")
    follow_up = _nullable_string(data["follow_up_question"], "follow_up_question")
    reply = _nullable_string(data["assistant_reply"], "assistant_reply")

    events: list[ExperimentEvent] = []
    requires_follow_up = False
    for index, raw_event in enumerate(data["events"]):
        if not isinstance(raw_event, dict):
            raise LLMOutputValidationError(f"events[{index}] 必须是对象")
        _require_exact_fields(raw_event, EVENT_FIELDS, f"events[{index}]")
        try:
            event_type = ExperimentEventType(raw_event["event_type"])
        except (ValueError, TypeError) as error:
            raise LLMOutputValidationError(f"events[{index}].event_type 无效") from error
        if raw_event["raw_text"] != expected_raw_text:
            raise LLMOutputValidationError(f"events[{index}].raw_text 与 ASR 原文不一致")
        if not isinstance(raw_event["normalized_text"], str) or not raw_event["normalized_text"].strip():
            raise LLMOutputValidationError(f"events[{index}].normalized_text 必须是非空字符串")
        raw_entities = raw_event["entities"]
        if not isinstance(raw_entities, dict):
            raise LLMOutputValidationError(f"events[{index}].entities 必须是对象")
        _require_exact_fields(raw_entities, ENTITY_FIELDS, f"events[{index}].entities")
        entities = {
            key: _nullable_string(value, f"events[{index}].entities.{key}")
            for key, value in raw_entities.items()
        }
        missing = raw_event["missing_fields"]
        if not isinstance(missing, list) or any(not isinstance(item, str) or not item for item in missing):
            raise LLMOutputValidationError(f"events[{index}].missing_fields 必须是非空字符串数组")
        if len(missing) != len(set(missing)):
            raise LLMOutputValidationError(f"events[{index}].missing_fields 不得重复")
        if not isinstance(raw_event["needs_confirmation"], bool):
            raise LLMOutputValidationError(f"events[{index}].needs_confirmation 必须是布尔值")
        reason = _nullable_string(raw_event["confirmation_reason"], "confirmation_reason")
        if raw_event["needs_confirmation"] and not reason:
            raise LLMOutputValidationError("需要确认时 confirmation_reason 不能为空")
        if not raw_event["needs_confirmation"] and reason is not None:
            raise LLMOutputValidationError("无需确认时 confirmation_reason 必须为 null")
        # 兼容模型可能仍对 ordinary missing_fields 给出追问；是否创建待确认问题
        # 仍由确定性协议策略决定，这里只保证解析不因追问标志而崩溃。
        requires_follow_up |= bool(missing) or raw_event["needs_confirmation"]
        events.append(ExperimentEvent(
            event_type=event_type,
            raw_text=expected_raw_text,
            normalized_text=raw_event["normalized_text"],
            entities=ExperimentEntities(**entities),
            missing_fields=missing,
            needs_confirmation=raw_event["needs_confirmation"],
            confirmation_reason=reason,
            source_session_id=session_id,
            source_segment_id=segment_id,
        ))

    if data["should_ask_follow_up"] != requires_follow_up:
        raise LLMOutputValidationError("追问标志与缺失字段/确认标志不一致")
    if requires_follow_up and (not follow_up or not follow_up.strip()):
        raise LLMOutputValidationError("需要追问时 follow_up_question 不能为空")
    if not requires_follow_up and follow_up is not None:
        raise LLMOutputValidationError("无需追问时 follow_up_question 必须为 null")
    return LLMAnalysisResult(events, requires_follow_up, follow_up, reply)


def parse_summary(content: str) -> ExperimentSummary:
    data = _load_object(content)
    _require_exact_fields(data, SUMMARY_FIELDS, "总结")
    if not isinstance(data["summary"], str) or not data["summary"].strip():
        raise LLMOutputValidationError("summary 必须是非空字符串")
    for field_name in SUMMARY_FIELDS - {"summary"}:
        value = data[field_name]
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise LLMOutputValidationError(f"{field_name} 必须是字符串数组")
    return ExperimentSummary(**data)
