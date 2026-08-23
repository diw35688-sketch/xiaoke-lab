import unittest
from datetime import datetime, timedelta, timezone

from src.core.playback_context import PlaybackContext, PlaybackSessionPhase
from src.core.playback_decision import PlaybackDisposition, PlaybackReason
from src.core.playback_request import PlaybackRequest
from src.core.playback_rules import decide_playback
from src.core.presentation_intent import MessageKind, MessagePriority


NOW = datetime(2026, 8, 23, 11, 0, tzinfo=timezone.utc)


def _request(priority=MessagePriority.ACTIVE_QUESTION, **overrides):
    values = {
        "intent_id": "voice-1",
        "kind": MessageKind.CLARIFICATION,
        "priority": priority,
        "voice_text": "离心时间是多少？",
        "created_at": NOW - timedelta(seconds=5),
        "ttl": timedelta(seconds=20),
    }
    values.update(overrides)
    return PlaybackRequest(**values)


def _context(**overrides):
    values = {
        "observed_at": NOW,
        "user_speaking": False,
        "voice_input_busy": False,
        "tts_playing": False,
        "session_phase": PlaybackSessionPhase.ACTIVE,
        "active_tts_priority": None,
    }
    values.update(overrides)
    return PlaybackContext(**values)


def _assert_decision(test, request, context, disposition, reason):
    decision = decide_playback(request, context)
    test.assertEqual(decision.disposition, disposition)
    test.assertEqual(decision.reason, reason)


class PlaybackTimingRulesTests(unittest.TestCase):
    def test_idle_window_is_ready_for_voice_eligible_priorities(self):
        for priority in (
            MessagePriority.CRITICAL,
            MessagePriority.DIRECT_ACK,
            MessagePriority.ACTIVE_QUESTION,
            MessagePriority.REVIEW,
            MessagePriority.SUMMARY,
        ):
            with self.subTest(priority=priority):
                _assert_decision(
                    self,
                    _request(priority),
                    _context(),
                    PlaybackDisposition.READY,
                    PlaybackReason.PLAYBACK_WINDOW_OPEN,
                )

    def test_user_speech_has_precedence_over_asr_for_noncritical_items(self):
        _assert_decision(
            self,
            _request(MessagePriority.DIRECT_ACK),
            _context(user_speaking=True, voice_input_busy=True),
            PlaybackDisposition.DEFERRED,
            PlaybackReason.USER_SPEAKING,
        )

    def test_voice_input_busy_defers_noncritical_items(self):
        _assert_decision(
            self,
            _request(),
            _context(voice_input_busy=True),
            PlaybackDisposition.DEFERRED,
            PlaybackReason.VOICE_INPUT_BUSY,
        )

    def test_tts_busy_defers_ordinary_and_unknown_competing_items(self):
        for request, context in (
            (
                _request(MessagePriority.DIRECT_ACK),
                _context(
                    tts_playing=True,
                    active_tts_priority=MessagePriority.SUMMARY,
                ),
            ),
            (
                _request(MessagePriority.CRITICAL),
                _context(tts_playing=True),
            ),
        ):
            with self.subTest(priority=request.priority):
                _assert_decision(
                    self,
                    request,
                    context,
                    PlaybackDisposition.DEFERRED,
                    PlaybackReason.TTS_BUSY,
                )

    def test_only_critical_preempts_known_lower_priority_tts(self):
        context = _context(
            tts_playing=True,
            active_tts_priority=MessagePriority.DIRECT_ACK,
        )
        _assert_decision(
            self,
            _request(MessagePriority.CRITICAL),
            context,
            PlaybackDisposition.PREEMPT,
            PlaybackReason.CRITICAL_OVER_LOWER_PRIORITY,
        )
        _assert_decision(
            self,
            _request(MessagePriority.ACTIVE_QUESTION),
            context,
            PlaybackDisposition.DEFERRED,
            PlaybackReason.TTS_BUSY,
        )

    def test_critical_safety_can_be_ready_while_user_is_speaking(self):
        _assert_decision(
            self,
            _request(MessagePriority.CRITICAL),
            _context(user_speaking=True, voice_input_busy=True),
            PlaybackDisposition.READY,
            PlaybackReason.PLAYBACK_WINDOW_OPEN,
        )

    def test_expiry_boundary_is_dropped(self):
        request = _request(
            created_at=NOW - timedelta(seconds=20),
            ttl=timedelta(seconds=20),
        )
        _assert_decision(
            self,
            request,
            _context(),
            PlaybackDisposition.DROP,
            PlaybackReason.EXPIRED,
        )

    def test_ended_session_drops_before_other_timing_checks(self):
        _assert_decision(
            self,
            _request(),
            _context(
                user_speaking=True,
                session_phase=PlaybackSessionPhase.ENDED,
            ),
            PlaybackDisposition.DROP,
            PlaybackReason.SESSION_ENDED,
        )

    def test_inactive_session_defers(self):
        _assert_decision(
            self,
            _request(),
            _context(session_phase=PlaybackSessionPhase.INACTIVE),
            PlaybackDisposition.DEFERRED,
            PlaybackReason.SESSION_NOT_ACTIVE,
        )

    def test_closing_phase_allows_summary_but_defers_question(self):
        closing = _context(session_phase=PlaybackSessionPhase.CLOSING)
        _assert_decision(
            self,
            _request(MessagePriority.SUMMARY),
            closing,
            PlaybackDisposition.READY,
            PlaybackReason.PLAYBACK_WINDOW_OPEN,
        )
        _assert_decision(
            self,
            _request(MessagePriority.ACTIVE_QUESTION),
            closing,
            PlaybackDisposition.DEFERRED,
            PlaybackReason.SESSION_NOT_ACTIVE,
        )

    def test_routine_and_debug_never_gain_playback_permission(self):
        for priority in (MessagePriority.ROUTINE, MessagePriority.DEBUG):
            with self.subTest(priority=priority):
                _assert_decision(
                    self,
                    _request(priority),
                    _context(),
                    PlaybackDisposition.DROP,
                    PlaybackReason.CONTEXT_LOST,
                )

    def test_inputs_must_use_contract_types(self):
        with self.assertRaisesRegex(TypeError, "PlaybackRequest"):
            decide_playback(object(), _context())
        with self.assertRaisesRegex(TypeError, "PlaybackContext"):
            decide_playback(_request(), object())


if __name__ == "__main__":
    unittest.main()
