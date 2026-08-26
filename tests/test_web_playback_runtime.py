import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from playback_runtime import ConversationPlaybackRegistry, WebPlaybackService  # noqa: E402
from src.core.deferred_playback_queue import DeferredPlaybackQueue  # noqa: E402
from src.core.playback_context_factory import PlaybackContextFactory  # noqa: E402
from src.core.playback_gate import PlaybackGate  # noqa: E402
from src.core.playback_scheduler import PlaybackScheduler  # noqa: E402
from src.core.presentation_delivery import VoiceDeliveryItem  # noqa: E402
from src.core.presentation_intent import MessageKind, MessagePriority  # noqa: E402
from src.core.voice_runtime_state import (  # noqa: E402
    VoiceRuntimeEventType,
    VoiceRuntimeState,
    VoiceStateCoordinator,
)
from src.core.playback_reevaluation import ReevaluationTrigger  # noqa: E402
from src.core.tts_adapter import TTSExecutionEvent, TTSExecutionEventType  # noqa: E402
from voice_runtime_sessions import VoiceRuntimeSessionRegistry  # noqa: E402


NOW = datetime(2026, 8, 23, 16, 0, tzinfo=timezone.utc)


class RecordingBrowserPort:
    def __init__(self):
        self.played = []
        self.stop_calls = 0

    def play(self, request):
        self.played.append(request)

    def stop(self):
        self.stop_calls += 1


def _item(intent_id="ask-1"):
    return VoiceDeliveryItem(
        intent_id,
        MessageKind.CLARIFICATION,
        MessagePriority.ACTIVE_QUESTION,
        "离心时间是多少？",
    )


def _service(state=None, *, observed_at=NOW, created_at=NOW):
    coordinator = VoiceStateCoordinator(state)
    port = RecordingBrowserPort()
    scheduler = PlaybackScheduler(
        PlaybackContextFactory(coordinator, lambda: observed_at),
        PlaybackGate(),
        DeferredPlaybackQueue(),
        port,
    )
    return WebPlaybackService(
        scheduler,
        clock=lambda: created_at,
        ttl=timedelta(seconds=20),
    ), port


class WebPlaybackServiceTests(unittest.TestCase):
    def test_idle_candidate_becomes_ready_only_after_scheduler_handoff(self):
        service, port = _service()

        events = service.authorize((_item(),))

        self.assertEqual(len(port.played), 1)
        self.assertEqual(events[0]["authorization"], "READY")
        self.assertEqual(events[0]["reason"], "playback_window_open")
        self.assertEqual(events[0]["items"][0]["intent_id"], "ask-1")

    def test_busy_voice_input_is_deferred_and_never_handed_to_browser(self):
        service, port = _service(
            VoiceRuntimeState(segment_capturing=True)
        )

        events = service.authorize((_item(),))

        self.assertEqual(port.played, [])
        self.assertEqual(events[0]["authorization"], "DEFERRED")
        self.assertEqual(events[0]["reason"], "voice_input_busy")

    def test_expired_candidate_is_dropped_and_never_handed_to_browser(self):
        service, port = _service(
            observed_at=NOW + timedelta(seconds=20),
            created_at=NOW,
        )

        events = service.authorize((_item(),))

        self.assertEqual(port.played, [])
        self.assertEqual(events[0]["authorization"], "DROP")
        self.assertEqual(events[0]["reason"], "expired")

    def test_empty_batch_has_no_scheduler_or_browser_side_effect(self):
        service, port = _service()

        self.assertEqual(service.authorize(()), ())
        self.assertEqual(port.played, [])


class ConversationPlaybackRegistryTests(unittest.TestCase):
    def test_barge_in_clears_old_tts_and_next_turn_can_play(self):
        sessions = VoiceRuntimeSessionRegistry()
        registry = ConversationPlaybackRegistry(sessions, clock=lambda: NOW)
        first = registry.authorize(
            (_item("old-reply"),), conversation_id="conversation-a"
        )
        self.assertEqual(first[0]["authorization"], "READY")
        sessions.consume(
            "conversation-a",
            VoiceRuntimeEventType.TTS_STARTED,
            tts_priority=MessagePriority.ACTIVE_QUESTION,
        )

        interrupted = sessions.consume(
            "conversation-a", VoiceRuntimeEventType.USER_SPEECH_STARTED
        )[0]
        self.assertFalse(interrupted.tts_playing)

        for event_type in (
            VoiceRuntimeEventType.USER_SPEECH_PAUSED,
            VoiceRuntimeEventType.SEGMENT_FINALIZED,
            VoiceRuntimeEventType.ASR_PROCESSING_STARTED,
            VoiceRuntimeEventType.ASR_PROCESSING_FINISHED,
        ):
            sessions.consume("conversation-a", event_type)

        next_reply = registry.authorize(
            (_item("new-reply"),), conversation_id="conversation-a"
        )
        self.assertEqual(next_reply[0]["authorization"], "READY")
        self.assertEqual(
            next_reply[0]["items"][0]["intent_id"], "new-reply"
        )

    def test_named_session_state_defers_only_its_own_playback_and_then_releases(self):
        sessions = VoiceRuntimeSessionRegistry()
        registry = ConversationPlaybackRegistry(sessions, clock=lambda: NOW)
        sessions.consume("conversation-a", VoiceRuntimeEventType.USER_SPEECH_STARTED)

        deferred = registry.authorize((_item("ask-a"),), conversation_id="conversation-a")
        ready_b = registry.authorize((_item("ask-b"),), conversation_id="conversation-b")

        self.assertEqual(deferred[0]["authorization"], "DEFERRED")
        self.assertEqual(deferred[0]["reason"], "user_speaking")
        self.assertEqual(ready_b[0]["authorization"], "READY")

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

        self.assertEqual(released[0]["authorization"], "READY")
        self.assertEqual(released[0]["items"][0]["intent_id"], "ask-a")

    def test_tts_finish_releases_item_deferred_by_same_session_playback(self):
        sessions = VoiceRuntimeSessionRegistry()
        registry = ConversationPlaybackRegistry(sessions, clock=lambda: NOW)
        registry.authorize((_item("active"),), conversation_id="conversation-a")
        sessions.consume(
            "conversation-a",
            VoiceRuntimeEventType.TTS_STARTED,
            tts_priority=MessagePriority.ACTIVE_QUESTION,
        )
        registry.handle_tts_event(
            "conversation-a",
            TTSExecutionEvent(
                TTSExecutionEventType.STARTED,
                "active",
                MessagePriority.ACTIVE_QUESTION,
            ),
        )

        deferred = registry.authorize(
            (_item("waiting"),), conversation_id="conversation-a"
        )
        self.assertEqual(deferred[0]["reason"], "tts_busy")

        sessions.consume("conversation-a", VoiceRuntimeEventType.TTS_FINISHED)
        registry.handle_tts_event(
            "conversation-a",
            TTSExecutionEvent(
                TTSExecutionEventType.FINISHED,
                "active",
                MessagePriority.ACTIVE_QUESTION,
            ),
        )
        released = registry.reevaluate(
            "conversation-a", ReevaluationTrigger.TTS_PLAYBACK_ENDED
        )

        self.assertEqual(released[0]["authorization"], "READY")
        self.assertEqual(released[0]["items"][0]["intent_id"], "waiting")

    def test_expired_deferred_item_is_dropped_when_voice_input_becomes_idle(self):
        current = [NOW]
        sessions = VoiceRuntimeSessionRegistry()
        registry = ConversationPlaybackRegistry(sessions, clock=lambda: current[0])
        sessions.consume("conversation-a", VoiceRuntimeEventType.USER_SPEECH_STARTED)
        deferred = registry.authorize(
            (_item("stale"),), conversation_id="conversation-a"
        )
        self.assertEqual(deferred[0]["authorization"], "DEFERRED")

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
        )

        self.assertEqual(dropped[0]["authorization"], "DROP")
        self.assertEqual(dropped[0]["reason"], "expired")


if __name__ == "__main__":
    unittest.main()
