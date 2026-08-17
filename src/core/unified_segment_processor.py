"""统一链的一段口述处理（业务装配工）。

把原来散落在 main.py 里的"观察 → 落盘 → 兜底 → 执行 → 确认"六步
封装成单一职责、无线程的纯业务流水线，便于用 Fake 依赖做单元测试，
也便于交给 OrderedTaskQueue 在后台单线程按序执行。

本模块不含任何线程/队列；"何时、以何种并发方式执行"由队列负责，
"如何处理一段口述"由本模块负责。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Callable, Protocol

from src.core.answer_fallback import (
    decide_unnumbered_answer,
)
from src.core.clarification_acceptance import (
    ClarificationAction,
    ClarificationActionType,
    ClarificationMutationPermission,
)
from src.core.confirmation_record import (
    ConfirmationRecord,
)
from src.core.pending_clarification import (
    ClarificationStatus,
)
from src.core.unified_observer import (
    UnifiedObservationStatus,
)

if TYPE_CHECKING:
    from src.asr.schemas import ASRResult
    from src.core.clarification_executor import (
        ClarificationExecutionResult,
    )
    from src.core.reply_coordinator import ReplyCoordinator
    from src.core.session_context import SessionContext
    from src.core.unified_observer import UnifiedObservation
    from src.storage.confirmation_store import ConfirmationStore
    from src.storage.event_store import ExperimentEventStore
    from src.storage.result_store import ASRResultStore


class ObserverLike(Protocol):
    """观察器依赖的最小接口：接收一段 ASR 证据返回观察摘要。"""

    def observe(
        self,
        *,
        request_id: str,
        session_id: str,
        segment_id: int,
        asr_result: ASRResult,
        reply_coordinator: ReplyCoordinator,
        recent_context: tuple[str, ...] = ...,
    ) -> UnifiedObservation: ...


class ExecutorLike(Protocol):
    """执行器依赖的最小接口：把动作翻译成状态变更。"""

    def execute(
        self,
        action: ClarificationAction,
    ) -> ClarificationExecutionResult: ...


@dataclass(frozen=True)
class PendingClarificationSummary:
    """"查看"动作时刻的待确认项只读快照，避免展示时再读可变状态。"""

    display_number: int
    is_deferred: bool
    question: str


@dataclass(frozen=True)
class SegmentJob:
    """提交给后台的一段口述工单。"""

    segment_id: int
    asr_result: ASRResult


@dataclass(frozen=True)
class SegmentOutcome:
    """一段口述处理完成后的成品结果。"""

    observation: UnifiedObservation
    review_summary: tuple[PendingClarificationSummary, ...] | None = None


class UnifiedSegmentProcessor:
    """处理一段口述的六步业务流水线；依赖全部由构造注入。"""

    def __init__(
        self,
        *,
        session_id: str,
        observer: ObserverLike,
        executor: ExecutorLike,
        asr_store: ASRResultStore,
        event_store: ExperimentEventStore,
        confirmation_store: ConfirmationStore,
        reply_coordinator: ReplyCoordinator,
        session_context: SessionContext,
        display: Callable[[SegmentOutcome], None] | None = None,
    ) -> None:
        self._session_id = session_id
        self._observer = observer
        self._executor = executor
        self._asr_store = asr_store
        self._event_store = event_store
        self._confirmation_store = confirmation_store
        self._reply_coordinator = reply_coordinator
        self._session_context = session_context
        self._display = display

    def process(
        self,
        job: SegmentJob,
    ) -> SegmentOutcome:
        """按固定顺序处理一段已经通过结束指令检查的口述。"""

        asr_result = job.asr_result
        segment_id = job.segment_id

        # ① 观察：统一链内部自行决定走精确命令快速路径还是调 LLM。
        recent_context = self._session_context.as_prompt_context()
        observation = self._observer.observe(
            request_id=f"unified-{self._session_id}-{segment_id}",
            session_id=self._session_id,
            segment_id=segment_id,
            asr_result=asr_result,
            reply_coordinator=self._reply_coordinator,
            recent_context=recent_context,
        )

        # ② 落盘 ASR。失败时向上抛出，由队列记录为 CompletedTask.error，
        #    后续步骤不再执行；原始 WAV 早已在录音时落盘，事实不丢。
        self._asr_store.append(
            result=asr_result,
            session_id=self._session_id,
            segment_id=segment_id,
        )

        # ③ 落盘事件 + 事件成功后更新上下文。
        if observation.accepted_analysis is not None:
            outcome = (
                observation.accepted_analysis.to_process_outcome()
            )
            self._event_store.append_analysis(outcome)
            self._session_context.add_analysis(outcome.value)

        # ④ 无编号回答兜底：统一链弃权时，若恰好一个待确认问题且
        #    短句提供了其缺失字段，则确定性判为回答。
        if (
            not observation.end_confirmation_requested
            and observation.clarification_action == "no_action"
            and observation.status == UnifiedObservationStatus.OBSERVED
        ):
            unresolved = self._reply_coordinator.active_clarifications()
            fallback = decide_unnumbered_answer(
                pending_questions=unresolved,
                text=asr_result.asr_transcript,
                current_segment_id=segment_id,
            )
            if fallback.is_answer and len(unresolved) == 1:
                question = unresolved[0]
                observation = replace(
                    observation,
                    clarification_action="answer",
                    destination="clarification_context",
                    permission="forward_context_candidate",
                    pending_action=ClarificationAction(
                        request_id=(
                            f"unified-{self._session_id}-{segment_id}"
                        ),
                        session_id=self._session_id,
                        segment_id=segment_id,
                        asr_transcript=asr_result.asr_transcript,
                        action_type=ClarificationActionType.ANSWER,
                        mutation_permission=(
                            ClarificationMutationPermission.PREPARE_UPDATE
                        ),
                        reason="无编号回答兜底",
                        requires_evidence_persistence=True,
                        target_clarification_id=(
                            question.clarification_id
                        ),
                        target_display_number=(
                            question.display_number
                        ),
                        expected_revision=question.revision,
                        answer_text=asr_result.asr_transcript,
                        supplied_entity_fields=fallback.fields,
                    ),
                )

        # ⑤ 执行动作。执行器内部异常不向上抛，只记为"内部异常"。
        executed = False
        execution_reason = None
        executed_action_type = None
        answer_remaining_fields: tuple[str, ...] = ()
        answer_resolved = False
        if observation.pending_action is not None:
            try:
                exec_result = self._executor.execute(
                    observation.pending_action
                )
                executed = exec_result.state_changed
                execution_reason = exec_result.reason
                executed_action_type = (
                    observation.pending_action.action_type
                )
                answer_remaining_fields = exec_result.remaining_fields
                answer_resolved = exec_result.resolved
            except Exception:
                execution_reason = "执行器内部异常"

        # ⑥ 确认答复持久化：只有 confirm 动作真实改变状态后才落盘。
        if (
            executed
            and executed_action_type == ClarificationActionType.CONFIRM
            and observation.pending_action is not None
        ):
            action = observation.pending_action
            target = self._reply_coordinator.find_clarification(
                action.target_clarification_id
            )
            if target is not None:
                self._confirmation_store.append(
                    ConfirmationRecord.from_executed_confirmation(
                        session_id=self._session_id,
                        clarification_id=target.clarification_id,
                        source_segment_id=target.source_segment_id,
                        answer_segment_id=segment_id,
                        answer_raw_text=asr_result.asr_transcript,
                        answer_audio_path=str(asr_result.audio_path),
                        fully_resolved=not target.is_unresolved,
                        remaining_fields=target.missing_fields,
                    )
                )

        # 查看动作是只读的：在处理时刻抓取待确认列表快照，
        # 供主线程稍后展示时使用（不依赖那时的可变状态）。
        review_summary = None
        if (
            observation.clarification_action == "review"
            and observation.status == UnifiedObservationStatus.OBSERVED
        ):
            review_summary = tuple(
                PendingClarificationSummary(
                    display_number=clarification.display_number,
                    is_deferred=(
                        clarification.status
                        == ClarificationStatus.DEFERRED
                    ),
                    question=clarification.question,
                )
                for clarification in (
                    self._reply_coordinator.active_clarifications()
                )
            )

        observation = replace(
            observation,
            executed=executed,
            execution_reason=execution_reason,
            answer_remaining_fields=answer_remaining_fields,
            answer_resolved=answer_resolved,
            answer_hint=(
                observation.status == UnifiedObservationStatus.OBSERVED
                and observation.acceptance_kind == "structured_experiment"
                and bool(self._reply_coordinator.active_clarifications())
            ),
        )

        outcome = SegmentOutcome(
            observation=observation,
            review_summary=review_summary,
        )

        # TIMING-01：结果在后台线程算完当场显示，不等下一段录音结束。
        # 显示职责通过回调注入，worker 不依赖终端/消息链的具体实现。
        if self._display is not None:
            self._display(outcome)

        return outcome
