"""把统一路由、分派与采用合同串成无副作用集成旁路。"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.asr.schemas import ASRResult
from src.core.clarification_acceptance import (
    ClarificationAction,
    ClarificationActionPlanner,
    ClarificationContextSnapshot,
)
from src.core.experiment_acceptance import (
    AcceptedExperimentAnalysis,
    ExperimentCandidateAcceptor,
)
from src.core.unified_dispatch import UnifiedDispatchDestination
from src.core.unified_dispatch_execution import DispatchExecutionRequest
from src.core.task_context import TaskContext
from src.core.unified_understanding import UnifiedUnderstandingInput


@dataclass(frozen=True)
class UnifiedAcceptanceBypassInput:
    """固定集成旁路所需的可信证据、身份和只读上下文。"""

    request_id: str
    session_id: str
    segment_id: int
    asr_result: ASRResult | None
    clarification_context: ClarificationContextSnapshot
    session_active: bool = True
    recent_context: tuple[str, ...] = ()
    raw_text: str | None = None
    task_context: TaskContext = field(default_factory=TaskContext.free)

    def __post_init__(self) -> None:
        if not self.request_id.strip() or not self.session_id.strip():
            raise ValueError("旁路请求身份不能为空。")
        if self.segment_id <= 0 or isinstance(self.segment_id, bool):
            raise ValueError("segment_id必须是正整数。")
        raw_text = self.raw_text
        if raw_text is None and self.asr_result is not None:
            raw_text = self.asr_result.asr_transcript
            object.__setattr__(self, "raw_text", raw_text)
        if not isinstance(raw_text, str) or not raw_text.strip():
            raise ValueError("旁路原文不能为空。")
        if self.asr_result is not None:
            if not self.asr_result.is_final:
                raise ValueError("采用旁路只接受最终ASR证据。")
            if self.asr_result.asr_transcript != raw_text:
                raise ValueError("ASR证据与旁路原文不一致。")

    def to_understanding_input(self) -> UnifiedUnderstandingInput:
        numbers = tuple(
            item.display_number
            for item in self.clarification_context.unresolved
        )
        current = self.clarification_context.current
        return UnifiedUnderstandingInput(
            raw_text=self.raw_text,
            session_active=self.session_active,
            session_id=self.session_id,
            segment_id=self.segment_id,
            recent_context=self.recent_context,
            task_context=self.task_context,
            pending_question_numbers=numbers,
            current_question_number=(
                current.display_number if current is not None else None
            ),
        )


@dataclass(frozen=True)
class UnifiedAcceptanceBypassResult:
    """集成旁路结果；只有已采用数据和只读动作计划。"""

    execution_request: DispatchExecutionRequest
    accepted_experiment: AcceptedExperimentAnalysis | None
    clarification_action: ClarificationAction
    end_confirmation_requested: bool = False
    end_session_execution_requested: bool = False
    protocol_navigation_action: str | None = None

    def __post_init__(self) -> None:
        identities = {
            (
                self.execution_request.request_id,
                self.execution_request.session_id,
                self.execution_request.segment_id,
            ),
            (
                self.clarification_action.request_id,
                self.clarification_action.session_id,
                self.clarification_action.segment_id,
            ),
        }
        if self.accepted_experiment is not None:
            identities.add((
                self.accepted_experiment.request_id,
                self.accepted_experiment.session_id,
                self.accepted_experiment.segment_id,
            ))
        if len(identities) != 1:
            raise ValueError("采用旁路各阶段请求身份必须一致。")


class UnifiedAcceptanceBypass:
    """只编排纯合同，不依赖存储、状态机、协调器或TTS。"""

    def __init__(self, router) -> None:
        self._router = router

    def inspect(
        self,
        bypass_input: UnifiedAcceptanceBypassInput,
    ) -> UnifiedAcceptanceBypassResult:
        route = self._router.route(
            bypass_input.to_understanding_input()
        )
        from src.core.unified_dispatch import UnifiedDispatchPlanner

        plan = UnifiedDispatchPlanner.plan(route)
        request = DispatchExecutionRequest(
            request_id=bypass_input.request_id,
            session_id=bypass_input.session_id,
            segment_id=bypass_input.segment_id,
            asr_evidence=bypass_input.asr_result,
            plan=plan,
            raw_text=bypass_input.raw_text,
        )

        end_confirmation_requested = False
        end_session_execution_requested = False
        protocol_navigation_action = None
        if plan.destination in {
            UnifiedDispatchDestination.EXPERIMENT_PIPELINE,
            UnifiedDispatchDestination.DEGRADED_NOTE,
        }:
            accepted = ExperimentCandidateAcceptor.accept(request)
            action = ClarificationActionPlanner.from_experiment(accepted)
        elif plan.destination in {
            UnifiedDispatchDestination.CLARIFICATION_CONTEXT,
            UnifiedDispatchDestination.ABSTENTION,
        }:
            accepted = None
            action = ClarificationActionPlanner.from_dispatch(
                request,
                bypass_input.clarification_context,
            )
        elif (
            plan.destination
            == UnifiedDispatchDestination.END_SESSION_CONFIRMATION
        ):
            accepted = None
            action = ClarificationActionPlanner.from_end_confirmation(
                request
            )
            end_confirmation_requested = True
        elif (
            plan.destination
            == UnifiedDispatchDestination.END_SESSION_EXECUTION
        ):
            accepted = None
            action = ClarificationActionPlanner.from_end_execution(request)
            end_session_execution_requested = True
        elif (
            plan.destination
            == UnifiedDispatchDestination.PROTOCOL_NAVIGATION
        ):
            accepted = None
            action = ClarificationActionPlanner.from_protocol_navigation(request)
            protocol_navigation_action = "next"
        else:
            raise ValueError(
                "当前采用旁路不处理该结束会话目标，避免扩大副作用范围。"
            )

        return UnifiedAcceptanceBypassResult(
            execution_request=request,
            accepted_experiment=accepted,
            clarification_action=action,
            end_confirmation_requested=end_confirmation_requested,
            end_session_execution_requested=end_session_execution_requested,
            protocol_navigation_action=protocol_navigation_action,
        )
