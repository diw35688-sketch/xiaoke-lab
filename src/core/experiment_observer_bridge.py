"""把语音实验输入安全接到统一观察器的受控接线。"""

from __future__ import annotations

from src.core.experiment_turn_input import ExperimentTurnInput
from src.core.reply_coordinator import ReplyCoordinator
from src.core.session_context import SessionContext
from src.core.unified_observer import UnifiedObservation, UnifiedObserver
from src.core.unified_segment_processor import (
    SegmentJob,
    SegmentOutcome,
    UnifiedSegmentProcessor,
)


def observe_experiment_turn(
    turn: ExperimentTurnInput,
    *,
    session_id: str,
    segment_id: int,
    observer: UnifiedObserver,
    coordinator: ReplyCoordinator,
    context: SessionContext,
) -> UnifiedObservation:
    """把任意来源 ExperimentTurnInput 映射到统一观察器，只观察不执行。

    所有语义读取 turn.raw_text；文字不伪装成 ASR。
    session_id / segment_id 显式传入：输入合同里没有这两个字段，
    段号由调用方（未来语音流）分配。
    """

    return observer.observe(
        request_id=turn.request_id,
        session_id=session_id,
        segment_id=segment_id,
        asr_result=turn.asr_result,
        reply_coordinator=coordinator,
        recent_context=context.as_prompt_context(),
        raw_text=turn.raw_text,
    )


def process_experiment_turn(
    turn: ExperimentTurnInput,
    *,
    segment_id: int,
    processor: UnifiedSegmentProcessor,
) -> SegmentOutcome:
    """把一段语音 ExperimentTurnInput 交给六步流水线完整处理。

    观察、落盘、执行澄清动作都由 processor 内部完成；
    processor 由调用方装配并跨 turn 复用，以保持协调器/上下文状态。
    文字输入（asr_result=None）显式拒绝。
    """

    if turn.asr_result is None:
        raise ValueError("文字输入暂不接入统一观察器。")
    return processor.process(
        SegmentJob(segment_id=segment_id, asr_result=turn.asr_result)
    )
