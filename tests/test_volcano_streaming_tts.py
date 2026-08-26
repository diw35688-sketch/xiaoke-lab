import gzip
import json
import struct
import unittest
from unittest.mock import AsyncMock, patch

from web.volcano_streaming_tts import (
    VolcanoStreamConfig,
    VolcanoStreamingTTSClient,
    VolcanoStreamingTTSError,
    build_request_frame,
    parse_response_frame,
)


CONFIG = VolcanoStreamConfig(
    appid="app",
    access_token="token",
    cluster="volcano_tts",
    voice="BV405_streaming",
    speed=1.2,
)


def audio_frame(sequence, audio=b"pcm"):
    payload = struct.pack(">iI", sequence, len(audio)) + audio
    return bytes((0x11, 0xB1, 0x00, 0x00)) + payload


class RequestFrameTests(unittest.TestCase):
    def test_request_uses_submit_and_pcm_without_exposing_token_in_header(self):
        frame = build_request_frame("你好", CONFIG)
        self.assertEqual(frame[:4], bytes((0x11, 0x10, 0x11, 0x00)))
        size = struct.unpack(">I", frame[4:8])[0]
        payload = json.loads(gzip.decompress(frame[8:8 + size]))

        self.assertEqual(payload["request"]["operation"], "submit")
        self.assertEqual(payload["audio"]["encoding"], "pcm")
        self.assertEqual(payload["audio"]["rate"], 24_000)
        self.assertEqual(payload["audio"]["voice_type"], "BV405_streaming")


class ResponseFrameTests(unittest.TestCase):
    def test_audio_frame_exposes_bytes_and_final_sequence(self):
        first = parse_response_frame(audio_frame(1, b"first"))
        final = parse_response_frame(audio_frame(-2, b"last"))

        self.assertEqual(first.audio, b"first")
        self.assertFalse(first.finished)
        self.assertEqual(final.audio, b"last")
        self.assertTrue(final.finished)

    def test_malformed_audio_length_is_rejected(self):
        malformed = bytes((0x11, 0xB1, 0x00, 0x00)) + struct.pack(">iI", 1, 9) + b"x"
        with self.assertRaisesRegex(VolcanoStreamingTTSError, "长度"):
            parse_response_frame(malformed)


class FakeSocket:
    def __init__(self, responses):
        self.responses = list(responses)
        self.sent = []
        self.closed = False

    async def send(self, frame):
        self.sent.append(frame)

    async def recv(self):
        return self.responses.pop(0)

    async def close(self):
        self.closed = True


class StreamingClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_warmup_connection_is_reused_by_first_turn(self):
        socket = FakeSocket([audio_frame(-1, b"warm")])
        client = VolcanoStreamingTTSClient()
        connect = AsyncMock(return_value=socket)
        with patch("web.volcano_streaming_tts.websockets.connect", connect):
            await client.warmup(CONFIG)
            chunks = [chunk async for chunk in client.stream("第一轮", CONFIG)]

        self.assertEqual(chunks, [b"warm"])
        self.assertEqual(connect.await_count, 1)

    async def test_completed_request_keeps_connection_for_next_turn(self):
        socket = FakeSocket([
            audio_frame(1, b"a"), audio_frame(-2, b"b"),
            audio_frame(-1, b"c"),
        ])
        client = VolcanoStreamingTTSClient()
        connect = AsyncMock(return_value=socket)
        with patch("web.volcano_streaming_tts.websockets.connect", connect):
            first = [chunk async for chunk in client.stream("第一轮", CONFIG)]
            second = [chunk async for chunk in client.stream("第二轮", CONFIG)]

        self.assertEqual(first, [b"a", b"b"])
        self.assertEqual(second, [b"c"])
        self.assertEqual(connect.await_count, 1)
        self.assertFalse(socket.closed)

    async def test_early_consumer_exit_closes_connection(self):
        socket = FakeSocket([audio_frame(1, b"a"), audio_frame(-2, b"b")])
        client = VolcanoStreamingTTSClient()
        with patch(
            "web.volcano_streaming_tts.websockets.connect",
            AsyncMock(return_value=socket),
        ):
            stream = client.stream("会被打断", CONFIG)
            self.assertEqual(await anext(stream), b"a")
            await stream.aclose()

        self.assertTrue(socket.closed)


if __name__ == "__main__":
    unittest.main()
