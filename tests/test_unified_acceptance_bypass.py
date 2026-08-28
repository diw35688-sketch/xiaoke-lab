import unittest

from src.asr.schemas import ASRResult
from src.core.clarification_acceptance import (
    ClarificationActionType,
    ClarificationContextSnapshot,
)
from src.core.experiment_acceptance import ExperimentAcceptanceKind
from src.core.intent_classifier import IntentCandidate
from src.core.interaction_command import InteractionCommandType
from src.core.pending_clarification import PendingClarification
from src.core.unified_acceptance_bypass import (
    UnifiedAcceptanceBypass,
    UnifiedAcceptanceBypassInput,
)
from src.core.unified_understanding import (
    ControlUnderstanding,
    ExperimentUnderstanding,
    UnifiedUnderstandingResult,
    build_degraded_understanding,
)
from src.llm.processor import ProcessOutcome
from src.llm.schemas import ExperimentEvent, ExperimentEventType, LLMAnalysisResult
from src.llm.unified_router import UnifiedUnderstandingRouter


class FixedAcceptanceProcessor:
    """为集成接线提供确定性统一理解，不模拟执行服务。"""

    def __init__(self) -> None:
        self.calls = []

    def understand(self, request):
        self.calls.append(request.raw_text)
        if request.raw_text == "加入五毫升缓冲液。":
            return self._experiment(request, follow_up=False)
        if request.raw_text == "将溶液加热。":
            return self._experiment(request, follow_up=True)
        if request.raw_text == "我还有什么没回答？":
            return self._control(
                request.raw_text,
                InteractionCommandType.REVIEW_PENDING,
            )
        if request.raw_text == "关于问题2，是五分钟。":
            return self._control(
                request.raw_text,
                InteractionCommandType.TARGETED_ANSWER,
                target_question_number=2,
                answer_text="五分钟",
            )
        if request.raw_text == "今天先记录到这里吧。":
            return self._control(
                request.raw_text,
                InteractionCommandType.END_SESSION,
            )
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
        return ProcessOutcome(value=UnifiedUnderstandingResult(
            raw_text=request.raw_text,
            experiment=ExperimentUnderstanding(analysis),
        ), llm_attempts=1, llm_processing_seconds=0.2)

    @staticmethod
    def _control(raw_text, command_type, **fields):
        return ProcessOutcome(value=UnifiedUnderstandingResult(
            raw_text=raw_text,
            control=ControlUnderstanding(IntentCandidate(
                command_type=command_type,
                reason="固定集成候选。",
                **fields,
            )),
        ), llm_attempts=1, llm_processing_seconds=0.1)


def clarification(
    clarification_id="clarification-1",
    number=1,
    *,
    requires_confirmation=True,
):
    return PendingClarification(
        clarification_id=clarification_id,
        display_number=number,
        source_segment_id=1,
        source_raw_text="实验原文。",
        question="请确认。",
        missing_fields=() if requires_confirmation else ("duration",),
        requires_confirmation=requires_confirmation,
    )


class UnifiedAcceptanceBypassTests(unittest.TestCase):
    def setUp(self):
        self.processor = FixedAcceptanceProcessor()
        self.bypass = UnifiedAcceptanceBypass(
            UnifiedUnderstandingRouter(self.processor)
        )

    def inspect(self, text, *, context=None, segment_id=3):
        return self.bypass.inspect(UnifiedAcceptanceBypassInput(
            request_id=f"request-{segment_id}",
            session_id="session-1",
            segment_id=segment_id,
            asr_result=ASRResult(
                asr_transcript=text,
                asr_model_raw_text=f"<|zh|>{text}",
                audio_path=f"fixed://{segment_id}.wav",
                audio_duration_seconds=1.0,
                recognition_seconds=0.1,
                model="fake-asr",
                language="zh",
            ),
            clarification_context=context or ClarificationContextSnapshot(),
        ))

    def test_normal_experiment_is_accepted_without_follow_up_action(self):
        result = self.inspect("加入五毫升缓冲液。")
        self.assertEqual(
            result.accepted_experiment.kind,
            ExperimentAcceptanceKind.STRUCTURED_EXPERIMENT,
        )
        self.assertEqual(
            result.clarification_action.action_type,
            ClarificationActionType.NO_ACTION,
        )

    def test_experiment_follow_up_forms_create_plan(self):
        result = self.inspect("将溶液加热。")
        self.assertEqual(
            result.clarification_action.action_type,
            ClarificationActionType.CREATE,
        )
        self.assertEqual(
            result.clarification_action.missing_fields,
            ("temperature",),
        )

    def test_exact_review_bypasses_processor_and_forms_review(self):
        result = self.inspect("查看待确认问题。")
        self.assertEqual(self.processor.calls, [])
        self.assertEqual(
            result.clarification_action.action_type,
            ClarificationActionType.REVIEW,
        )

    def test_llm_end_session_requests_confirmation_not_raise(self):
        result = self.inspect("今天先记录到这里吧。")
        self.assertTrue(result.end_confirmation_requested)
        self.assertIsNone(result.accepted_experiment)
        self.assertEqual(
            result.clarification_action.action_type,
            ClarificationActionType.NO_ACTION,
        )

    def test_exact_end_session_executes_without_llm_or_value_error(self):
        result = self.inspect("结束实验记录")
        self.assertEqual(self.processor.calls, [])
        self.assertTrue(result.end_session_execution_requested)
        self.assertFalse(result.end_confirmation_requested)
        self.assertIsNone(result.accepted_experiment)
        self.assertEqual(
            result.clarification_action.action_type,
            ClarificationActionType.NO_ACTION,
        )

    def test_llm_natural_review_forms_only_read_only_review(self):
        result = self.inspect("我还有什么没回答？")
        self.assertEqual(self.processor.calls, ["我还有什么没回答？"])
        self.assertEqual(
            result.clarification_action.action_type,
            ClarificationActionType.REVIEW,
        )

    def test_exact_defer_targets_current_without_state_change(self):
        item = clarification()
        context = ClarificationContextSnapshot(
            (item,),
            current_clarification_id=item.clarification_id,
        )
        result = self.inspect("这个问题先跳过。", context=context)
        action = result.clarification_action
        self.assertEqual(action.action_type, ClarificationActionType.DEFER)
        self.assertEqual(action.expected_revision, item.revision)
        self.assertTrue(item.is_active)

    def test_exact_defer_targeted_defers_numbered_question(self):
        item2 = clarification(clarification_id="clarification-2", number=2)
        context = ClarificationContextSnapshot((item2,))
        result = self.inspect("问题二先跳过。", context=context)
        action = result.clarification_action
        self.assertEqual(action.action_type, ClarificationActionType.DEFER)
        self.assertEqual(action.target_clarification_id, "clarification-2")
        self.assertEqual(action.expected_revision, item2.revision)

    def test_exact_targeted_answer_reaches_only_named_question(self):
        first = clarification("clarification-1", 1)
        second = clarification("clarification-2", 2, requires_confirmation=False)
        context = ClarificationContextSnapshot((first, second))
        result = self.inspect("问题2五分钟。", context=context)
        action = result.clarification_action
        self.assertEqual(action.action_type, ClarificationActionType.ANSWER)
        self.assertEqual(action.target_clarification_id, "clarification-2")
        self.assertEqual(action.answer_text, "五分钟")

    def test_llm_medium_risk_targeted_answer_stays_no_action(self):
        context = ClarificationContextSnapshot((
            clarification("clarification-2", 2),
        ))
        result = self.inspect("关于问题2，是五分钟。", context=context)
        self.assertEqual(
            result.clarification_action.action_type,
            ClarificationActionType.NO_ACTION,
        )
        self.assertIsNone(
            result.clarification_action.target_clarification_id
        )

    def test_degraded_note_is_accepted_as_evidence_but_creates_no_question(self):
        result = self.inspect("模拟模型失败。")
        self.assertEqual(
            result.accepted_experiment.kind,
            ExperimentAcceptanceKind.DEGRADED_EVIDENCE_NOTE,
        )
        self.assertEqual(
            result.clarification_action.action_type,
            ClarificationActionType.NO_ACTION,
        )

    def test_identity_and_transcript_survive_every_stage(self):
        result = self.inspect("将溶液加热。", segment_id=7)
        request = result.execution_request
        accepted = result.accepted_experiment
        action = result.clarification_action
        self.assertEqual(
            (request.request_id, accepted.request_id, action.request_id),
            ("request-7", "request-7", "request-7"),
        )
        self.assertEqual(
            (request.segment_id, accepted.segment_id, action.segment_id),
            (7, 7, 7),
        )
        self.assertEqual(
            request.asr_evidence.asr_transcript,
            action.asr_transcript,
        )


if __name__ == "__main__":
    unittest.main()
