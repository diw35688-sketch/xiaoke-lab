"""Deterministic protocol navigation policy; no storage or LLM access."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from src.core.pending_clarification import ClarificationStatus, PendingClarification
from src.core.protocol_execution_state import (
    ProtocolExecutionState,
    ProtocolStepProgressStatus,
)


@dataclass(frozen=True)
class ProtocolMoveDecision:
    allowed: bool
    reason: str
    state: ProtocolExecutionState
    from_step_number: int
    target_step_number: int
    missing_fields: tuple[str, ...] = ()
    blocking_question_numbers: tuple[int, ...] = ()
    deferred_question_numbers: tuple[int, ...] = ()


def decide_protocol_move(
    *,
    state: ProtocolExecutionState,
    action: str,
    total_steps: int,
    evaluation: Mapping[str, object],
    unresolved: Sequence[PendingClarification],
    target_step_number: int | None = None,
) -> ProtocolMoveDecision:
    current = state.current_step_number
    if total_steps <= 0:
        raise ValueError("方案总步骤数必须为正整数。")

    if action == "prev":
        target = current - 1
        if target < 1:
            return _blocked(state, target, "已经是第一步。")
        return _allowed(state, target, state.statuses.get(
            current, ProtocolStepProgressStatus.IN_PROGRESS
        ), "已返回上一步。")

    if action == "jump":
        if target_step_number is None:
            raise ValueError("jump 必须包含目标步骤号。")
        target = int(target_step_number)
        if not 1 <= target <= total_steps:
            return _blocked(state, target, "目标步骤号超出方案范围。")
        if target == current:
            return _allowed(
                state, target,
                state.statuses.get(current, ProtocolStepProgressStatus.IN_PROGRESS),
                "已经位于目标步骤。",
            )
        if target < current:
            return _allowed(state, target, state.statuses.get(
                current, ProtocolStepProgressStatus.IN_PROGRESS
            ), "已返回指定步骤。")
        if target != current + 1:
            return _blocked(state, target, "不能直接跳过尚未依次处理的方案步骤。")
        action = "next"
    elif action == "next":
        target = current + 1
    else:
        raise ValueError("不支持的步骤操作：" + str(action))

    if target > total_steps:
        return _blocked(state, target, "已经是最后一步。")

    missing = tuple(str(item) for item in evaluation.get("missing_fields") or ())
    scoped = tuple(
        item for item in unresolved
        if item.protocol_id == state.protocol_id
        and item.protocol_version == state.protocol_version
        and item.protocol_step_number == current
    )
    active = tuple(
        item.display_number for item in scoped
        if item.status == ClarificationStatus.ACTIVE
    )
    deferred_items = tuple(
        item for item in scoped
        if item.status == ClarificationStatus.DEFERRED
    )
    deferred = tuple(item.display_number for item in deferred_items)

    # 方案执行以自然聊天为主：未回答的现场字段不阻断继续，保留在当前步骤状态中供之后补充。
    # active / uncovered 只作为状态信息返回，不再把“下一步”变成硬门槛。
    existing_status = state.statuses.get(
        current, ProtocolStepProgressStatus.IN_PROGRESS
    )
    manually_completed = existing_status == ProtocolStepProgressStatus.COMPLETED
    leaving_status = (
        ProtocolStepProgressStatus.COMPLETED
        if manually_completed
        else ProtocolStepProgressStatus.LEFT_WITH_PENDING
        if missing
        else ProtocolStepProgressStatus.COMPLETED
    )
    if manually_completed:
        reason = "当前步骤已确认完成，已进入下一步。"
        missing = ()
        deferred = ()
    elif missing and deferred:
        reason = "已带着暂缓问题进入下一步。"
    elif missing:
        reason = "当前步骤仍有未记录字段，已进入下一步。"
    else:
        reason = "当前步骤已完成，已进入下一步。"
    return _allowed(state, target, leaving_status, reason, missing, deferred)


def _allowed(
    state: ProtocolExecutionState,
    target: int,
    leaving_status: ProtocolStepProgressStatus,
    reason: str,
    missing: tuple[str, ...] = (),
    deferred: tuple[int, ...] = (),
) -> ProtocolMoveDecision:
    return ProtocolMoveDecision(
        True,
        reason,
        state.move_to(target, leaving_status=leaving_status),
        state.current_step_number,
        target,
        missing,
        (),
        deferred,
    )


def _blocked(
    state: ProtocolExecutionState, target: int, reason: str
) -> ProtocolMoveDecision:
    return ProtocolMoveDecision(
        False, reason, state, state.current_step_number, target
    )
