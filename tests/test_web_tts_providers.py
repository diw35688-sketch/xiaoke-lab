# -*- coding: utf-8 -*-
"""web/tts_providers.py 火山引擎豆包语音供应商的单测。

不依赖真实网络：用 unittest.mock 替换 httpx.post。
覆盖：鉴权头与请求体构造、音频 base64 解析、密钥格式错误、
火山业务错误码、供应商注册信息。
"""

import base64
import json
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

WEB_DIR = __import__("pathlib").Path(__file__).resolve().parent.parent / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

import tts_providers  # noqa: E402


def fake_settings(**overrides):
    base = dict(
        tts_provider="volcano",
        tts_api_key="appid123:tok456",
        tts_base_url="",
        tts_model="volcano_tts",
        tts_voice="BV001_streaming",
        tts_speed=1.0,
        tts_url="http://127.0.0.1:8001/tts",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def fake_response(payload: dict, status: int = 200):
    response = mock.MagicMock()
    response.status_code = status
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


class VolcanoTtsTests(unittest.TestCase):
    def test_volcano_registered_in_providers(self):
        meta = tts_providers.provider_meta("volcano")
        self.assertEqual(meta["id"], "volcano")
        self.assertTrue(meta["needs_key"])
        self.assertTrue(meta["server_side"])

    def test_request_builds_auth_header_and_payload(self):
        audio = b"\x00\x01fake-mp3-bytes"
        payload = {"code": 3000, "data": base64.b64encode(audio).decode("ascii")}
        with mock.patch("httpx.post", return_value=fake_response(payload)) as post:
            audio_bytes, mime = tts_providers.synthesize(
                "语音合成测试", fake_settings()
            )

        self.assertEqual(audio_bytes, audio)
        self.assertEqual(mime, "audio/mpeg")
        call = post.call_args
        self.assertEqual(call.args[0], "https://openspeech.bytedance.com/api/v1/tts")
        headers = call.kwargs["headers"]
        # 火山新接口鉴权头为两段：Bearer;token（appid 放请求体），三段会报 invalid amount of parts
        self.assertEqual(headers["Authorization"], "Bearer;tok456")
        body = call.kwargs["json"]
        self.assertEqual(body["app"]["appid"], "appid123")
        self.assertEqual(body["app"]["token"], "tok456")
        self.assertEqual(body["app"]["cluster"], "volcano_tts")
        self.assertEqual(body["audio"]["voice_type"], "BV001_streaming")
        self.assertEqual(body["audio"]["encoding"], "mp3")
        self.assertEqual(body["request"]["text"], "语音合成测试")
        self.assertEqual(body["request"]["text_type"], "plain")

    def test_cluster_comes_from_tts_model(self):
        audio = b"\x00\x01fake-mp3"
        payload = {"code": 3000, "data": base64.b64encode(audio).decode("ascii")}
        with mock.patch("httpx.post", return_value=fake_response(payload)) as post:
            tts_providers.synthesize(
                "测试", fake_settings(tts_model="volcano_icl")
            )
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["app"]["cluster"], "volcano_icl")

    def test_key_without_colon_raises(self):
        with self.assertRaisesRegex(RuntimeError, "appid:access_token"):
            tts_providers.synthesize("测试", fake_settings(tts_api_key="no-colon-here"))

    def test_business_error_code_raises(self):
        payload = {"code": 4001, "message": "token 无效"}
        with mock.patch("httpx.post", return_value=fake_response(payload)):
            with self.assertRaisesRegex(RuntimeError, "4001"):
                tts_providers.synthesize("测试", fake_settings())

    def test_missing_audio_data_raises(self):
        payload = {"code": 3000, "data": ""}
        with mock.patch("httpx.post", return_value=fake_response(payload)):
            with self.assertRaisesRegex(RuntimeError, "音频"):
                tts_providers.synthesize("测试", fake_settings())

    def test_http_error_passthroughs_volcano_body(self):
        import httpx

        error_response = mock.MagicMock()
        error_response.status_code = 401
        error_response.text = '{"code":3001,"message":"load grant: not found"}'
        error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401 Unauthorized", request=mock.MagicMock(), response=error_response
        )
        with mock.patch("httpx.post", return_value=error_response):
            with self.assertRaisesRegex(RuntimeError, "not found"):
                tts_providers.synthesize("测试", fake_settings())


if __name__ == "__main__":
    unittest.main()
