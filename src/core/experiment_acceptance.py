"""把统一理解候选验收为可交给持久化适配器的正式结果。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

from src.core.unified_dispatch import (
    UnifiedDispatchDestination,
    UnifiedDispatchPermission,
)
from src.core.unified_dispatch_execution import DispatchExecutionRequest
from src.llm.processor import ProcessOutcome
from src.llm.schemas import ExperimentEventType, LLMAnalysisResult
from src.llm.validation import parse_analysis


class ExperimentAcceptanceKind(str, Enum):
    """被采用数据的可信用途。"""

    STRUCTURED_EXPERIMENT = "structured_experiment"
    DEGRADED_EVIDENCE_NOTE = "degraded_evidence_note"


@dataclass(frozen=True)
class AcceptedExperimentAnalysis:
    """已验收的不可变分析快照；不是一次新的模型调用。"""

    request_id: str
    session_id: str
    segment_id: int
    asr_transcript: str
    kind: ExperimentAcceptanceKind
    analysis_json: str
    event_count: int
    degraded: bool
    error: str | None
    llm_attempts: int
    llm_processing_seconds: float

    def __post_init__(self) -> None:
        if not self.request_id.strip() or not self.session_id.strip():
            raise ValueError("采用结果身份不能为空。")
        if self.segment_id <= 0 or isinstance(self.segment_id, bool):
            raise ValueError("segment_id必须是正整数。")
        if not self.asr_transcript.strip():
            raise ValueError("asr_transcript不能为空。")
        if self.event_count <= 0 or isinstance(self.event_count, bool):
            raise ValueError("event_count必须是正整数。")
        if self.llm_attempts < 0 or isinstance(self.llm_attempts, bool):
            raise ValueError("llm_attempts不能为负数。")
        if self.llm_processing_seconds < 0:
            raise ValueError("llm_processing_seconds不能为负数。")
        if self.degraded != (
            self.kind == ExperimentAcceptanceKind.DEGRADED_EVIDENCE_NOTE
        ):
            raise ValueError("采用类型与降级标志不一致。")
        if self.degraded and not self.error:
            raise ValueError("降级采用必须保留错误原因。")
        if not self.degraded and self.error is not None:
            raise ValueError("正常采用不能携带降级错误。")

        analysis = self.materialize_analysis()
        if len(analysis.events) != self.event_count:
            raise ValueError("event_count与规范分析快照不一致。")
        _validate_event_sources(
            analysis,
            transcript=self.asr_transcript,
            session_id=self.session_id,
            segment_id=self.segment_id,
        )
        if self.degraded:
            _validate_degraded_note(analysis, self.asr_transcript)

    def materialize_analysis(self) -> LLMAnalysisResult:
        """从不可变快照严格生成新的旧链路分析对象。"""

        return parse_analysis(
            self.analysis_json,
            expected_raw_text=self.asr_transcript,
            session_id=self.session_id,
            segment_id=self.segment_id,
        )

    def to_process_outcome(self) -> ProcessOutcome[LLMAnalysisResult]:
        """供旧存储边界过渡使用；只解析快照，不调用LLM。"""

        return ProcessOutcome(
            value=self.materialize_analysis(),
            degraded=self.degraded,
            error=self.error,
            llm_attempts=self.llm_attempts,
            llm_processing_seconds=self.llm_processing_seconds,
        )


class ExperimentCandidateAcceptor:
    """纯验收器：没有LLM、存储、上下文或状态依赖。"""

    @classmethod
    def accept(
        cls,
        request: DispatchExecutionRequest,
    ) -> AcceptedExperimentAnalysis:
        route = request.plan.route_result
        outcome = route.understanding_outcome
        if outcome is None:
            raise ValueError("实验采用必须来自统一理解结果。")
        understanding = outcome.value
        if understanding.experiment is None:
            raise ValueError("实验采用请求缺少experiment理解分支。")
        if understanding.raw_text != request.raw_text:
            raise ValueError("统一理解原文与可信输入原文不一致。")

        if outcome.degraded:
            cls._validate_degraded_dispatch(request, outcome.error)
            kind = ExperimentAcceptanceKind.DEGRADED_EVIDENCE_NOTE
        else:
            cls._validate_normal_dispatch(request, outcome.error)
            kind = ExperimentAcceptanceKind.STRUCTURED_EXPERIMENT

        analysis = understanding.experiment.analysis
        if not analysis.events:
            raise ValueError("实验采用候选至少需要一个事件。")
        _validate_event_sources(
            analysis,
            transcript=request.raw_text,
            session_id=request.session_id,
            segment_id=request.segment_id,
        )
        if outcome.degraded:
            _validate_degraded_note(
                analysis,
                request.raw_text,
            )
        elif _looks_like_degraded_note(
            analysis,
            request.raw_text,
        ):
            raise ValueError("降级NOTE不能伪装成正常实验采用。")

        analysis_json = json.dumps(
            _analysis_payload_without_trusted_sources(analysis),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return AcceptedExperimentAnalysis(
            request_id=request.request_id,
            session_id=request.session_id,
            segment_id=request.segment_id,
            asr_transcript=request.raw_text,
            kind=kind,
            analysis_json=analysis_json,
            event_count=len(analysis.events),
            degraded=outcome.degraded,
            error=outcome.error,
            llm_attempts=outcome.llm_attempts,
            llm_processing_seconds=outcome.llm_processing_seconds,
        )

    @staticmethod
    def _validate_normal_dispatch(
        request: DispatchExecutionRequest,
        error: str | None,
    ) -> None:
        if (
            request.destination
            != UnifiedDispatchDestination.EXPERIMENT_PIPELINE
            or request.permission
            != UnifiedDispatchPermission.FORWARD_EXPERIMENT_ANALYSIS
        ):
            raise ValueError("正常实验只能从实验分派目标和权限采用。")
        if error is not None:
            raise ValueError("非降级统一理解不能携带错误。")

    @staticmethod
    def _validate_degraded_dispatch(
        request: DispatchExecutionRequest,
        error: str | None,
    ) -> None:
        if (
            request.destination != UnifiedDispatchDestination.DEGRADED_NOTE
            or request.permission
            != UnifiedDispatchPermission.FORWARD_DEGRADED_NOTE
        ):
            raise ValueError("降级结果只能从degraded_note目标采用。")
        if not error:
            raise ValueError("降级统一理解必须保留错误原因。")


def _validate_event_sources(
    analysis: LLMAnalysisResult,
    *,
    transcript: str,
    session_id: str,
    segment_id: int,
) -> None:
    for index, event in enumerate(analysis.events, start=1):
        if event.raw_text != transcript:
            raise ValueError(f"事件{index}原文与ASR证据不一致。")
        if event.source_session_id != session_id:
            raise ValueError(f"事件{index}的session来源不一致。")
        if event.source_segment_id != segment_id:
            raise ValueError(f"事件{index}的segment来源不一致。")


def _validate_degraded_note(
    analysis: LLMAnalysisResult,
    transcript: str,
) -> None:
    if len(analysis.events) != 1:
        raise ValueError("降级采用必须且只能包含一个保真NOTE。")
    event = analysis.events[0]
    if event.event_type != ExperimentEventType.NOTE:
        raise ValueError("降级采用只能包含NOTE事件。")
    if event.normalized_text != transcript:
        raise ValueError("降级NOTE不能改写ASR忠实转写。")
    if not event.needs_confirmation:
        raise ValueError("降级NOTE必须标记需要确认。")


def _looks_like_degraded_note(
    analysis: LLMAnalysisResult,
    transcript: str,
) -> bool:
    if len(analysis.events) != 1:
        return False
    event = analysis.events[0]
    return (
        event.event_type == ExperimentEventType.NOTE
        and event.raw_text == transcript
        and event.normalized_text == transcript
        and event.needs_confirmation
        and bool(event.confirmation_reason)
        and event.confirmation_reason.startswith("统一理解失败：")
    )


def _analysis_payload_without_trusted_sources(
    analysis: LLMAnalysisResult,
) -> dict:
    """构造可重新严格解析的业务快照；来源身份由程序重新注入。"""

    payload = analysis.to_dict()
    for event in payload["events"]:
        event.pop("source_session_id", None)
        event.pop("source_segment_id", None)
    return payload
