import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from api.tts import router  # noqa: E402


def settings(provider="volcano"):
    return SimpleNamespace(
        tts_provider=provider,
        tts_api_key="app:token",
        tts_model="volcano_tts",
        tts_voice="BV405_streaming",
        tts_speed=1.2,
    )


class WebTTSStreamTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def test_stream_endpoint_forwards_pcm_chunks_and_contract_headers(self):
        async def fake_stream(text, config):
            self.assertEqual(text, "流式测试")
            self.assertEqual(config.voice, "BV405_streaming")
            yield b"\x00\x00"
            yield b"\x01\x00"

        with (
            patch("api.tts.settings_store.current", return_value=settings()),
            patch("api.tts.volcano_streaming_tts.stream", side_effect=fake_stream),
        ):
            response = self.client.post("/tts/stream", json={"text": "流式测试"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"\x00\x00\x01\x00")
        self.assertEqual(response.headers["x-audio-format"], "pcm_s16le")
        self.assertEqual(response.headers["x-audio-sample-rate"], "24000")
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_stream_endpoint_rejects_a_second_provider_route(self):
        with patch("api.tts.settings_store.current", return_value=settings("browser")):
            response = self.client.post("/tts/stream", json={"text": "不能走兜底"})

        self.assertEqual(response.status_code, 409)
        self.assertIn("只支持", response.json()["detail"])

    def test_warmup_opens_the_same_production_client(self):
        async def fake_warmup(config):
            self.assertEqual(config.voice, "BV405_streaming")

        with (
            patch("api.tts.settings_store.current", return_value=settings()),
            patch("api.tts.volcano_streaming_tts.warmup", side_effect=fake_warmup) as warmup,
        ):
            response = self.client.post("/tts/warmup")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["transport"], "websocket")
        self.assertEqual(warmup.await_count, 1)


if __name__ == "__main__":
    unittest.main()
