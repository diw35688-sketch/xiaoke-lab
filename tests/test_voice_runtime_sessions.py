# -*- coding: utf-8 -*-

import unittest

from src.core.voice_runtime_state import VoiceRuntimeEventType
from web.voice_runtime_sessions import VoiceRuntimeSessionRegistry


class VoiceRuntimeSessionRegistryTests(unittest.TestCase):
    def test_speech_start_changes_only_the_named_conversation(self):
        sessions = VoiceRuntimeSessionRegistry()

        state_a, applied = sessions.consume("conversation-a", VoiceRuntimeEventType.USER_SPEECH_STARTED)

        self.assertTrue(applied)
        self.assertTrue(state_a.user_speaking)
        self.assertTrue(state_a.segment_capturing)
        self.assertIsNone(sessions.snapshot("conversation-b"))

    def test_duplicate_speech_start_is_idempotent_for_http_retry(self):
        sessions = VoiceRuntimeSessionRegistry()
        sessions.consume("conversation-a", VoiceRuntimeEventType.USER_SPEECH_STARTED)

        state, applied = sessions.consume("conversation-a", VoiceRuntimeEventType.USER_SPEECH_STARTED)

        self.assertFalse(applied)
        self.assertTrue(state.user_speaking)
        self.assertTrue(state.segment_capturing)

    def test_speech_pause_changes_only_speaking_and_is_idempotent(self):
        sessions = VoiceRuntimeSessionRegistry()
        sessions.consume("conversation-a", VoiceRuntimeEventType.USER_SPEECH_STARTED)

        paused, applied = sessions.consume(
            "conversation-a", VoiceRuntimeEventType.USER_SPEECH_PAUSED
        )
        retried, retry_applied = sessions.consume(
            "conversation-a", VoiceRuntimeEventType.USER_SPEECH_PAUSED
        )

        self.assertTrue(applied)
        self.assertFalse(paused.user_speaking)
        self.assertTrue(paused.segment_capturing)
        self.assertFalse(retry_applied)
        self.assertIs(retried, paused)
        self.assertIsNone(sessions.snapshot("conversation-b"))

    def test_speech_resume_reopens_speaking_in_same_segment_and_is_idempotent(self):
        sessions = VoiceRuntimeSessionRegistry()
        sessions.consume("conversation-a", VoiceRuntimeEventType.USER_SPEECH_STARTED)
        sessions.consume("conversation-a", VoiceRuntimeEventType.USER_SPEECH_PAUSED)

        resumed, applied = sessions.consume(
            "conversation-a", VoiceRuntimeEventType.USER_SPEECH_RESUMED
        )
        retried, retry_applied = sessions.consume(
            "conversation-a", VoiceRuntimeEventType.USER_SPEECH_RESUMED
        )

        self.assertTrue(applied)
        self.assertTrue(resumed.user_speaking)
        self.assertTrue(resumed.segment_capturing)
        self.assertFalse(retry_applied)
        self.assertIs(retried, resumed)
        self.assertIsNone(sessions.snapshot("conversation-b"))

    def test_started_after_pause_is_normalized_to_resume_in_same_segment(self):
        sessions = VoiceRuntimeSessionRegistry()
        sessions.consume("conversation-a", VoiceRuntimeEventType.USER_SPEECH_STARTED)
        sessions.consume("conversation-a", VoiceRuntimeEventType.USER_SPEECH_PAUSED)

        resumed, applied = sessions.consume(
            "conversation-a", VoiceRuntimeEventType.USER_SPEECH_STARTED
        )

        self.assertTrue(applied)
        self.assertTrue(resumed.user_speaking)
        self.assertTrue(resumed.segment_capturing)


if __name__ == "__main__":
    unittest.main()
