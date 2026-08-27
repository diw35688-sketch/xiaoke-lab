"""自由实验六步流水线的受控集成测试。

用真实观察链（UnifiedObserver + Fake processor）、真实执行器
（ClarificationExecutor）、真实协调器（ReplyCoordinator）+ Fake 三个存储，
验证六步流水线能串联跑通并实现追问-回答闭环。
"""

import unittest

from src.asr.schemas import ASRResult
from src.core.clarification_executor import ClarificationExecutor
from src.core.conversation_turn import (
    ExperimentContext,
    InputSource,
    InteractionMode,
)
from src.core.experiment_observer_bridge import process_experiment_turn
from src.core.experiment_turn_input import ExperimentTurnInput
from src.core.reply_coordinator import ReplyCoordinator
from src.core.session_context import SessionContext
from src.core.unified_acceptance_bypass import UnifiedAcceptanceBypass
from src.core.unified_observer import (
    UnifiedObservationStatus,
    UnifiedObserver,
)
from src.core.unified_segment_processor import UnifiedSegmentProcessor
from src.core.unified_understanding import (
    ExperimentUnderstanding,
    UnifiedUnderstandingResult,
    build_degraded_understanding,
)
from src.llm.processor import ProcessOutcome
from src.llm.schemas import ExperimentEvent, ExperimentEventType, LLMAnalysisResult
from src.llm.unified_router import UnifiedUnderstandingRouter


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


def _voice_turn(text, *, request_id="request-1", **overrides):
    values = {
        "conversation_id": "conversation-a",
        "request_id": request_id,
        "turn_id": f"turn-{request_id}",
        "interaction_mode": InteractionMode.EXPERIMENT,
        "experiment_context": ExperimentContext.FREE,
        "mode_version": 1,
        "input_source": InputSource.SINGLE_RECORDING,
        "raw_text": text,
        "asr_result": _asr_result(text),
    }
    values.update(overrides)
    return ExperimentTurnInput(**values)


class PipelineFakeProcessor:
    """确定性理解结果；覆盖实验、追问、降级与回答补字段场景。"""

    def __init__(self):
        self.calls = []

    def understand(self, request):
        self.calls.append(request.raw_text)
        if request.raw_text == "加入五毫升缓冲液。":
            return self._experiment(request, follow_up=False)
        if request.raw_text == "将溶液加热。":
            return self._experiment(request, follow_up=True)
        if request.raw_text == "60摄氏度":
            return self._experiment(request, follow_up=False)
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


class FakeAsrStore:
    def __init__(self):
        self.appended = []

    def append(self, *, result, session_id, segment_id):
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


class ExperimentPipelineTests(unittest.TestCase):
    def setUp(self):
        self.asr_store = FakeAsrStore()
        self.event_store = FakeEventStore()
        self.confirmation_store = FakeConfirmationStore()
        self.coordinator = ReplyCoordinator()
        self.context = SessionContext()
        self.processor = UnifiedSegmentProcessor(
            session_id="lab-1",
            observer=UnifiedObserver(
                UnifiedAcceptanceBypass(
                    UnifiedUnderstandingRouter(PipelineFakeProcessor())
                )
            ),
            executor=ClarificationExecutor(self.coordinator),
            asr_store=self.asr_store,
            event_store=self.event_store,
            confirmation_store=self.confirmation_store,
            reply_coordinator=self.coordinator,
            session_context=self.context,
        )

    def test_six_steps_run_for_a_voice_turn(self):
        turn = _voice_turn("加入五毫升缓冲液。")

        outcome = process_experiment_turn(turn, segment_id=1, processor=self.processor)

        self.assertEqual(outcome.observation.status, UnifiedObservationStatus.OBSERVED)
        self.assertEqual(outcome.observation.acceptance_kind, "structured_experiment")
        self.assertEqual(len(self.asr_store.appended), 1)
        self.assertEqual(len(self.event_store.appended), 1)
        self.assertEqual(len(self.context), 1)

    def test_closed_loop_follow_up_then_answer(self):
        first = _voice_turn("将溶液加热。", request_id="request-1")
        process_experiment_turn(first, segment_id=1, processor=self.processor)
        self.assertEqual(len(self.coordinator.active_clarifications()), 1)

        second = _voice_turn("60摄氏度", request_id="request-2")
        outcome = process_experiment_turn(second, segment_id=2, processor=self.processor)

        self.assertEqual(outcome.observation.clarification_action, "answer")
        self.assertTrue(outcome.observation.answer_resolved)
        self.assertEqual(self.coordinator.active_clarifications(), ())

    def test_text_turn_is_rejected(self):
        turn = _voice_turn(
            "加入五毫升缓冲液。",
            input_source=InputSource.TEXT,
            asr_result=None,
        )

        with self.assertRaisesRegex(ValueError, "文字输入暂不接入"):
            process_experiment_turn(turn, segment_id=1, processor=self.processor)

    def test_llm_failure_degrades_without_losing_asr(self):
        turn = _voice_turn("模拟模型失败。")

        outcome = process_experiment_turn(turn, segment_id=1, processor=self.processor)

        self.assertEqual(outcome.observation.acceptance_kind, "degraded_evidence_note")
        self.assertEqual(len(self.asr_store.appended), 1)
        self.assertEqual(len(self.event_store.appended), 1)


if __name__ == "__main__":
    unittest.main()
