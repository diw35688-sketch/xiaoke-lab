"""Probe the current Volcengine v1 WebSocket TTS configuration.

This script reads the existing Web settings, requests one fixed sentence with
operation=submit, and reports time to WebSocket connection and first audio
chunk.  It never prints credentials and does not save the returned audio.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import struct
import sys
import time
import uuid
from pathlib import Path

import websockets


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
sys.path.insert(0, str(WEB_DIR))

import settings_store  # noqa: E402


WS_URL = "wss://openspeech.bytedance.com/api/v1/tts/ws_binary"
PROBE_TEXT = "语音流式合成测试。"


def _request_frame(payload: dict[str, object]) -> bytes:
    body = gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    # v1, 4-byte header; full client request; JSON; gzip.
    return bytes((0x11, 0x10, 0x11, 0x00)) + struct.pack(">I", len(body)) + body


def _parse_response(message: bytes) -> tuple[str, int, bool]:
    if len(message) < 4:
        raise RuntimeError("火山返回了不完整的 WebSocket 帧")
    header_size = (message[0] & 0x0F) * 4
    message_type = message[1] >> 4
    flags = message[1] & 0x0F
    compression = message[2] & 0x0F
    payload = message[header_size:]

    if message_type == 0x0B:  # audio-only server response
        if flags == 0:
            return "audio", 0, False
        if len(payload) < 8:
            raise RuntimeError("火山音频帧缺少序号或长度")
        sequence = struct.unpack(">i", payload[:4])[0]
        payload_size = struct.unpack(">I", payload[4:8])[0]
        audio = payload[8:8 + payload_size]
        return "audio", len(audio), sequence < 0

    if message_type == 0x0F:  # error response
        if len(payload) < 8:
            raise RuntimeError("火山返回了无法解析的错误帧")
        code = struct.unpack(">I", payload[:4])[0]
        message_size = struct.unpack(">I", payload[4:8])[0]
        detail = payload[8:8 + message_size]
        if compression == 1:
            detail = gzip.decompress(detail)
        raise RuntimeError(f"火山 WebSocket 错误 code={code}: {detail.decode('utf-8', 'replace')}")

    return "metadata", 0, False


async def probe() -> None:
    settings = settings_store.current()
    if settings.tts_provider != "volcano":
        raise RuntimeError(f"当前 TTS 不是 volcano，而是 {settings.tts_provider!r}")
    raw_key = settings.tts_api_key or ""
    if ":" not in raw_key:
        raise RuntimeError("当前火山凭据不是 appid:access_token 格式")
    appid, token = (part.strip() for part in raw_key.split(":", 1))
    if not appid or not token:
        raise RuntimeError("当前火山 appid 或 access_token 为空")

    payload = {
        "app": {
            "appid": appid,
            "token": token,
            "cluster": (settings.tts_model or "volcano_tts").strip(),
        },
        "user": {"uid": "web_lab_assistant_stream_probe"},
        "audio": {
            "voice_type": settings.tts_voice or "BV001_streaming",
            "encoding": "pcm",
            "rate": 24000,
            "speed_ratio": float(settings.tts_speed or 1.0),
            "volume_ratio": 1.0,
            "pitch_ratio": 1.0,
        },
        "request": {
            "reqid": uuid.uuid4().hex,
            "text": PROBE_TEXT,
            "text_type": "plain",
            "operation": "submit",
            "with_frontend": 1,
            "frontend_type": "unitTson",
        },
    }

    started = time.perf_counter()
    print(f"provider=volcano voice={payload['audio']['voice_type']} text_chars={len(PROBE_TEXT)}")
    async with websockets.connect(
        WS_URL,
        additional_headers={"Authorization": f"Bearer;{token}"},
        open_timeout=10,
        close_timeout=5,
        max_size=8 * 1024 * 1024,
    ) as socket:
        connected = time.perf_counter()
        print(f"websocket_connected_ms={round((connected - started) * 1000)}")
        await socket.send(_request_frame(payload))

        first_audio_at: float | None = None
        total_audio_bytes = 0
        async with asyncio.timeout(20):
            while True:
                message = await socket.recv()
                if not isinstance(message, bytes):
                    raise RuntimeError("火山返回了预期外的文本帧")
                kind, audio_bytes, finished = _parse_response(message)
                if kind != "audio":
                    continue
                total_audio_bytes += audio_bytes
                if audio_bytes and first_audio_at is None:
                    first_audio_at = time.perf_counter()
                    print(f"first_audio_ms={round((first_audio_at - started) * 1000)}")
                    print(f"first_audio_after_connect_ms={round((first_audio_at - connected) * 1000)}")
                if finished:
                    completed = time.perf_counter()
                    print(f"complete_ms={round((completed - started) * 1000)}")
                    print(f"audio_bytes={total_audio_bytes}")
                    break

        if first_audio_at is None:
            raise RuntimeError("连接完成，但 20 秒内没有收到有效音频分片")


if __name__ == "__main__":
    try:
        asyncio.run(probe())
    except Exception as error:
        print(f"probe_failed={type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
