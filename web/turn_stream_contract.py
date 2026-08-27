"""Stable SSE envelope for the unified Web Turn endpoints."""
from __future__ import annotations

import json
from typing import Mapping


TURN_STATUS_PHASES = frozenset({
    "audio_saved",
    "asr",
    "dispatching",
    "understanding",
    "validating",
    "saving",
})


def sse_event(payload: Mapping[str, object]) -> str:
    if not isinstance(payload, Mapping) or not payload.get("type"):
        raise ValueError("SSE payload 必须包含 type。")
    return "data: " + json.dumps(
        dict(payload), ensure_ascii=False, separators=(",", ":")
    ) + "\n\n"


def turn_accepted_event(
    *, conversation_id: str, request_id: str, turn_id: str, replayed: bool
) -> dict[str, object]:
    return {
        "type": "turn_accepted",
        "conversation_id": conversation_id,
        "request_id": request_id,
        "turn_id": turn_id,
        "replayed": replayed,
    }


def turn_status_event(
    phase: str, text: str, *, elapsed_ms: int | None = None
) -> dict[str, object]:
    if phase not in TURN_STATUS_PHASES:
        raise ValueError(f"未知 Turn 状态阶段：{phase}")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Turn 状态文案不能为空。")
    event: dict[str, object] = {
        "type": "turn_status", "phase": phase, "text": text
    }
    if elapsed_ms is not None:
        event["elapsed_ms"] = int(elapsed_ms)
    return event


def turn_error_event(
    code: str, detail: str, *, retryable: bool
) -> dict[str, object]:
    if not code or not detail:
        raise ValueError("Turn 错误必须包含 code 和 detail。")
    return {
        "type": "turn_error",
        "code": code,
        "detail": detail,
        "retryable": bool(retryable),
    }
