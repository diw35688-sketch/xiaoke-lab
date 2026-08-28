"""Legacy /record response is a thin projection of committed unified Turns."""

import json
import sys
import unittest
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

WEB = Path(__file__).resolve().parent.parent / "web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

import api.record as record_api  # noqa: E402
from api.record import _record_events, _record_response  # noqa: E402
from src.core.presentation_delivery import VoiceDeliveryItem  # noqa: E402
from src.core.presentation_intent import MessageKind, MessagePriority  # noqa: E402


class _Store:
    def load_lab_record(self, request_id):
        return {
            "id": 9, "created_at": "now", "request_id": request_id,
            "conversation_id": "c1", "turn_id": "t1",
            "session_id": "lab1", "segment_id": 3,
            "transcript": "加热到60摄氏度",
            "entities": {"temperature": "60摄氏度"},
            "extraction": {"events": []},
            "extraction_source": "llm",
            "evaluation": {"follow_up_required": False},
            "step": {"mode": "free"}, "at": "2026-08-26T00:00:00",
        }


class _Service:
    def __init__(self, *, replayed=False, with_voice=True):
        self.store = _Store()
        self.turns = []
        self.completed = SimpleNamespace(
            replayed=replayed,
            result={
                "turn": {"blocks": [
                    {"type": "record_card", "payload": {
                        "entities": {"temperature": "60摄氏度"}
                    }},
                    {"type": "assistant_text", "payload": {"text": "已记录。"}},
                ]},
                "business": {"kind": "experiment", "segment_id": 3},
                "timing": {"marks": {}},
            },
            voice_items=((VoiceDeliveryItem(
                "intent-1", MessageKind.RECORD_ACK, MessagePriority.ROUTINE,
                "已记录。", "t1:assistant", 20,
            ),) if with_voice else ()),
        )

    def submit(self, turn):
        self.turns.append(turn)
        future = Future()
        future.set_result(self.completed)
        return SimpleNamespace(future=future)


class RecordCompatibilityAdapterTests(unittest.TestCase):
    def _call(self, *, replayed=False, with_voice=True):
        service = _Service(replayed=replayed, with_voice=with_voice)
        with mock.patch("api.turn.turn_application_service", service), mock.patch(
            "api.record.current_session_id", return_value="lab1"
        ), mock.patch(
            "api.record.web_playback_service.authorize",
            return_value=({"type": "voice_delivery", "authorization": "READY"},),
        ) as authorize:
            result = _record_response(
                "加热到60摄氏度", extract=True, conversation_id="c1",
                request_id="r1", turn_id="t1",
            )
        return service, result, authorize

    def test_adapter_submits_one_text_experiment_turn(self):
        service, result, _ = self._call()
        self.assertEqual(len(service.turns), 1)
        turn = service.turns[0]
        self.assertEqual(turn.request_id, "r1")
        self.assertEqual(turn.raw_text, "加热到60摄氏度")
        self.assertIsNone(turn.asr_result)
        self.assertEqual(result["evaluation"], {"follow_up_required": False})
        self.assertEqual(result["entities"], {"temperature": "60摄氏度"})

    def test_response_preserves_old_message_shape(self):
        _, result, _ = self._call()
        message = result["messages"][0]
        self.assertEqual(message["intent_id"], "intent-1")
        self.assertEqual(message["kind"], "record_ack")
        self.assertEqual(message["text"], "已记录。")
        json.dumps(result, ensure_ascii=False)

    def test_replay_never_reauthorizes_voice(self):
        _, result, authorize = self._call(replayed=True)
        authorize.assert_not_called()
        self.assertEqual(result["voice_delivery_events"], [])

    def test_new_result_authorizes_only_service_voice_items(self):
        _, result, authorize = self._call()
        authorize.assert_called_once()
        self.assertEqual(result["voice_delivery_events"][0]["type"], "voice_delivery")

    def test_stream_sends_status_before_committed_result(self):
        committed = {"segment_id": 1, "messages": [], "voice_delivery_events": []}
        with mock.patch("api.record._record_response", return_value=committed):
            events = [json.loads(line) for line in _record_events("加热", extract=True)]
        self.assertEqual([event["type"] for event in events], [
            "record_status", "record_result"
        ])

    def test_stream_failure_emits_no_result(self):
        with mock.patch(
            "api.record._record_response", side_effect=RuntimeError("disk full")
        ):
            events = [json.loads(line) for line in _record_events("加热", extract=True)]
        self.assertEqual([event["type"] for event in events], [
            "record_status", "record_error"
        ])


if __name__ == "__main__":
    unittest.main()
