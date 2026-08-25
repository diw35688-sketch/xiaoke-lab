import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
for path in (str(WEB), str(ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from playback_runtime import ConversationPlaybackRegistry  # noqa: E402
from src.core.presentation_delivery import build_delivery_plan  # noqa: E402
from src.core.presentation_intent import (  # noqa: E402
    MessageKind,
    MessagePriority,
    PresentationIntent,
    ScreenTarget,
)
from src.core.playback_reevaluation import ReevaluationTrigger  # noqa: E402
from src.core.voice_runtime_state import VoiceRuntimeEventType  # noqa: E402
from voice_runtime_sessions import VoiceRuntimeSessionRegistry  # noqa: E402


NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def _producer_item(producer):
    specs = {
        "chat": (
            MessageKind.ASSISTANT_REPLY,
            {"text": "可以先检查温度是否稳定。"},
            MessagePriority.REVIEW,
            ScreenTarget.DIALOGUE,
            "turn-a:assistant",
        ),
        "record": (
            MessageKind.CLARIFICATION,
            {"question": "加热了多长时间？"},
            MessagePriority.ACTIVE_QUESTION,
            ScreenTarget.CURRENT_QUESTION,
            "turn-a:confirmation:record-question",
        ),
        "tool": (
            MessageKind.CLARIFICATION,
            {"question": "记录工具返回：加热了多长时间？"},
            MessagePriority.ACTIVE_QUESTION,
            ScreenTarget.DIALOGUE,
            "turn-a:assistant",
        ),
    }
    kind, args, priority, target, source = specs[producer]
    intent = PresentationIntent(
        intent_id=f"{producer}-intent",
        kind=kind,
        args=args,
        priority=priority,
        screen_target=target,
    )
    plan = build_delivery_plan(
        (intent,), ui_mode="user",
        source_block_ids={intent.intent_id: source},
    )
    return plan.voice_items[0]


class ThreeProducerAutoMatrixTests(unittest.TestCase):
    def test_all_producers_keep_visible_block_identity_through_scheduler(self):
        sessions = VoiceRuntimeSessionRegistry()
        registry = ConversationPlaybackRegistry(sessions, clock=lambda: NOW)

        for producer in ("chat", "record", "tool"):
            with self.subTest(producer=producer):
                item = _producer_item(producer)
                event = registry.authorize((item,), conversation_id=f"idle-{producer}")[0]
                self.assertEqual(event["authorization"], "READY")
                self.assertEqual(
                    event["items"][0]["source_block_id"], item.source_block_id
                )
                self.assertEqual(event["items"][0]["intent_id"], item.intent_id)

    def test_all_producers_defer_only_in_busy_conversation_and_release_unchanged(self):
        sessions = VoiceRuntimeSessionRegistry()
        registry = ConversationPlaybackRegistry(sessions, clock=lambda: NOW)
        sessions.consume("conversation-a", VoiceRuntimeEventType.USER_SPEECH_STARTED)

        expected_sources = {}
        for producer in ("chat", "record", "tool"):
            item = _producer_item(producer)
            expected_sources[item.intent_id] = item.source_block_id
            event = registry.authorize((item,), conversation_id="conversation-a")[0]
            self.assertEqual(event["authorization"], "DEFERRED")
            self.assertEqual(event["items"][0]["source_block_id"], item.source_block_id)

        ready_b = registry.authorize(
            (_producer_item("record"),), conversation_id="conversation-b"
        )[0]
        self.assertEqual(ready_b["authorization"], "READY")

        for event_type in (
            VoiceRuntimeEventType.USER_SPEECH_PAUSED,
            VoiceRuntimeEventType.SEGMENT_FINALIZED,
            VoiceRuntimeEventType.ASR_PROCESSING_STARTED,
            VoiceRuntimeEventType.ASR_PROCESSING_FINISHED,
        ):
            sessions.consume("conversation-a", event_type)
        released = registry.reevaluate(
            "conversation-a", ReevaluationTrigger.VOICE_INPUT_BECAME_IDLE
        )
        self.assertEqual(len(released), 3)
        for event in released:
            item = event["items"][0]
            self.assertEqual(event["authorization"], "READY")
            self.assertEqual(item["source_block_id"], expected_sources[item["intent_id"]])

    def test_expired_producer_output_drops_without_losing_source_identity(self):
        current = [NOW]
        sessions = VoiceRuntimeSessionRegistry()
        registry = ConversationPlaybackRegistry(
            sessions, clock=lambda: current[0], ttl=timedelta(seconds=20)
        )
        sessions.consume("conversation-a", VoiceRuntimeEventType.USER_SPEECH_STARTED)
        item = _producer_item("record")
        registry.authorize((item,), conversation_id="conversation-a")
        for event_type in (
            VoiceRuntimeEventType.USER_SPEECH_PAUSED,
            VoiceRuntimeEventType.SEGMENT_FINALIZED,
            VoiceRuntimeEventType.ASR_PROCESSING_STARTED,
            VoiceRuntimeEventType.ASR_PROCESSING_FINISHED,
        ):
            sessions.consume("conversation-a", event_type)
        current[0] = NOW + timedelta(seconds=21)

        dropped = registry.reevaluate(
            "conversation-a", ReevaluationTrigger.VOICE_INPUT_BECAME_IDLE
        )[0]
        self.assertEqual(dropped["authorization"], "DROP")
        self.assertEqual(dropped["items"][0]["source_block_id"], item.source_block_id)

    def test_production_adapters_bind_request_turn_to_visible_blocks(self):
        chat = (WEB / "api" / "chat.py").read_text(encoding="utf-8")
        record = (WEB / "api" / "record.py").read_text(encoding="utf-8")
        stream = (WEB / "frontend" / "streaming_chat_v2.js").read_text(encoding="utf-8")
        context = (WEB / "frontend" / "conversation_context_blocks.js").read_text(encoding="utf-8")
        self.assertIn('assistant_block_id = f"{spoken_turn_id}:spoken"', chat)
        self.assertIn('f"{turn_id}:confirmation:{intent.intent_id}"', record)
        self.assertIn("request_id: localRequestId, turn_id: localTurnId", stream)
        self.assertIn("confirmation:${message.intent_id || index}", context)


if __name__ == "__main__":
    unittest.main()
