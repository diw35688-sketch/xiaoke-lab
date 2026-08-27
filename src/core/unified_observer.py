"""把统一采用链安全地接到主流程观察位。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from src.asr.schemas import ASRResult
from src.core.clarification_acceptance import (
    ClarificationAction,
    ClarificationContextSnapshot,
)
from src.core.reply_coordinator import ReplyCoordinator
from src.core.unified_acceptance_bypass import (
    UnifiedAcceptanceBypass,
    UnifiedAcceptanceBypassInput,
)

if TYPE_CHECKING:
    from src.core.experiment_acceptance import AcceptedExperimentAnalysis


class UnifiedObservationStatus(str, Enum):
    OBSERVED = "observed"
    FAILED = "failed"


@dataclass(frozen=True)
class UnifiedObservation:
    """不含口述正文或模型原始响应的观察摘要。

    accepted_analysis 是可选的完整分析快照，
    供主流程在统一链路活跃时直接用于事件落盘，
    避免旧链路再次调用 LLM 产生重复分析。

    partial / partial_question 是"部分观察"通道（web 降级生产者使用）：
    partial=True 时放宽 OBSERVED 校验（不再强制 destination /
    clarification_action），追问文本走 partial_question 直接透传；
    CLI 完整路径不传 partial（默认 False），校验与行为零变化。
    """

    request_id: str
    session_id: str
    segment_id: int
    status: UnifiedObservationStatus
    destination: str | None = None
    permission: str | None = None
    acceptance_kind: str | None = None
    clarification_action: str | None = None
    missing_fields: tuple[str, ...] = ()
    follow_up_required: bool | None = None
    error_type: str | None = None
    executed: bool = False
    execution_reason: str | None = None
    accepted_analysis: (
        AcceptedExperimentAnalysis | None
    ) = None
    pending_action: ClarificationAction | None = None
    end_confirmation_requested: bool = False
    end_session_execution_requested: bool = False
    answer_remaining_fields: tuple[str, ...] = ()
    answer_resolved: bool = False
    partial: bool = False
    partial_question: str | None = None

    def __post_init__(self) -> None:
        if self.partial:
            if self.status != UnifiedObservationStatus.OBSERVED:
                raise ValueError("部分观察只能是成功观察。")
            if self.error_type is not None:
                raise ValueError("部分成功观察不能携带错误。")
            if (
                self.partial_question is not None
                and not self.partial_question.strip()
            ):
                raise ValueError("部分观察的追问文本不能是空白。")
            return
        if self.partial_question is not None:
            raise ValueError("追问文本仅允许部分观察携带。")
        if self.status == UnifiedObservationStatus.OBSERVED:
            if self.destination is None or self.clarification_action is None:
                raise ValueError("成功观察必须包含目标和澄清动作。")
            if self.error_type is not None:
                raise ValueError("成功观察不能携带错误。")
        elif self.error_type is None:
            raise ValueError("失败观察必须包含错误类型。")

    @property
    def is_experiment_evidence(self) -> bool:
        """是否产生可入库的实验分析证据（含降级 NOTE）。

        只有结构化实验或降级证据 NOTE 才算实验段；
        查看、暂缓、弃权、失败观察都不算，避免计数虚高。
        """

        return self.acceptance_kind in {
            "structured_experiment",
            "degraded_evidence_note",
        }


class UnifiedObserver:
    """观察统一链路的施工单；配置执行器后可真实修改协调器。"""

    def __init__(
        self,
        bypass: UnifiedAcceptanceBypass,
    ) -> None:
        self._bypass = bypass

    def observe(
        self,
        *,
        request_id: str,
        session_id: str,
        segment_id: int,
        asr_result: ASRResult | None,
        reply_coordinator: ReplyCoordinator,
        recent_context: tuple[str, ...] = (),
        raw_text: str | None = None,
    ) -> UnifiedObservation:
        try:
            snapshot = ClarificationContextSnapshot(
                unresolved=reply_coordinator.active_clarifications(),
                current_clarification_id=(
                    reply_coordinator.current_clarification().clarification_id
                    if reply_coordinator.current_clarification() is not None
                    else None
                ),
            )
            result = self._bypass.inspect(UnifiedAcceptanceBypassInput(
                request_id=request_id,
                session_id=session_id,
                segment_id=segment_id,
                asr_result=asr_result,
                clarification_context=snapshot,
                recent_context=recent_context,
                raw_text=raw_text,
            ))
            plan = result.execution_request.plan
            accepted = result.accepted_experiment
            analysis = (
                accepted.materialize_analysis()
                if accepted is not None
                else None
            )
            missing_fields = tuple(dict.fromkeys(
                field_name
                for event in (analysis.events if analysis else ())
                for field_name in event.missing_fields
            ))

            action = result.clarification_action

            return UnifiedObservation(
                request_id=request_id,
                session_id=session_id,
                segment_id=segment_id,
                status=UnifiedObservationStatus.OBSERVED,
                destination=plan.destination.value,
                permission=plan.permission.value,
                acceptance_kind=(accepted.kind.value if accepted else None),
                clarification_action=result.clarification_action.action_type.value,
                missing_fields=missing_fields,
                follow_up_required=(
                    analysis.should_ask_follow_up
                    if analysis is not None
                    else None
                ),
                accepted_analysis=accepted,
                pending_action=action,
                end_confirmation_requested=(
                    result.end_confirmation_requested
                ),
                end_session_execution_requested=(
                    getattr(result, "end_session_execution_requested", False)
                ),
            )
        except Exception as error:
            return UnifiedObservation(
                request_id=request_id,
                session_id=session_id,
                segment_id=segment_id,
                status=UnifiedObservationStatus.FAILED,
                error_type=type(error).__name__,
            )
