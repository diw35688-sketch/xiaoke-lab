# -*- coding: utf-8 -*-
"""B2-1：UnifiedObservation 部分观察（partial）构造校验 + 投影分支测试。

覆盖：
- partial=True 时放宽 OBSERVED 校验（不强制 destination/clarification_action）；
- partial 只允许成功观察、只允许携带非空追问文本；
- CLI 完整路径（partial 默认 False）校验与投影行为零变化（回归）。
"""

import unittest

from src.core.presentation_copy import RecordAckResult
from src.core.presentation_intent import (
    MessageKind,
    MessagePriority,
    ScreenTarget,
)
from src.core.presentation_projection import messages_for_observation
from src.core.unified_observer import (
    UnifiedObservation,
    UnifiedObservationStatus,
)


def _partial_observation(**overrides):
    defaults = {
        "request_id": "web-degraded-1",
        "session_id": "s",
        "segment_id": 1,
        "status": UnifiedObservationStatus.OBSERVED,
        "partial": True,
    }
    defaults.update(overrides)
    return UnifiedObservation(**defaults)


class PartialObservationConstructionTests(unittest.TestCase):
    """部分观察的构造与校验。"""

    def test_partial_observed_allowed_without_destination_and_action(self):
        observation = _partial_observation()
        self.assertTrue(observation.partial)
        self.assertIsNone(observation.destination)
        self.assertIsNone(observation.clarification_action)

    def test_partial_observed_carries_question(self):
        observation = _partial_observation(
            partial_question="缺时长，请补充",
            missing_fields=("duration",),
            follow_up_required=True,
        )
        self.assertEqual(observation.partial_question, "缺时长，请补充")
        self.assertEqual(observation.missing_fields, ("duration",))

    def test_full_observation_still_requires_destination(self):
        """回归：CLI 完整路径（partial 默认 False）校验不放宽。"""
        with self.assertRaises(ValueError):
            UnifiedObservation(
                request_id="unified-1",
                session_id="s",
                segment_id=1,
                status=UnifiedObservationStatus.OBSERVED,
                clarification_action="create",
            )

    def test_partial_failed_is_rejected(self):
        with self.assertRaises(ValueError):
            _partial_observation(status=UnifiedObservationStatus.FAILED)

    def test_partial_observed_with_error_type_is_rejected(self):
        with self.assertRaises(ValueError):
            _partial_observation(error_type="SomeError")

    def test_question_only_allowed_when_partial(self):
        """回归：完整观察夹带 partial_question 必须报错。"""
        with self.assertRaises(ValueError):
            UnifiedObservation(
                request_id="unified-1",
                session_id="s",
                segment_id=1,
                status=UnifiedObservationStatus.OBSERVED,
                destination="experiment_pipeline",
                clarification_action="no_action",
                partial_question="不能带",
            )

    def test_partial_blank_question_is_rejected(self):
        with self.assertRaises(ValueError):
            _partial_observation(partial_question="   ")

    def test_partial_defaults_to_false(self):
        observation = UnifiedObservation(
            request_id="unified-1",
            session_id="s",
            segment_id=1,
            status=UnifiedObservationStatus.OBSERVED,
            destination="experiment_pipeline",
            clarification_action="no_action",
        )
        self.assertFalse(observation.partial)
        self.assertIsNone(observation.partial_question)


class PartialObservationProjectionTests(unittest.TestCase):
    """投影层 partial 分支。"""

    def test_partial_with_question_projects_clarification(self):
        messages = messages_for_observation(
            _partial_observation(partial_question="缺时长，请补充")
        )
        self.assertEqual(len(messages), 1)
        intent = messages[0]
        self.assertEqual(intent.kind, MessageKind.CLARIFICATION)
        self.assertEqual(intent.args["question"], "缺时长，请补充")
        self.assertEqual(intent.screen_target, ScreenTarget.CURRENT_QUESTION)
        self.assertEqual(intent.priority, MessagePriority.ACTIVE_QUESTION)
        self.assertEqual(intent.source_segment_id, 1)

    def test_partial_with_question_emits_no_record_ack(self):
        """有追问时只出追问，不出记录回执（单问题闸门友好）。"""
        messages = messages_for_observation(
            _partial_observation(partial_question="缺时长，请补充")
        )
        self.assertEqual(len(messages), 1)
        self.assertNotEqual(messages[0].kind, MessageKind.RECORD_ACK)

    def test_partial_without_question_projects_degraded_record_ack(self):
        messages = messages_for_observation(_partial_observation())
        self.assertEqual(len(messages), 1)
        intent = messages[0]
        self.assertEqual(intent.kind, MessageKind.RECORD_ACK)
        self.assertEqual(intent.args["result"], RecordAckResult.DEGRADED)
        self.assertEqual(intent.screen_target, ScreenTarget.STATUS)

    def test_partial_recorded_projects_recorded_no_step(self):
        """无追问且结构化成功（partial_recorded）→ RECORDED_NO_STEP（已记录）。"""
        messages = messages_for_observation(
            _partial_observation(acceptance_kind="partial_recorded")
        )
        self.assertEqual(len(messages), 1)
        intent = messages[0]
        self.assertEqual(intent.kind, MessageKind.RECORD_ACK)
        self.assertEqual(intent.args["result"], RecordAckResult.RECORDED_NO_STEP)
        self.assertEqual(intent.screen_target, ScreenTarget.STATUS)

    def test_full_structured_experiment_still_projects_recorded(self):
        """回归：CLI 完整观察投影逻辑不变。"""
        observation = UnifiedObservation(
            request_id="unified-1",
            session_id="s",
            segment_id=1,
            status=UnifiedObservationStatus.OBSERVED,
            destination="experiment_pipeline",
            clarification_action="no_action",
            acceptance_kind="structured_experiment",
        )
        messages = messages_for_observation(
            observation,
            experiment_step_number=3,
        )
        self.assertEqual(len(messages), 1)
        intent = messages[0]
        self.assertEqual(intent.kind, MessageKind.RECORD_ACK)
        self.assertEqual(intent.args["result"], RecordAckResult.RECORDED)
        self.assertEqual(intent.args["step_number"], 3)

    def test_failed_observation_still_projects_failed(self):
        """回归：失败观察投影逻辑不变。"""
        observation = UnifiedObservation(
            request_id="unified-1",
            session_id="s",
            segment_id=1,
            status=UnifiedObservationStatus.FAILED,
            error_type="SomeError",
        )
        messages = messages_for_observation(observation)
        self.assertEqual(len(messages), 1)
        intent = messages[0]
        self.assertEqual(intent.kind, MessageKind.RECORD_ACK)
        self.assertEqual(intent.args["result"], RecordAckResult.FAILED)


if __name__ == "__main__":
    unittest.main()
