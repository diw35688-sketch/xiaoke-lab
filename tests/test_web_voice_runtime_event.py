# -*- coding: utf-8 -*-

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from api.voice_runtime import router, voice_runtime_sessions, web_playback_service
from fastapi import FastAPI


class WebVoiceRuntimeEventTests(unittest.TestCase):
    def setUp(self):
        voice_runtime_sessions.clear()
        web_playback_service.clear()
        app = FastAPI()
        app.include_router(router)
        # 这些用例测的是语音运行时路由本身，不是登录。
        # 用依赖覆盖注入一个固定用户，既满足归属参数，又不把认证逻辑
        # 掺进无关测试里（登录闸门另有 test_auth_api 专门把关）。
        from api.auth import require_user
        app.dependency_overrides[require_user] = lambda: {
            "id": "test-user", "username": "tester", "display_name": "tester",
            "is_admin": True, "is_active": True,
        }
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        voice_runtime_sessions.clear()
        web_playback_service.clear()

    @patch("api.voice_runtime.conversation_exists", return_value=True)
    def test_user_speech_started_reaches_named_session_state(self, _exists):
        response = self.client.post(
            "/voice/runtime/event",
            json={"conversation_id": "conversation-a", "type": "user_speech_started"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["conversation_id"], "conversation-a")
        self.assertTrue(response.json()["state"]["user_speaking"])
        self.assertTrue(response.json()["state"]["segment_capturing"])
        self.assertIsNone(voice_runtime_sessions.snapshot("conversation-b"))

    @patch("api.voice_runtime.conversation_exists", return_value=True)
    def test_user_speech_paused_keeps_same_session_segment_open(self, _exists):
        self.client.post(
            "/voice/runtime/event",
            json={"conversation_id": "conversation-a", "type": "user_speech_started"},
        )

        response = self.client.post(
            "/voice/runtime/event",
            json={"conversation_id": "conversation-a", "type": "user_speech_paused"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["conversation_id"], "conversation-a")
        self.assertFalse(response.json()["state"]["user_speaking"])
        self.assertTrue(response.json()["state"]["segment_capturing"])
        self.assertIsNone(voice_runtime_sessions.snapshot("conversation-b"))

    @patch("api.voice_runtime.conversation_exists", return_value=True)
    def test_user_speech_resumed_reuses_same_session_segment(self, _exists):
        for event_type in ("user_speech_started", "user_speech_paused"):
            self.client.post(
                "/voice/runtime/event",
                json={"conversation_id": "conversation-a", "type": event_type},
            )

        response = self.client.post(
            "/voice/runtime/event",
            json={"conversation_id": "conversation-a", "type": "user_speech_resumed"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["conversation_id"], "conversation-a")
        self.assertTrue(response.json()["state"]["user_speaking"])
        self.assertTrue(response.json()["state"]["segment_capturing"])
        self.assertIsNone(voice_runtime_sessions.snapshot("conversation-b"))

    @patch("api.voice_runtime.conversation_exists", return_value=True)
    def test_browser_started_after_pause_is_accepted_as_resume(self, _exists):
        responses = []
        for event_type in (
            "user_speech_started",
            "user_speech_paused",
            "user_speech_started",
        ):
            responses.append(
                self.client.post(
                    "/voice/runtime/event",
                    json={"conversation_id": "conversation-a", "type": event_type},
                )
            )

        self.assertEqual([response.status_code for response in responses], [200, 200, 200])
        state = responses[-1].json()["state"]
        self.assertTrue(state["user_speaking"])
        self.assertTrue(state["segment_capturing"])

    @patch("api.voice_runtime.conversation_exists", return_value=False)
    def test_unknown_conversation_is_rejected_instead_of_created(self, _exists):
        response = self.client.post(
            "/voice/runtime/event",
            json={"conversation_id": "missing", "type": "user_speech_started"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertIsNone(voice_runtime_sessions.snapshot("missing"))

    @patch("api.voice_runtime.conversation_exists", return_value=True)
    def test_finalized_and_asr_lifecycle_close_the_same_session_input(self, _exists):
        for event_type in (
            "user_speech_started",
            "user_speech_paused",
            "segment_finalized",
            "asr_processing_started",
        ):
            response = self.client.post(
                "/voice/runtime/event",
                json={"conversation_id": "conversation-a", "type": event_type},
            )
            self.assertEqual(response.status_code, 200)

        processing = response.json()["state"]
        self.assertFalse(processing["segment_capturing"])
        self.assertTrue(processing["asr_processing"])

        finished = self.client.post(
            "/voice/runtime/event",
            json={
                "conversation_id": "conversation-a",
                "type": "asr_processing_finished",
            },
        )
        self.assertEqual(finished.status_code, 200)
        self.assertFalse(finished.json()["state"]["asr_processing"])

    @patch("api.voice_runtime.conversation_exists", return_value=True)
    def test_tts_lifecycle_requires_identity_and_clears_playing_state(self, _exists):
        invalid = self.client.post(
            "/voice/runtime/event",
            json={"conversation_id": "conversation-a", "type": "tts_started"},
        )
        self.assertEqual(invalid.status_code, 422)

        common = {
            "conversation_id": "conversation-a",
            "intent_id": "ask-a",
            "priority": "ACTIVE_QUESTION",
        }
        started = self.client.post(
            "/voice/runtime/event", json={**common, "type": "tts_started"}
        )
        finished = self.client.post(
            "/voice/runtime/event", json={**common, "type": "tts_finished"}
        )

        self.assertEqual(started.status_code, 200)
        self.assertTrue(started.json()["state"]["tts_playing"])
        self.assertEqual(finished.status_code, 200)
        self.assertFalse(finished.json()["state"]["tts_playing"])

    @patch("api.voice_runtime.conversation_exists", return_value=True)
    def test_client_playback_result_is_observable_without_changing_state(self, _exists):
        response = self.client.post(
            "/voice/runtime/client-result",
            json={
                "conversation_id": "conversation-a",
                "code": "PLAYBACK_DISABLED",
                "authorization": "READY",
                "reason": "playback_window_open",
                "intent_id": "reply-a",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"accepted": True})
        self.assertIsNone(voice_runtime_sessions.snapshot("conversation-a"))

    @patch("api.voice_runtime.ensure_conversation", return_value="conversation-startup")
    @patch("api.voice_runtime.settings_store.current")
    def test_startup_welcome_uses_formal_voice_delivery(self, current, ensure):
        current.return_value.tts_speed = 1.2
        response = self.client.post(
            "/voice/runtime/startup",
            json={
                "source_block_id": "turn-startup:voice-startup",
                "local_hour": 20,
                "local_minute": 5,
                "mode": "free",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["conversation_id"], "conversation-startup")
        self.assertEqual(
            data["welcome_text"],
            "晚上好，现在是20点05分，当前为自由实验记录。",
        )
        delivery = data["voice_delivery_events"][0]
        self.assertEqual(delivery["type"], "voice_delivery")
        self.assertEqual(delivery["authorization"], "READY")
        self.assertEqual(delivery["items"][0]["source_block_id"], "turn-startup:voice-startup")
        self.assertEqual(delivery["items"][0]["speech_rate"], 1.2)
        # 归属参数是首参：确保建会话时带上了当前用户，而不是建成无主会话。
        ensure.assert_called_once_with("test-user", None)


if __name__ == "__main__":
    unittest.main()
