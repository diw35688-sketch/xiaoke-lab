# -*- coding: utf-8 -*-
"""web/degraded_producer.py 降级生产者单测：不依赖网络与真实服务。

覆盖：追问/记录两类部分观察的字段映射、身份透传、missing_fields 转 tuple、
标志与文本矛盾的边界、空 evaluation、畸形输入降级 FAILED、
以及与投影层 messages_for_observation 的联动（链路通）。
"""

import sys
import unittest
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

import degraded_producer  # noqa: E402
from src.core.presentation_copy import RecordAckResult  # noqa: E402
from src.core.presentation_intent import (  # noqa: E402
    MessageKind,
    ScreenTarget,
)
from src.core.presentation_projection import messages_for_observation  # noqa: E402
from src.core.unified_observer import UnifiedObservationStatus  # noqa: E402


def _produce(evaluation, **identity):
    return degraded_producer.produce_partial_observation(
        request_id=identity.get("request_id", "web-1"),
        session_id=identity.get("session_id", "s"),
        segment_id=identity.get("segment_id", 1),
        evaluation=evaluation,
    )


class DegradedProducerFollowupTests(unittest.TestCase):
    """追问类部分观察。"""

    def test_followup_evaluation_produces_clarification_observation(self):
        evaluation = {
            "missing_fields": ["duration"],
            "follow_up_question": "缺时长，请补充",
            "follow_up_required": True,
        }
        observation = _produce(evaluation)
        self.assertEqual(observation.status, UnifiedObservationStatus.OBSERVED)
        self.assertTrue(observation.partial)
        self.assertEqual(observation.destination, "clarification_context")
        self.assertIsNone(observation.acceptance_kind)
        self.assertEqual(observation.missing_fields, ("duration",))
        self.assertTrue(observation.follow_up_required)
        self.assertEqual(observation.partial_question, "缺时长，请补充")

    def test_identity_fields_passthrough(self):
        observation = _produce(
            {"follow_up_question": "缺时长，请补充"},
            request_id="web-req-9",
            session_id="sess-2",
            segment_id=7,
        )
        self.assertEqual(observation.request_id, "web-req-9")
        self.assertEqual(observation.session_id, "sess-2")
        self.assertEqual(observation.segment_id, 7)


class DegradedProducerRecordTests(unittest.TestCase):
    """记录类部分观察。"""

    def test_record_evaluation_produces_degraded_record_observation(self):
        evaluation = {
            "missing_fields": [],
            "follow_up_question": None,
            "follow_up_required": False,
        }
        observation = _produce(evaluation)
        self.assertEqual(observation.status, UnifiedObservationStatus.OBSERVED)
        self.assertTrue(observation.partial)
        self.assertEqual(observation.destination, "experiment_pipeline")
        self.assertEqual(observation.acceptance_kind, "degraded_evidence_note")
        self.assertEqual(observation.missing_fields, ())
        self.assertFalse(observation.follow_up_required)
        self.assertIsNone(observation.partial_question)

    def test_missing_fields_list_converted_to_tuple(self):
        observation = _produce({"missing_fields": ["a", "b"]})
        self.assertEqual(observation.missing_fields, ("a", "b"))

    def test_empty_evaluation_produces_record_observation(self):
        observation = _produce({})
        self.assertEqual(observation.status, UnifiedObservationStatus.OBSERVED)
        self.assertEqual(observation.destination, "experiment_pipeline")
        self.assertEqual(observation.acceptance_kind, "degraded_evidence_note")
        self.assertIsNone(observation.partial_question)
        self.assertEqual(observation.missing_fields, ())

    def test_record_with_entities_produces_partial_recorded(self):
        """无追问但抽到实体 → partial_recorded（已记录，不是降级）。"""
        observation = degraded_producer.produce_partial_observation(
            request_id="web-1",
            session_id="s",
            segment_id=1,
            evaluation={"follow_up_question": None, "follow_up_required": False},
            entities={"action": "加入", "object": "缓冲液"},
        )
        self.assertEqual(observation.status, UnifiedObservationStatus.OBSERVED)
        self.assertEqual(observation.destination, "experiment_pipeline")
        self.assertEqual(observation.acceptance_kind, "partial_recorded")
        self.assertIsNone(observation.partial_question)


class DegradedProducerBoundaryTests(unittest.TestCase):
    """标志与文本矛盾的边界：以追问文本为准。"""

    def test_required_flag_true_but_empty_question_counts_as_record(self):
        evaluation = {
            "follow_up_required": True,
            "follow_up_question": "",
        }
        observation = _produce(evaluation)
        self.assertEqual(observation.destination, "experiment_pipeline")
        self.assertEqual(observation.acceptance_kind, "degraded_evidence_note")
        self.assertIsNone(observation.partial_question)
        # 标志如实抄录，但不参与判定
        self.assertTrue(observation.follow_up_required)

    def test_question_with_blank_spaces_counts_as_record(self):
        observation = _produce({"follow_up_question": "   "})
        self.assertEqual(observation.destination, "experiment_pipeline")
        self.assertIsNone(observation.partial_question)


class DegradedProducerFailureTests(unittest.TestCase):
    """畸形输入降级为 FAILED 观察，永不抛异常。"""

    def test_none_evaluation_produces_failed_observation(self):
        observation = _produce(None)
        self.assertEqual(observation.status, UnifiedObservationStatus.FAILED)
        self.assertEqual(observation.error_type, "TypeError")

    def test_non_dict_evaluation_produces_failed_observation(self):
        observation = _produce("not-a-dict")
        self.assertEqual(observation.status, UnifiedObservationStatus.FAILED)
        self.assertEqual(observation.error_type, "TypeError")


class DegradedProducerProjectionLinkTests(unittest.TestCase):
    """降级生产者 → 投影层联动：链路通且意图正确。"""

    def test_followup_observation_projects_clarification(self):
        observation = _produce(
            {"follow_up_question": "缺时长，请补充", "missing_fields": ["duration"]}
        )
        messages = messages_for_observation(observation)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].kind, MessageKind.CLARIFICATION)
        self.assertEqual(messages[0].args["question"], "缺时长，请补充")
        self.assertEqual(messages[0].screen_target, ScreenTarget.CURRENT_QUESTION)

    def test_record_observation_projects_degraded_record_ack(self):
        observation = _produce({})
        messages = messages_for_observation(observation)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].kind, MessageKind.RECORD_ACK)
        self.assertEqual(messages[0].args["result"], RecordAckResult.DEGRADED)
        self.assertEqual(messages[0].screen_target, ScreenTarget.STATUS)

    def test_failed_observation_projects_failed_record_ack(self):
        observation = _produce(None)
        messages = messages_for_observation(observation)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].kind, MessageKind.RECORD_ACK)
        self.assertEqual(messages[0].args["result"], RecordAckResult.FAILED)


if __name__ == "__main__":
    unittest.main()
