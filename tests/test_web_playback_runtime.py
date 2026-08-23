import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from playback_runtime import WebPlaybackService  # noqa: E402
from src.core.deferred_playback_queue import DeferredPlaybackQueue  # noqa: E402
from src.core.playback_context_factory import PlaybackContextFactory  # noqa: E402
from src.core.playback_gate import PlaybackGate  # noqa: E402
from src.core.playback_scheduler import PlaybackScheduler  # noqa: E402
from src.core.presentation_delivery import VoiceDeliveryItem  # noqa: E402
from src.core.presentation_intent import MessageKind, MessagePriority  # noqa: E402
from src.core.voice_runtime_state import (  # noqa: E402
    VoiceRuntimeState,
    VoiceStateCoordinator,
)


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


if __name__ == "__main__":
    unittest.main()
