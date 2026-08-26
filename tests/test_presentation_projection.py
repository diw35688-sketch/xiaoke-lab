import unittest

from src.core.clarification_acceptance import (
    ClarificationAction,
    ClarificationActionType,
    ClarificationMutationPermission,
)
from src.core.presentation_copy import (
    ConfirmationAckResult,
    ProgramStatus,
    RecordAckResult,
)
from src.core.presentation_intent import (
    MessageKind,
    MessagePriority,
    ScreenTarget,
)
from src.core.presentation_projection import (
    messages_for_observation,
    messages_for_program_status,
    messages_for_review,
    messages_for_wake_ack,
)
from src.core.unified_observer import (
    UnifiedObservation,
    UnifiedObservationStatus,
)
from src.core.unified_segment_processor import PendingClarificationSummary


class _FakeEvent:
    def __init__(self, normalized_text):
        self.normalized_text = normalized_text


class _FakeAnalysis:
    def __init__(self, events):
        self.events = events


class _FakeAccepted:
    def __init__(self, normalized_texts):
        self._analysis = _FakeAnalysis(
            [_FakeEvent(text) for text in normalized_texts]
        )

    def materialize_analysis(self):
        return self._analysis


def _observation(**overrides):
    defaults = {
        "request_id": "unified-s-1",
        "session_id": "s",
        "segment_id": 1,
        "status": UnifiedObservationStatus.OBSERVED,
        "destination": "experiment_pipeline",
        "clarification_action": "no_action",
    }
    defaults.update(overrides)
    return UnifiedObservation(**defaults)


def _create_action(question):
    return ClarificationAction(
        request_id="unified-s-1",
        session_id="s",
        segment_id=1,
        asr_transcript="加入缓冲液",
        action_type=ClarificationActionType.CREATE,
        mutation_permission=ClarificationMutationPermission.PREPARE_CREATE,
        reason="创建追问",
        requires_evidence_persistence=True,
        question=question,
        missing_fields=("temperature",),
    )


def _update_action(action_type, display_number):
    kwargs = {
        "request_id": "unified-s-1",
        "session_id": "s",
        "segment_id": 1,
        "asr_transcript": "60摄氏度",
        "action_type": action_type,
        "mutation_permission": ClarificationMutationPermission.PREPARE_UPDATE,
        "reason": "处理追问",
        "requires_evidence_persistence": True,
        "target_clarification_id": "q1",
        "target_display_number": display_number,
        "expected_revision": 1,
    }
    if action_type in {
        ClarificationActionType.ANSWER,
        ClarificationActionType.CONFIRM,
        ClarificationActionType.REJECT_SUGGESTION,
    }:
        kwargs["answer_text"] = "60摄氏度"
    return ClarificationAction(**kwargs)


class ProgramProjectionTests(unittest.TestCase):
    def test_program_status_projects_fixed_semantics(self):
        intent = messages_for_program_status(
            ProgramStatus.READY,
            request_id="program-1",
        )[0]

        self.assertEqual(intent.kind, MessageKind.PROGRAM_STATUS)
        self.assertEqual(intent.args["status"], ProgramStatus.READY)
        self.assertEqual(intent.priority, MessagePriority.DIRECT_ACK)
        self.assertEqual(intent.screen_target, ScreenTarget.STATUS)

    def test_wake_ack_projects_keyword_without_rendering_copy(self):
        intent = messages_for_wake_ack(
            "小科小科",
            request_id="program-2",
        )[0]

        self.assertEqual(intent.kind, MessageKind.WAKE_ACK)
        self.assertEqual(intent.args, {"keyword": "小科小科"})
        self.assertEqual(intent.priority, MessagePriority.DIRECT_ACK)


class ObservationProjectionTests(unittest.TestCase):
    def test_abstention_no_action_projects_retry_feedback(self):
        observation = _observation(
            destination="abstention",
            permission="no_action",
            clarification_action="no_action",
        )

        messages = messages_for_observation(observation)

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].kind, MessageKind.SYSTEM_ISSUE)
        self.assertEqual(messages[0].args["text"], "没听清，请再说。")
        self.assertEqual(messages[0].priority, MessagePriority.DIRECT_ACK)

    def test_failed_projects_record_ack_failed(self):
        observation = _observation(
            status=UnifiedObservationStatus.FAILED,
            error_type="ValueError",
        )

        messages = messages_for_observation(
            observation, experiment_step_number=0
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].kind, MessageKind.RECORD_ACK)
        self.assertEqual(messages[0].args["result"], RecordAckResult.FAILED)

    def test_degraded_projects_record_ack_degraded(self):
        observation = _observation(
            acceptance_kind="degraded_evidence_note",
        )

        messages = messages_for_observation(
            observation, experiment_step_number=0
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].kind, MessageKind.RECORD_ACK)
        self.assertEqual(messages[0].args["result"], RecordAckResult.DEGRADED)

    def test_recorded_projects_record_ack_with_step_number(self):
        observation = _observation(
            acceptance_kind="structured_experiment",
        )

        messages = messages_for_observation(
            observation, experiment_step_number=3
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].args["result"], RecordAckResult.RECORDED)
        self.assertEqual(messages[0].args["step_number"], 3)
        self.assertEqual(messages[0].source_segment_id, 1)
        self.assertEqual(messages[0].args["event_previews"], ())

    def test_recorded_projects_normalized_event_previews(self):
        observation = _observation(
            acceptance_kind="structured_experiment",
            accepted_analysis=_FakeAccepted(
                ("加入5毫升缓冲液。", "加热到60摄氏度。")
            ),
        )

        messages = messages_for_observation(
            observation, experiment_step_number=3
        )

        previews = messages[0].args["event_previews"]
        self.assertEqual(
            [item.normalized_text for item in previews],
            ["加入5毫升缓冲液。", "加热到60摄氏度。"],
        )

    def test_answer_hint_appends_after_record_ack(self):
        observation = _observation(
            acceptance_kind="structured_experiment",
            answer_hint=True,
        )

        messages = messages_for_observation(
            observation, experiment_step_number=2
        )

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].kind, MessageKind.RECORD_ACK)
        self.assertEqual(messages[1].kind, MessageKind.ANSWER_HINT)
        self.assertEqual(
            messages[1].screen_target, ScreenTarget.DIALOGUE
        )

    def test_degraded_record_ack_has_empty_previews(self):
        observation = _observation(
            acceptance_kind="degraded_evidence_note",
        )

        messages = messages_for_observation(
            observation, experiment_step_number=0
        )

        self.assertEqual(messages[0].args["event_previews"], ())

    def test_create_projects_clarification_with_question(self):
        observation = _observation(
            clarification_action="create",
            executed=True,
            pending_action=_create_action("加热到什么温度？"),
        )

        messages = messages_for_observation(
            observation, experiment_step_number=0
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].kind, MessageKind.CLARIFICATION)
        self.assertEqual(messages[0].args["question"], "加热到什么温度？")
        self.assertEqual(
            messages[0].screen_target, ScreenTarget.CURRENT_QUESTION
        )
        self.assertEqual(messages[0].priority, MessagePriority.ACTIVE_QUESTION)

    def test_answer_projects_confirmation_ack_with_remaining_fields(self):
        observation = _observation(
            clarification_action="answer",
            executed=True,
            pending_action=_update_action(
                ClarificationActionType.ANSWER, display_number=1
            ),
            answer_remaining_fields=("duration",),
            answer_resolved=False,
        )

        messages = messages_for_observation(
            observation, experiment_step_number=0
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].kind, MessageKind.CONFIRMATION_ACK)
        self.assertEqual(
            messages[0].args["result"], ConfirmationAckResult.ANSWERED
        )
        self.assertEqual(messages[0].args["display_number"], 1)
        self.assertEqual(messages[0].args["remaining_fields"], ("duration",))

    def test_answer_resolved_projects_confirmation_ack_resolved(self):
        observation = _observation(
            clarification_action="answer",
            executed=True,
            pending_action=_update_action(
                ClarificationActionType.ANSWER, display_number=1
            ),
            answer_remaining_fields=(),
            answer_resolved=True,
        )

        messages = messages_for_observation(
            observation, experiment_step_number=0
        )

        self.assertEqual(len(messages), 1)
        self.assertTrue(messages[0].args["resolved"])

    def test_answer_needs_confirm_projects_confirmation_ack(self):
        observation = _observation(
            clarification_action="answer",
            executed=True,
            pending_action=_update_action(
                ClarificationActionType.ANSWER, display_number=1
            ),
            answer_remaining_fields=(),
            answer_resolved=False,
        )

        messages = messages_for_observation(
            observation, experiment_step_number=0
        )

        self.assertEqual(len(messages), 1)
        self.assertFalse(messages[0].args["resolved"])
        self.assertEqual(messages[0].args["remaining_fields"], ())

    def test_confirm_projects_confirmation_ack(self):
        observation = _observation(
            clarification_action="confirm",
            executed=True,
            pending_action=_update_action(
                ClarificationActionType.CONFIRM, display_number=2
            ),
        )

        messages = messages_for_observation(
            observation, experiment_step_number=0
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(
            messages[0].args["result"], ConfirmationAckResult.CONFIRMED
        )
        self.assertEqual(messages[0].args["display_number"], 2)


    def test_confirm_with_remaining_fields_projects_confirmation_ack(self):
        observation = _observation(
            clarification_action="confirm",
            executed=True,
            pending_action=_update_action(
                ClarificationActionType.CONFIRM, display_number=2
            ),
            answer_remaining_fields=("duration",),
            answer_resolved=False,
        )

        messages = messages_for_observation(
            observation, experiment_step_number=0
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(
            messages[0].args["result"], ConfirmationAckResult.CONFIRMED
        )
        self.assertEqual(messages[0].args["remaining_fields"], ("duration",))
        self.assertFalse(messages[0].args["resolved"])

    def test_no_action_projects_feedback_in_control_context(self):
        observation = _observation(
            clarification_action="no_action",
            executed=False,
            execution_reason="指定的问题编号不存在。",
        )

        messages = messages_for_observation(
            observation, experiment_step_number=0
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].kind, MessageKind.NO_ACTION_FEEDBACK)
        self.assertEqual(
            messages[0].args["reason"], "指定的问题编号不存在。"
        )
        self.assertEqual(
            messages[0].screen_target, ScreenTarget.DIALOGUE
        )

    def test_no_action_does_not_duplicate_degraded_record_ack(self):
        observation = _observation(
            acceptance_kind="degraded_evidence_note",
            clarification_action="no_action",
            executed=False,
            execution_reason="降级NOTE只保留证据，不自动创建待确认问题。",
        )

        messages = messages_for_observation(
            observation, experiment_step_number=0
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].kind, MessageKind.RECORD_ACK)

    def test_no_action_does_not_duplicate_experiment_record_ack(self):
        observation = _observation(
            acceptance_kind="structured_experiment",
            clarification_action="no_action",
            executed=False,
            execution_reason="实验分析不需要追问。",
        )

        messages = messages_for_observation(
            observation, experiment_step_number=2
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].kind, MessageKind.RECORD_ACK)

    def test_defer_projects_deferred(self):
        observation = _observation(
            clarification_action="defer",
            executed=True,
            pending_action=_update_action(
                ClarificationActionType.DEFER, display_number=3
            ),
        )

        messages = messages_for_observation(
            observation, experiment_step_number=0
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].kind, MessageKind.CLARIFICATION_DEFERRED)
        self.assertEqual(messages[0].args["display_number"], 3)

    def test_end_confirmation_projects_clarification(self):
        observation = _observation(end_confirmation_requested=True)

        messages = messages_for_observation(
            observation, experiment_step_number=0
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].kind, MessageKind.CLARIFICATION)
        self.assertIn("结束", messages[0].args["question"])

    def test_recorded_plus_end_confirmation_produces_two_messages(self):
        observation = _observation(
            acceptance_kind="structured_experiment",
            end_confirmation_requested=True,
        )

        messages = messages_for_observation(
            observation, experiment_step_number=2
        )

        self.assertEqual(len(messages), 2)
        kinds = [m.kind for m in messages]
        self.assertIn(MessageKind.RECORD_ACK, kinds)
        self.assertIn(MessageKind.CLARIFICATION, kinds)


class ReviewProjectionTests(unittest.TestCase):
    def test_empty_review_projects_one_review_intent(self):
        messages = messages_for_review((), request_id="unified-s-1")

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].kind, MessageKind.CLARIFICATION_REVIEW)
        self.assertEqual(messages[0].args["items"], ())

    def test_review_projects_items(self):
        summary = (
            PendingClarificationSummary(
                display_number=1, is_deferred=False, question="离心多久？"
            ),
            PendingClarificationSummary(
                display_number=2, is_deferred=True, question="温度？"
            ),
        )

        messages = messages_for_review(summary, request_id="unified-s-1")

        self.assertEqual(len(messages), 1)
        items = messages[0].args["items"]
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].display_number, 1)
        self.assertFalse(items[0].is_deferred)
        self.assertEqual(items[1].display_number, 2)
        self.assertTrue(items[1].is_deferred)


if __name__ == "__main__":
    unittest.main()
