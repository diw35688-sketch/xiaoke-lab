"""UnifiedSegmentProcessor 的单元测试。

用 Fake 观察器/执行器/存储 + 真实的纯领域对象（SessionContext、
ReplyCoordinator）验证六步业务流水线的顺序、失败边界与上下文链。
不调用真实 LLM，不做任何文件 I/O。
"""

import unittest
from types import SimpleNamespace

from src.asr.schemas import ASRResult
from src.core.clarification_acceptance import (
    ClarificationAction,
    ClarificationActionType,
    ClarificationMutationPermission,
)
from src.core.clarification_executor import (
    ClarificationExecutionResult,
)
from src.core.reply_coordinator import ReplyCoordinator
from src.core.session_context import SessionContext
from src.core.unified_observer import (
    UnifiedObservation,
    UnifiedObservationStatus,
)
from src.core.unified_segment_processor import (
    SegmentJob,
    UnifiedSegmentProcessor,
)
from src.llm.processor import ProcessOutcome
from src.llm.schemas import (
    ExperimentEvent,
    ExperimentEventType,
    LLMAnalysisResult,
)


def _accepted_analysis(transcript: str, segment_id: int):
    """构造一个假的已验收分析，其 to_process_outcome 返回真实分析。"""

    event = ExperimentEvent(
        event_type=ExperimentEventType.OPERATION,
        raw_text=transcript,
        normalized_text=transcript,
        source_session_id="s1",
        source_segment_id=segment_id,
    )
    analysis = LLMAnalysisResult(events=[event])
    outcome = ProcessOutcome(
        value=analysis,
        degraded=False,
        error=None,
        llm_attempts=1,
        llm_processing_seconds=0.0,
    )
    return SimpleNamespace(to_process_outcome=lambda: outcome)


def _experiment_observation(
    segment_id: int,
    accepted_analysis,
    pending_action=None,
) -> UnifiedObservation:
    return UnifiedObservation(
        request_id=f"unified-s1-{segment_id}",
        session_id="s1",
        segment_id=segment_id,
        status=UnifiedObservationStatus.OBSERVED,
        destination="experiment_pipeline",
        permission="forward_experiment_analysis",
        acceptance_kind=(
            "structured_experiment" if accepted_analysis else None
        ),
        clarification_action="no_action",
        accepted_analysis=accepted_analysis,
        pending_action=pending_action,
    )


def _failed_observation(segment_id: int) -> UnifiedObservation:
    return UnifiedObservation(
        request_id=f"unified-s1-{segment_id}",
        session_id="s1",
        segment_id=segment_id,
        status=UnifiedObservationStatus.FAILED,
        error_type="ValueError",
    )


class FakeObserver:
    """按顺序返回预设观察，并记录每次收到的 recent_context。"""

    def __init__(self, observations):
        self._observations = list(observations)
        self.received_contexts = []

    def observe(self, **kwargs):
        self.received_contexts.append(kwargs["recent_context"])
        return self._observations.pop(0)


class FakeExecutor:
    """记录执行的动作；可配置返回结果或抛出异常。"""

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.actions = []

    def execute(self, action):
        self.actions.append(action)
        if self.error is not None:
            raise self.error
        return self.result


class FakeAsrStore:
    def __init__(self, error=None):
        self.error = error
        self.appended = []

    def append(self, *, result, session_id, segment_id):
        if self.error is not None:
            raise self.error
        self.appended.append((result, session_id, segment_id))


class FakeEventStore:
    def __init__(self):
        self.appended = []

    def append_analysis(self, outcome):
        self.appended.append(outcome)


class FakeConfirmationStore:
    def __init__(self):
        self.appended = []

    def append(self, record):
        self.appended.append(record)


def _make_processor(
    observer,
    *,
    executor=None,
    asr_store=None,
    event_store=None,
    confirmation_store=None,
    coordinator=None,
    context=None,
    display=None,
) -> UnifiedSegmentProcessor:
    return UnifiedSegmentProcessor(
        session_id="s1",
        observer=observer,
        executor=executor if executor is not None else FakeExecutor(),
        asr_store=asr_store if asr_store is not None else FakeAsrStore(),
        event_store=(
            event_store if event_store is not None else FakeEventStore()
        ),
        confirmation_store=(
            confirmation_store
            if confirmation_store is not None
            else FakeConfirmationStore()
        ),
        reply_coordinator=(
            coordinator if coordinator is not None else ReplyCoordinator()
        ),
        session_context=context if context is not None else SessionContext(),
        display=display,
    )


class UnifiedSegmentProcessorTest(unittest.TestCase):
    def test_experiment_segment_sets_answer_hint_when_questions_active(self):
        # Arrange：已有待确认问题，新段是结构化实验。
        coordinator = ReplyCoordinator()
        coordinator.register_clarification(
            segment_id=1,
            raw_text="加入缓冲液。",
            question="实际加了多少毫升？",
            missing_fields=("amount_value",),
        )
        asr = ASRResult(
            asr_transcript="50毫升",
            asr_model_raw_text="50毫升",
        )
        observer = FakeObserver([
            _experiment_observation(2, _accepted_analysis("50毫升", 2)),
        ])
        processor = _make_processor(
            observer,
            coordinator=coordinator,
            executor=FakeExecutor(
                result=ClarificationExecutionResult(
                    request_id="unified-s1-2",
                    session_id="s1",
                    segment_id=2,
                    action_type=ClarificationActionType.NO_ACTION,
                    state_changed=False,
                    reason="实验分析不需要追问。",
                )
            ),
        )

        # Act
        outcome = processor.process(
            SegmentJob(segment_id=2, asr_result=asr)
        )

        # Assert
        self.assertTrue(outcome.observation.answer_hint)

    def test_experiment_segment_persists_asr_event_and_context(self):
        # Arrange
        asr = ASRResult(
            asr_transcript="加热到60度",
            asr_model_raw_text="加热到60度",
        )
        accepted = _accepted_analysis("加热到60度", 1)
        observer = FakeObserver([_experiment_observation(1, accepted)])
        asr_store = FakeAsrStore()
        event_store = FakeEventStore()
        context = SessionContext()
        processor = _make_processor(
            observer,
            asr_store=asr_store,
            event_store=event_store,
            context=context,
        )

        # Act
        outcome = processor.process(
            SegmentJob(segment_id=1, asr_result=asr)
        )

        # Assert：ASR、事件、上下文三者都落盘/更新
        self.assertEqual(len(asr_store.appended), 1)
        self.assertEqual(len(event_store.appended), 1)
        self.assertEqual(len(context), 1)
        self.assertTrue(outcome.observation.is_experiment_evidence)

    def test_second_segment_receives_first_segment_context(self):
        # Arrange：两段连续口述，第二段依赖第一段
        asr1 = ASRResult(
            asr_transcript="加入缓冲液",
            asr_model_raw_text="加入缓冲液",
        )
        asr2 = ASRResult(
            asr_transcript="加热到60度",
            asr_model_raw_text="加热到60度",
        )
        observer = FakeObserver([
            _experiment_observation(1, _accepted_analysis("加入缓冲液", 1)),
            _experiment_observation(2, _accepted_analysis("加热到60度", 2)),
        ])
        processor = _make_processor(observer)

        # Act：顺序处理两段
        processor.process(SegmentJob(segment_id=1, asr_result=asr1))
        processor.process(SegmentJob(segment_id=2, asr_result=asr2))

        # Assert：第二段观察者收到的上下文包含第一段的事件
        self.assertEqual(len(observer.received_contexts), 2)
        second_context = observer.received_contexts[1]
        self.assertEqual(len(second_context), 1)
        self.assertIn("加入缓冲液", second_context[0])

    def test_failed_observation_still_saves_asr(self):
        # Arrange：观察失败（如 LLM 异常）但仍需保存原始 ASR
        asr = ASRResult(
            asr_transcript="加热到60度",
            asr_model_raw_text="加热到60度",
        )
        observer = FakeObserver([_failed_observation(1)])
        asr_store = FakeAsrStore()
        event_store = FakeEventStore()
        processor = _make_processor(
            observer,
            asr_store=asr_store,
            event_store=event_store,
        )

        # Act
        outcome = processor.process(
            SegmentJob(segment_id=1, asr_result=asr)
        )

        # Assert：ASR 已保存，事件未保存，状态为 FAILED
        self.assertEqual(len(asr_store.appended), 1)
        self.assertEqual(len(event_store.appended), 0)
        self.assertEqual(
            outcome.observation.status,
            UnifiedObservationStatus.FAILED,
        )

    def test_asr_save_failure_propagates(self):
        # Arrange：ASR 落盘失败
        asr = ASRResult(
            asr_transcript="加热到60度",
            asr_model_raw_text="加热到60度",
        )
        observer = FakeObserver([
            _experiment_observation(1, _accepted_analysis("加热到60度", 1)),
        ])
        asr_store = FakeAsrStore(error=RuntimeError("disk full"))
        processor = _make_processor(observer, asr_store=asr_store)

        # Act & Assert：异常向上传播，交给队列记录
        with self.assertRaises(RuntimeError):
            processor.process(SegmentJob(segment_id=1, asr_result=asr))

    def test_pending_action_is_executed(self):
        # Arrange：带一个动作的观察
        action = ClarificationAction(
            request_id="unified-s1-1",
            session_id="s1",
            segment_id=1,
            asr_transcript="加热到60度",
            action_type=ClarificationActionType.NO_ACTION,
            mutation_permission=ClarificationMutationPermission.NONE,
            reason="test",
            requires_evidence_persistence=False,
        )
        result = ClarificationExecutionResult(
            request_id="unified-s1-1",
            session_id="s1",
            segment_id=1,
            action_type=ClarificationActionType.NO_ACTION,
            state_changed=False,
            reason="NO_ACTION 无需状态变更。",
        )
        executor = FakeExecutor(result=result)
        asr = ASRResult(
            asr_transcript="加热到60度",
            asr_model_raw_text="加热到60度",
        )
        observer = FakeObserver([
            _experiment_observation(1, None, pending_action=action),
        ])
        processor = _make_processor(observer, executor=executor)

        # Act
        outcome = processor.process(
            SegmentJob(segment_id=1, asr_result=asr)
        )

        # Assert：执行器被调用，结果传播到 outcome
        self.assertEqual(len(executor.actions), 1)
        self.assertFalse(outcome.observation.executed)
        self.assertEqual(
            outcome.observation.execution_reason,
            "NO_ACTION 无需状态变更。",
        )

    def test_display_callback_is_invoked_with_outcome(self):
        # Arrange：注入 display 回调，收集被显示的结果
        asr = ASRResult(
            asr_transcript="加热到60度",
            asr_model_raw_text="加热到60度",
        )
        accepted = _accepted_analysis("加热到60度", 1)
        observer = FakeObserver([_experiment_observation(1, accepted)])
        displayed = []
        processor = _make_processor(
            observer,
            display=displayed.append,
        )

        # Act
        outcome = processor.process(
            SegmentJob(segment_id=1, asr_result=asr)
        )

        # Assert：回调恰好被调用一次，且拿到的是同一个结果对象
        self.assertEqual(len(displayed), 1)
        self.assertIs(displayed[0], outcome)

    def test_executor_exception_is_isolated(self):
        # Arrange：执行器内部抛异常
        action = ClarificationAction(
            request_id="unified-s1-1",
            session_id="s1",
            segment_id=1,
            asr_transcript="加热到60度",
            action_type=ClarificationActionType.NO_ACTION,
            mutation_permission=ClarificationMutationPermission.NONE,
            reason="test",
            requires_evidence_persistence=False,
        )
        executor = FakeExecutor(error=RuntimeError("boom"))
        asr = ASRResult(
            asr_transcript="加热到60度",
            asr_model_raw_text="加热到60度",
        )
        observer = FakeObserver([
            _experiment_observation(1, None, pending_action=action),
        ])
        processor = _make_processor(observer, executor=executor)

        # Act：不应向上抛，而是记为"内部异常"
        outcome = processor.process(
            SegmentJob(segment_id=1, asr_result=asr)
        )

        # Assert
        self.assertFalse(outcome.observation.executed)
        self.assertEqual(
            outcome.observation.execution_reason,
            "执行器内部异常",
        )


if __name__ == "__main__":
    unittest.main()
