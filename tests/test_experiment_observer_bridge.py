import unittest

from src.asr.schemas import ASRResult
from src.core.conversation_turn import (
    ExperimentContext,
    InputSource,
    InteractionMode,
)
from src.core.experiment_observer_bridge import observe_experiment_turn
from src.core.experiment_turn_input import ExperimentTurnInput
from src.core.reply_coordinator import ReplyCoordinator
from src.core.session_context import SessionContext
from src.core.unified_acceptance_bypass import UnifiedAcceptanceBypass
from src.core.unified_observer import (
    UnifiedObservationStatus,
    UnifiedObserver,
)
from src.core.unified_understanding import (
    ExperimentUnderstanding,
    UnifiedUnderstandingResult,
    build_degraded_understanding,
)
from src.llm.processor import ProcessOutcome
from src.llm.schemas import ExperimentEvent, ExperimentEventType, LLMAnalysisResult
from src.llm.unified_router import UnifiedUnderstandingRouter
from web.experiment_runtime_sessions import ExperimentRuntimeSessionRegistry


def _asr_result(text):
    return ASRResult(
        asr_transcript=text,
        asr_model_raw_text=f"<|zh|>{text}",
        audio_path="fixed://segment.wav",
        audio_duration_seconds=1.0,
        recognition_seconds=0.1,
        model="fake-asr",
        language="zh",
    )


def _voice_turn(text, **overrides):
    values = {
        "conversation_id": "conversation-a",
        "request_id": "request-1",
        "turn_id": "turn-1",
        "interaction_mode": InteractionMode.EXPERIMENT,
        "experiment_context": ExperimentContext.FREE,
        "mode_version": 1,
        "input_source": InputSource.SINGLE_RECORDING,
        "raw_text": text,
        "asr_result": _asr_result(text),
    }
    values.update(overrides)
    return ExperimentTurnInput(**values)


class CountingFakeProcessor:
    """确定性理解结果，带调用计数；构造 source 匹配的有效事件。"""

    def __init__(self):
        self.calls = []

    def understand(self, request):
        self.calls.append(request.raw_text)
        if request.raw_text == "加入五毫升缓冲液。":
            return self._experiment(request, follow_up=False)
        if request.raw_text == "将溶液加热。":
            return self._experiment(request, follow_up=True)
        if request.raw_text == "模拟模型失败。":
            value = build_degraded_understanding(
                raw_text=request.raw_text,
                session_id=request.session_id,
                segment_id=request.segment_id,
                reason="Fake timeout",
            )
            return ProcessOutcome(
                value=value,
                degraded=True,
                error="Fake timeout",
                llm_attempts=2,
                llm_processing_seconds=0.3,
            )
        raise AssertionError(f"未配置的Fake文本：{request.raw_text}")

    @staticmethod
    def _experiment(request, *, follow_up):
        event = ExperimentEvent(
            event_type=ExperimentEventType.OPERATION,
            raw_text=request.raw_text,
            normalized_text=request.raw_text,
            missing_fields=["temperature"] if follow_up else [],
            source_session_id=request.session_id,
            source_segment_id=request.segment_id,
        )
        analysis = LLMAnalysisResult(
            events=[event],
            should_ask_follow_up=follow_up,
            follow_up_question="加热到多少摄氏度？" if follow_up else None,
        )
        return ProcessOutcome(
            value=UnifiedUnderstandingResult(
                raw_text=request.raw_text,
                experiment=ExperimentUnderstanding(analysis),
            ),
            llm_attempts=1,
            llm_processing_seconds=0.2,
        )


class ExperimentObserverBridgeTests(unittest.TestCase):
    def setUp(self):
        self.processor = CountingFakeProcessor()
        self.observer = UnifiedObserver(
            UnifiedAcceptanceBypass(
                UnifiedUnderstandingRouter(self.processor)
            )
        )

    def _observe(self, turn, *, session_id="lab-1", segment_id=1):
        return observe_experiment_turn(
            turn,
            session_id=session_id,
            segment_id=segment_id,
            observer=self.observer,
            coordinator=ReplyCoordinator(),
            context=SessionContext(),
        )

    def test_voice_turn_is_observed_with_identity_preserved(self):
        turn = _voice_turn("加入五毫升缓冲液。")

        observation = self._observe(turn)

        self.assertEqual(observation.status, UnifiedObservationStatus.OBSERVED)
        self.assertEqual(observation.request_id, "request-1")
        self.assertEqual(observation.session_id, "lab-1")
        self.assertEqual(observation.segment_id, 1)
        self.assertEqual(observation.acceptance_kind, "structured_experiment")
        self.assertEqual(
            observation.accepted_analysis.asr_transcript,
            "加入五毫升缓冲液。",
        )

    def test_text_turn_is_observed_without_fake_asr(self):
        turn = _voice_turn(
            "加入五毫升缓冲液。",
            input_source=InputSource.TEXT,
            asr_result=None,
        )

        observation = self._observe(turn)

        self.assertEqual(observation.status, UnifiedObservationStatus.OBSERVED)
        self.assertEqual(observation.accepted_analysis.asr_transcript, turn.raw_text)
        self.assertIsNone(turn.asr_result)

    def test_exact_command_bypasses_llm(self):
        turn = _voice_turn("查看待确认问题。")

        observation = self._observe(turn)

        self.assertEqual(self.processor.calls, [])
        self.assertEqual(observation.clarification_action, "review")

    def test_ordinary_input_uses_one_llm_call(self):
        turn = _voice_turn("加入五毫升缓冲液。")

        observation = self._observe(turn)

        self.assertEqual(self.processor.calls, ["加入五毫升缓冲液。"])
        self.assertEqual(observation.acceptance_kind, "structured_experiment")

    def test_llm_failure_degrades_without_losing_asr(self):
        turn = _voice_turn("模拟模型失败。")

        observation = self._observe(turn)

        self.assertEqual(observation.acceptance_kind, "degraded_evidence_note")
        self.assertEqual(
            observation.accepted_analysis.asr_transcript,
            "模拟模型失败。",
        )

    def test_runs_inside_experiment_runtime_session(self):
        registry = ExperimentRuntimeSessionRegistry()
        self.addCleanup(registry.clear)
        runtime = registry.session("conversation-a", "lab-1")
        turn = _voice_turn("加入五毫升缓冲液。")

        def operation(coordinator, context):
            return observe_experiment_turn(
                turn,
                session_id="lab-1",
                segment_id=1,
                observer=self.observer,
                coordinator=coordinator,
                context=context,
            )

        submission = runtime.submit(turn, operation)
        observation = submission.future.result(timeout=1)

        self.assertEqual(observation.status, UnifiedObservationStatus.OBSERVED)
        self.assertEqual(observation.acceptance_kind, "structured_experiment")


if __name__ == "__main__":
    unittest.main()
