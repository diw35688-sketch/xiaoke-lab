import json
import struct
import sys
import tempfile
import unittest
import wave
from contextlib import closing
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

WEB = Path(__file__).resolve().parent.parent / "web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))
# tests 目录也要在路径上：discover 与 -m unittest tests.x 两种跑法的导入方式不同。
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from fastapi.testclient import TestClient  # noqa: E402
from api import turn as turn_api  # noqa: E402
from app import app  # noqa: E402
from asr_application_service import ASRApplicationService  # noqa: E402
import auth as auth_core  # noqa: E402
from database import db  # noqa: E402
import auth_helpers  # noqa: E402
from src.asr.schemas import ASRResult  # noqa: E402
from src.core.conversation_turn import (  # noqa: E402
    BlockType, ConversationBlock, ConversationTurn,
)
from turn_processors import PreparedTurn  # noqa: E402


def _wav():
    data = BytesIO()
    with wave.open(data, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(struct.pack("<160h", *([0] * 160)))
    return data.getvalue()


class _Backend:
    def recognize(self, path, *, language="zh"):
        return ASRResult(
            asr_transcript="温度八十摄氏度",
            asr_model_raw_text="温度八十摄氏度",
            audio_path=str(path), audio_duration_seconds=.01,
            recognition_seconds=.01, model="fake", language=language,
            is_final=True,
        )


class _Processor:
    def prepare(self, turn, timing):
        user = ConversationBlock(
            f"{turn.turn_id}:user", BlockType.USER_TEXT, {"text": turn.raw_text}
        )
        assistant = ConversationBlock(
            f"{turn.turn_id}:assistant", BlockType.ASSISTANT_TEXT, {"text": "收到"}
        )
        return PreparedTurn(
            ConversationTurn(
                turn.conversation_id, turn.request_id, turn.turn_id,
                turn.interaction_mode, turn.experiment_context,
                turn.mode_version, turn.input_source, (user, assistant),
            ),
            {"kind": turn.interaction_mode.value},
            messages=(
                {"role": "user", "content": turn.raw_text, "block_id": user.block_id},
                {"role": "assistant", "content": "收到", "block_id": assistant.block_id},
            ) if turn.interaction_mode.value == "chat" else (),
        )


def _events(response):
    return [json.loads(line[6:]) for line in response.text.splitlines()
            if line.startswith("data: ")]


class TurnAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = db.DATABASE_PATH
        db.DATABASE_PATH = Path(self.temp.name) / "api.db"
        db.initialize_database()
        self.old_experiment = turn_api.turn_application_service._experiment_processor
        processor = _Processor()
        turn_api.turn_application_service._experiment_processor = processor
        self.client = TestClient(app)
        # 全局登录闸门：测试也要真的走一遍注册/登录，不给自己开后门。
        self._iter_patch = patch.object(auth_core, "DEFAULT_ITERATIONS", 1000)
        self._iter_patch.start()
        auth_helpers.login(self.client)

    def tearDown(self):
        self._iter_patch.stop()
        turn_api.turn_application_service._experiment_processor = self.old_experiment
        db.DATABASE_PATH = self.old_db
        self.temp.cleanup()

    def test_text_returns_fixed_sse_order_and_replays(self):
        body = {
            "conversation_id": None, "request_id": "api-text-1",
            "turn_id": "turn-text-1", "lab_session_id": None,
            "interaction_mode": "chat", "experiment_context": "none",
            "mode_version": 1, "text": "你好",
        }
        first = _events(self.client.post("/turn/text", json=body))
        self.assertEqual(first[0]["type"], "turn_accepted")
        self.assertEqual(first[-2]["type"], "turn_result")
        self.assertEqual(first[-1]["type"], "done")
        body["conversation_id"] = first[0]["conversation_id"]
        replay = _events(self.client.post("/turn/text", json=body))
        self.assertTrue(replay[0]["replayed"])
        self.assertTrue(replay[-2]["replayed"])
        self.assertFalse(any(e["type"] == "voice_delivery" for e in replay))

    def test_audio_is_registered_then_saves_complete_asr_evidence(self):
        metadata = {
            "conversation_id": "audio-conversation", "request_id": "api-audio-1",
            "turn_id": "turn-audio-1", "lab_session_id": None,
            "interaction_mode": "chat", "experiment_context": "none",
            "mode_version": 1, "input_source": "single_recording",
        }
        fake_asr = ASRApplicationService(
            audio_root=Path(self.temp.name) / "audio",
            backend_factory=_Backend,
        )
        with patch("api.turn.get_asr_application_service", return_value=fake_asr):
            response = self.client.post(
                "/turn/audio",
                files={"audio": ("sample.wav", _wav(), "audio/wav")},
                data={"metadata": json.dumps(metadata)},
            )
        events = _events(response)
        phases = [e.get("phase") for e in events if e["type"] == "turn_status"]
        self.assertIn("audio_saved", phases)
        self.assertIn("asr", phases)
        with closing(db.get_connection()) as connection:
            row = connection.execute(
                "SELECT payload_json,audio_rel_path,audio_sha256 FROM asr_evidence"
            ).fetchone()
        payload = json.loads(row["payload_json"])
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["asr_transcript"], "温度八十摄氏度")
        self.assertTrue(row["audio_sha256"])

    def test_committed_turn_always_finishes_stream_when_voice_authorization_fails(self):
        body = {
            "conversation_id": "voice-failure-conversation",
            "request_id": "api-voice-failure-1",
            "turn_id": "turn-voice-failure-1",
            "lab_session_id": None,
            "interaction_mode": "chat",
            "experiment_context": "none",
            "mode_version": 1,
            "text": "你好",
        }
        original = turn_api.turn_application_service._experiment_processor

        class _VoiceProcessor(_Processor):
            def prepare(self, turn, timing):
                prepared = super().prepare(turn, timing)
                from src.core.presentation_delivery import VoiceDeliveryItem
                from src.core.presentation_intent import MessageKind, MessagePriority
                return PreparedTurn(
                    prepared.turn,
                    prepared.business,
                    messages=prepared.messages,
                    voice_items=(VoiceDeliveryItem(
                        "voice-failure", MessageKind.ASSISTANT_REPLY,
                        MessagePriority.REVIEW, "收到",
                        prepared.turn.blocks[1].block_id,
                    ),),
                )

        turn_api.turn_application_service._experiment_processor = _VoiceProcessor()
        try:
            with patch.object(
                turn_api.web_playback_service,
                "authorize",
                side_effect=ValueError("模拟语音授权失败"),
            ):
                events = _events(self.client.post("/turn/text", json=body))
        finally:
            turn_api.turn_application_service._experiment_processor = original

        self.assertEqual(events[-2]["type"], "turn_result")
        self.assertEqual(events[-1]["type"], "done")


if __name__ == "__main__":
    unittest.main()
