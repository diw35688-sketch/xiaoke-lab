# -*- coding: utf-8 -*-
"""One production adapter for Volcengine v1 WebSocket streaming TTS.

The adapter keeps a healthy WebSocket for normal sequential requests.  If a
consumer cancels mid-stream, the connection is closed so stale audio from the
cancelled request can never leak into the next request.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import struct
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator

import websockets


VOLCANO_TTS_WS_URL = "wss://openspeech.bytedance.com/api/v1/tts/ws_binary"
PCM_SAMPLE_RATE = 24_000
PCM_CHANNELS = 1
PCM_SAMPLE_WIDTH = 2


class VolcanoStreamingTTSError(RuntimeError):
    """A configuration, transport, or upstream protocol failure."""


@dataclass(frozen=True)
class VolcanoStreamConfig:
    appid: str
    access_token: str
    cluster: str
    voice: str
    speed: float

    @classmethod
    def from_settings(cls, settings: Any) -> "VolcanoStreamConfig":
        raw_key = settings.tts_api_key or ""
        if ":" not in raw_key:
            raise VolcanoStreamingTTSError(
                "火山引擎密钥格式应为 appid:access_token（中间用冒号）"
            )
        appid, access_token = (part.strip() for part in raw_key.split(":", 1))
        if not appid or not access_token:
            raise VolcanoStreamingTTSError("火山引擎 appid 或 access_token 为空")
        return cls(
            appid=appid,
            access_token=access_token,
            cluster=(settings.tts_model or "volcano_tts").strip() or "volcano_tts",
            voice=(settings.tts_voice or "BV001_streaming").strip(),
            speed=float(settings.tts_speed or 1.0),
        )


@dataclass(frozen=True)
class VolcanoFrame:
    audio: bytes = b""
    finished: bool = False


def build_request_frame(text: str, config: VolcanoStreamConfig) -> bytes:
    payload = {
        "app": {
            "appid": config.appid,
            "token": config.access_token,
            "cluster": config.cluster,
        },
        "user": {"uid": "web_lab_assistant"},
        "audio": {
            "voice_type": config.voice,
            "encoding": "pcm",
            "rate": PCM_SAMPLE_RATE,
            "speed_ratio": config.speed,
            "volume_ratio": 1.0,
            "pitch_ratio": 1.0,
        },
        "request": {
            "reqid": uuid.uuid4().hex,
            "text": text,
            "text_type": "plain",
            "operation": "submit",
            "with_frontend": 1,
            "frontend_type": "unitTson",
        },
    }
    body = gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    # Protocol v1, one 4-byte header; full-client-request; JSON; gzip.
    return bytes((0x11, 0x10, 0x11, 0x00)) + struct.pack(">I", len(body)) + body


def parse_response_frame(message: bytes) -> VolcanoFrame:
    if not isinstance(message, bytes) or len(message) < 4:
        raise VolcanoStreamingTTSError("火山返回了不完整的 WebSocket 帧")
    header_size = (message[0] & 0x0F) * 4
    if header_size < 4 or len(message) < header_size:
        raise VolcanoStreamingTTSError("火山 WebSocket 帧头长度无效")
    message_type = message[1] >> 4
    flags = message[1] & 0x0F
    compression = message[2] & 0x0F
    payload = message[header_size:]

    if message_type == 0x0B:  # audio-only response
        if flags == 0:
            return VolcanoFrame()
        if len(payload) < 8:
            raise VolcanoStreamingTTSError("火山音频帧缺少序号或长度")
        sequence = struct.unpack(">i", payload[:4])[0]
        payload_size = struct.unpack(">I", payload[4:8])[0]
        audio = payload[8:8 + payload_size]
        if len(audio) != payload_size:
            raise VolcanoStreamingTTSError("火山音频帧声明长度与实际长度不一致")
        return VolcanoFrame(audio=audio, finished=sequence < 0)

    if message_type == 0x0F:  # upstream error
        if len(payload) < 8:
            raise VolcanoStreamingTTSError("火山返回了无法解析的错误帧")
        code = struct.unpack(">I", payload[:4])[0]
        message_size = struct.unpack(">I", payload[4:8])[0]
        detail = payload[8:8 + message_size]
        if compression == 1:
            try:
                detail = gzip.decompress(detail)
            except gzip.BadGzipFile:
                pass
        raise VolcanoStreamingTTSError(
            f"火山 WebSocket 错误 code={code}: {detail.decode('utf-8', 'replace')}"
        )

    # Metadata/full-response frames contain no playable PCM.
    return VolcanoFrame()


class VolcanoStreamingTTSClient:
    def __init__(self, *, url: str = VOLCANO_TTS_WS_URL) -> None:
        self._url = url
        self._socket: Any | None = None
        self._connection_key: tuple[str, str] | None = None
        self._lock = asyncio.Lock()

    async def _close_unlocked(self) -> None:
        socket, self._socket = self._socket, None
        self._connection_key = None
        if socket is not None:
            try:
                await socket.close()
            except Exception:
                pass

    async def close(self) -> None:
        async with self._lock:
            await self._close_unlocked()

    async def warmup(self, config: VolcanoStreamConfig) -> None:
        """Open the authenticated socket before the first user-facing utterance."""
        async with self._lock:
            await self._connect_unlocked(config)

    async def _connect_unlocked(self, config: VolcanoStreamConfig) -> Any:
        connection_key = (config.appid, config.access_token)
        if self._socket is not None and self._connection_key == connection_key:
            return self._socket
        await self._close_unlocked()
        try:
            self._socket = await websockets.connect(
                self._url,
                additional_headers={
                    "Authorization": f"Bearer;{config.access_token}",
                },
                open_timeout=10,
                close_timeout=3,
                max_size=8 * 1024 * 1024,
                ping_interval=20,
                ping_timeout=10,
            )
        except Exception as error:
            raise VolcanoStreamingTTSError(
                f"无法连接火山流式 TTS：{type(error).__name__}: {error}"
            ) from error
        self._connection_key = connection_key
        return self._socket

    async def stream(
        self, text: str, config: VolcanoStreamConfig
    ) -> AsyncIterator[bytes]:
        if not isinstance(text, str) or not text.strip():
            raise VolcanoStreamingTTSError("流式 TTS 文本不能为空")

        completed = False
        async with self._lock:
            socket = await self._connect_unlocked(config)
            try:
                request_frame = build_request_frame(text.strip(), config)
                try:
                    await socket.send(request_frame)
                except Exception:
                    # An idle connection may have been closed upstream. Reconnect
                    # once before any audio has entered the browser-visible stream.
                    await self._close_unlocked()
                    socket = await self._connect_unlocked(config)
                    await socket.send(request_frame)
                async with asyncio.timeout(30):
                    while True:
                        message = await socket.recv()
                        frame = parse_response_frame(message)
                        if frame.audio:
                            yield frame.audio
                        if frame.finished:
                            completed = True
                            break
            except asyncio.CancelledError:
                raise
            except VolcanoStreamingTTSError:
                raise
            except Exception as error:
                raise VolcanoStreamingTTSError(
                    f"火山流式合成中断：{type(error).__name__}: {error}"
                ) from error
            finally:
                # A half-consumed response would contaminate the next request.
                if not completed:
                    await self._close_unlocked()


volcano_streaming_tts = VolcanoStreamingTTSClient()
