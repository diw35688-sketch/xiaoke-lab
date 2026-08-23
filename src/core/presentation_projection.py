"""呈现投影：把业务事实翻译成呈现意图（纯函数，无副作用）。

投影层只读业务结果、产出语义意图，不打印、不改状态、不产中文——
中文由文案目录按 kind + args 生成。这是"业务事实 → 语义意图 → 文案"
三段的中间一段。
"""

from __future__ import annotations

from src.core.presentation_copy import (
    ConfirmationAckResult,
    ProgramStatus,
    RecordAckResult,
    ReviewItem,
)
from src.core.presentation_intent import (
    MessageKind,
    MessagePriority,
    PresentationIntent,
    ScreenTarget,
)
from src.core.unified_observer import (
    UnifiedObservation,
    UnifiedObservationStatus,
)
from src.core.unified_segment_processor import PendingClarificationSummary

_END_CONFIRMATION_QUESTION = '是否结束本次实验记录？（请说"是的"或"不是"）'


def messages_for_program_status(
    status: ProgramStatus,
    *,
    request_id: str,
) -> tuple[PresentationIntent, ...]:
    """把程序生命周期状态投影为一条用户反馈。"""

    return (
        PresentationIntent(
            intent_id=f"{request_id}-program-status",
            kind=MessageKind.PROGRAM_STATUS,
            args={"status": status},
            priority=MessagePriority.DIRECT_ACK,
            screen_target=ScreenTarget.STATUS,
        ),
    )


def messages_for_wake_ack(
    keyword: str,
    *,
    request_id: str,
) -> tuple[PresentationIntent, ...]:
    """把唤醒检测结果投影为一条用户反馈。"""

    return (
        PresentationIntent(
            intent_id=f"{request_id}-wake",
            kind=MessageKind.WAKE_ACK,
            args={"keyword": keyword},
            priority=MessagePriority.DIRECT_ACK,
            screen_target=ScreenTarget.STATUS,
        ),
    )


def messages_for_observation(
    observation: UnifiedObservation,
    *,
    experiment_step_number: int | None = None,
) -> tuple[PresentationIntent, ...]:
    """把一段口述的观察摘要翻译成呈现意图（零条或多条）。

    experiment_step_number 仅在 structured_experiment 时使用；
    非实验段（降级/失败/追问/命令）传 None。

    部分观察（partial=True，web 降级生产者产出）走独立分支：
    有追问文本 → 一条 CLARIFICATION；无追问 → 一条降级 RECORD_ACK。
    CLI 完整观察（partial=False）不受影响，走下方既有逻辑。
    """

    if observation.status == UnifiedObservationStatus.FAILED:
        return (_record_ack(observation, RecordAckResult.FAILED),)

    if observation.partial:
        if observation.partial_question:
            return (_clarification(observation, observation.partial_question),)
        # 无追问时区分：结构化成功（partial_recorded）→ 已记录；真降级 → 不可用
        result = (
            RecordAckResult.RECORDED_NO_STEP
            if observation.acceptance_kind == "partial_recorded"
            else RecordAckResult.DEGRADED
        )
        return (_record_ack(observation, result),)

    messages: list[PresentationIntent] = []
    if observation.acceptance_kind == "degraded_evidence_note":
        messages.append(_record_ack(observation, RecordAckResult.DEGRADED))
    elif observation.acceptance_kind == "structured_experiment":
        messages.append(
            _record_ack(
                observation,
                RecordAckResult.RECORDED,
                experiment_step_number,
            )
        )

    action = observation.clarification_action
    if observation.executed:
        pending = observation.pending_action
        if action == "create" and pending is not None:
            messages.append(_clarification(observation, pending.question))
        elif action == "answer" and pending is not None:
            messages.append(
                _confirmation_ack(
                    observation,
                    ConfirmationAckResult.ANSWERED,
                    display_number=pending.target_display_number,
                    remaining_fields=observation.answer_remaining_fields,
                    resolved=observation.answer_resolved,
                )
            )
        elif action == "confirm" and pending is not None:
            messages.append(
                _confirmation_ack(
                    observation,
                    ConfirmationAckResult.CONFIRMED,
                    display_number=pending.target_display_number,
                    remaining_fields=observation.answer_remaining_fields,
                    resolved=observation.answer_resolved,
                )
            )
        elif action == "defer" and pending is not None:
            messages.append(
                _deferred(observation, pending.target_display_number)
            )
    elif action == "no_action":
        if (
            observation.acceptance_kind is None
            and not observation.end_confirmation_requested
            and observation.destination != "abstention"
        ):
            messages.append(_no_action_feedback(observation))

    if observation.end_confirmation_requested:
        messages.append(
            _clarification(observation, _END_CONFIRMATION_QUESTION)
        )

    if (
        observation.destination == "abstention"
        and observation.clarification_action == "no_action"
    ):
        messages.append(
            PresentationIntent(
                intent_id=f"{observation.request_id}-no-action-feedback",
                kind=MessageKind.SYSTEM_ISSUE,
                args={"text": "没听清，请再说。"},
                priority=MessagePriority.DIRECT_ACK,
                screen_target=ScreenTarget.DIALOGUE,
                source_segment_id=observation.segment_id,
            )
        )

    return tuple(messages)


def messages_for_review(
    summary: tuple[PendingClarificationSummary, ...],
    *,
    request_id: str,
) -> tuple[PresentationIntent, ...]:
    """把查看动作的待确认快照翻译成一条查看意图。"""

    items = tuple(
        ReviewItem(
            display_number=item.display_number,
            is_deferred=item.is_deferred,
            question=item.question,
        )
        for item in summary
    )
    return (
        PresentationIntent(
            intent_id=f"{request_id}-review",
            kind=MessageKind.CLARIFICATION_REVIEW,
            args={"items": items},
            priority=MessagePriority.REVIEW,
            screen_target=ScreenTarget.DIALOGUE,
        ),
    )


def _record_ack(
    observation: UnifiedObservation,
    result: RecordAckResult,
    step_number: int | None = None,
) -> PresentationIntent:
    args: dict[str, object] = {"result": result}
    if step_number is not None:
        args["step_number"] = step_number
    return PresentationIntent(
        intent_id=f"{observation.request_id}-record",
        kind=MessageKind.RECORD_ACK,
        args=args,
        priority=MessagePriority.ROUTINE,
        screen_target=ScreenTarget.STATUS,
        source_segment_id=observation.segment_id,
    )


def _clarification(
    observation: UnifiedObservation,
    question: str,
) -> PresentationIntent:
    return PresentationIntent(
        intent_id=f"{observation.request_id}-clarification",
        kind=MessageKind.CLARIFICATION,
        args={"question": question},
        priority=MessagePriority.ACTIVE_QUESTION,
        screen_target=ScreenTarget.CURRENT_QUESTION,
        source_segment_id=observation.segment_id,
    )


def _confirmation_ack(
    observation: UnifiedObservation,
    result: ConfirmationAckResult,
    *,
    display_number: int | None,
    remaining_fields: tuple[str, ...] = (),
    resolved: bool = False,
) -> PresentationIntent:
    args: dict[str, object] = {
        "result": result,
        "display_number": display_number,
    }
    if result in {
        ConfirmationAckResult.ANSWERED,
        ConfirmationAckResult.CONFIRMED,
    }:
        args["remaining_fields"] = remaining_fields
        args["resolved"] = resolved
    return PresentationIntent(
        intent_id=f"{observation.request_id}-ack",
        kind=MessageKind.CONFIRMATION_ACK,
        args=args,
        priority=MessagePriority.DIRECT_ACK,
        screen_target=ScreenTarget.STATUS,
        source_segment_id=observation.segment_id,
    )


def _no_action_feedback(
    observation: UnifiedObservation,
) -> PresentationIntent:
    return PresentationIntent(
        intent_id=f"{observation.request_id}-no-action",
        kind=MessageKind.NO_ACTION_FEEDBACK,
        args={"reason": observation.execution_reason or ""},
        priority=MessagePriority.DIRECT_ACK,
        screen_target=ScreenTarget.DIALOGUE,
        source_segment_id=observation.segment_id,
    )


def _deferred(
    observation: UnifiedObservation,
    display_number: int | None,
) -> PresentationIntent:
    return PresentationIntent(
        intent_id=f"{observation.request_id}-defer",
        kind=MessageKind.CLARIFICATION_DEFERRED,
        args={"display_number": display_number},
        priority=MessagePriority.DIRECT_ACK,
        screen_target=ScreenTarget.STATUS,
        source_segment_id=observation.segment_id,
    )
