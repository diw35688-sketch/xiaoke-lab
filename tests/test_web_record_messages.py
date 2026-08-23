# -*- coding: utf-8 -*-
"""web/api/record.py 影子 messages 接线测试：不依赖网络与真实服务。

mock 掉 llm_bridge.extract、数据库函数与 domain.evaluate，
验证：/record 返回里的 messages 影子字段出现与结构正确、
原始字段（evaluation/transcript/entities/segment_id）保留、
messages 不落库（白名单九列之外）、畸形 evaluation 降级为失败消息。
"""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

import api.record as record_api  # noqa: E402
from api.record import RecordPayload, _record_events, record  # noqa: E402

FOLLOWUP_EVALUATION = {
    "missing_fields": ["duration"],
    "follow_up_question": "缺时长，请补充",
    "follow_up_required": True,
    "deviations": [],
    "sourced_values": {},
}

RECORD_EVALUATION = {
    "missing_fields": [],
    "follow_up_question": None,
    "follow_up_required": False,
    "deviations": [],
    "sourced_values": {},
}

captured_items: list = []


def _fake_save(item):
    captured_items.append(item)
    return dict(item)


class RecordMessagesShadowTests(unittest.TestCase):
    """B3 影子 messages：出现、结构正确、原始字段保留。"""

    def setUp(self):
        captured_items.clear()

    def _call(self, evaluation, transcript="加热到60摄氏度"):
        with mock.patch(
            "api.record.llm_bridge.extract",
            return_value={"events": [], "degraded": False},
        ), mock.patch(
            "api.record.current_session_id", return_value="test-session"
        ), mock.patch("api.record.next_segment_id", return_value=1), mock.patch(
            "api.record.list_records", return_value=[]
        ), mock.patch(
            "api.record.save_record", side_effect=_fake_save
        ), mock.patch(
            "api.record.domain.evaluate", return_value=evaluation
        ):
            return record(RecordPayload(transcript=transcript))

    def test_record_returns_messages_shadow_field_with_clarification(self):
        result = self._call(FOLLOWUP_EVALUATION)
        self.assertIn("messages", result)
        self.assertEqual(len(result["messages"]), 1)
        message = result["messages"][0]
        self.assertEqual(message["kind"], "clarification")
        self.assertEqual(message["screen_target"], "current_question")
        self.assertIn("小科：缺时长，请补充", message["text"])

    def test_record_voice_candidate_is_scheduler_authorized(self):
        result = self._call(FOLLOWUP_EVALUATION)

        self.assertEqual(len(result["voice_delivery_events"]), 1)
        event = result["voice_delivery_events"][0]
        self.assertEqual(event["type"], "voice_delivery")
        self.assertEqual(event["authorization"], "READY")
        self.assertEqual(event["items"][0]["intent_id"], result["messages"][0]["intent_id"])

    def test_silent_record_ack_creates_no_playback_event(self):
        result = self._call(RECORD_EVALUATION)

        self.assertEqual(result["voice_delivery_events"], [])

    def test_record_preserves_original_fields(self):
        result = self._call(FOLLOWUP_EVALUATION)
        self.assertEqual(result["evaluation"], FOLLOWUP_EVALUATION)
        self.assertEqual(result["transcript"], "加热到60摄氏度")
        self.assertEqual(result["segment_id"], 1)
        self.assertEqual(result["session_id"], "test-session")
        self.assertIn("entities", result)

    def test_record_no_followup_produces_recorded_ack(self):
        """无追问且规则抽取兜底抽到实体 → 已记录（不是降级"不可用"）。"""
        result = self._call(RECORD_EVALUATION)
        self.assertEqual(len(result["messages"]), 1)
        message = result["messages"][0]
        self.assertEqual(message["kind"], "record_ack")
        self.assertEqual(message["screen_target"], "status")
        self.assertIn("已记录", message["text"])
        self.assertNotIn("不可用", message["text"])

    def test_record_no_followup_no_entities_produces_degraded_ack(self):
        """无追问且抽不到任何实体 → 真降级"结构化处理暂时不可用"。"""
        result = self._call(RECORD_EVALUATION, transcript="溶液颜色变蓝")
        self.assertEqual(len(result["messages"]), 1)
        message = result["messages"][0]
        self.assertEqual(message["kind"], "record_ack")
        self.assertIn("原始记录已保存", message["text"])
        self.assertIn("不可用", message["text"])

    def test_messages_not_persisted_into_database_item(self):
        """影子字段不入库：save_record 收到的 item 不含 messages。"""
        self._call(FOLLOWUP_EVALUATION)
        self.assertEqual(len(captured_items), 1)
        self.assertNotIn("messages", captured_items[0])
        self.assertIn("evaluation", captured_items[0])

    def test_none_evaluation_produces_failed_message(self):
        """畸形 evaluation（None）→ 降级为失败消息，接口不崩。"""
        result = self._call(None)
        self.assertEqual(len(result["messages"]), 1)
        message = result["messages"][0]
        self.assertEqual(message["kind"], "record_ack")
        self.assertIn("处理失败", message["text"])

    def test_messages_are_json_serializable(self):
        result = self._call(FOLLOWUP_EVALUATION)
        json.dumps(result["messages"])  # 不抛即通过

    def test_save_failure_does_not_generate_messages(self):
        """落盘失败时不能先生成任何声称成功或追问的用户消息。"""
        with mock.patch(
            "api.record.llm_bridge.extract",
            return_value={"events": [], "degraded": False},
        ), mock.patch(
            "api.record.current_session_id", return_value="test-session"
        ), mock.patch(
            "api.record.next_segment_id", return_value=1
        ), mock.patch(
            "api.record.list_records", return_value=[]
        ), mock.patch(
            "api.record.domain.evaluate", return_value=FOLLOWUP_EVALUATION
        ), mock.patch(
            "api.record.save_record", side_effect=OSError("disk full")
        ), mock.patch(
            "api.record.web_renderer.WebRenderer.render_many"
        ) as render_many:
            with self.assertRaises(HTTPException):
                record(RecordPayload(transcript="加热到60摄氏度"))
        render_many.assert_not_called()

    def test_record_delegates_to_shared_service_before_web_rendering(self):
        """HTTP 入口使用共享服务，同时保留旧返回字段。"""
        with mock.patch(
            "api.record._build_record_service",
            wraps=record_api._build_record_service,
        ) as builder:
            result = self._call(FOLLOWUP_EVALUATION)
        builder.assert_called_once()
        self.assertEqual(result["evaluation"], FOLLOWUP_EVALUATION)
        self.assertEqual(result["messages"][0]["kind"], "clarification")

    def test_stream_sends_status_before_committed_result(self):
        committed = {
            "segment_id": 1,
            "messages": [],
            "voice_delivery_events": [],
        }
        with mock.patch("api.record._record_response", return_value=committed):
            events = [
                json.loads(line)
                for line in _record_events("加热样品", extract=True)
            ]

        self.assertEqual(events[0]["type"], "record_status")
        self.assertEqual(events[0]["phase"], "understanding")
        self.assertEqual(
            events[1], {"type": "record_result", "data": committed}
        )

    def test_stream_save_failure_emits_no_result(self):
        with mock.patch(
            "api.record._record_response",
            side_effect=record_api.RecordPersistenceError("disk full"),
        ):
            events = [
                json.loads(line)
                for line in _record_events("加热样品", extract=True)
            ]

        self.assertEqual(
            [event["type"] for event in events],
            ["record_status", "record_error"],
        )
        self.assertIn("disk full", events[1]["detail"])


if __name__ == "__main__":
    unittest.main()
