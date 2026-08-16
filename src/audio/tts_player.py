"""可按音频块检查取消的TTS播放纯逻辑。"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.audio.cancel_scope import CancelScope
from src.audio.tts_backend import TTSBackend


class TTSPlaybackStatus(str, Enum):
    """一次TTS播放的终态。"""

    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class TTSPlaybackResult:
    """一次TTS播放的不可变结果。"""

    text: str
    status: TTSPlaybackStatus
    chunks_played: int
    generation: int
    error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("text必须是字符串。")
        if not isinstance(self.status, TTSPlaybackStatus):
            raise TypeError("status必须是TTSPlaybackStatus。")
        if not isinstance(self.chunks_played, int) or isinstance(
            self.chunks_played,
            bool,
        ):
            raise TypeError("chunks_played必须是整数。")
        if self.chunks_played < 0:
            raise ValueError("chunks_played不能小于0。")
        if not isinstance(self.generation, int) or isinstance(
            self.generation,
            bool,
        ):
            raise TypeError("generation必须是整数。")
        if not 0 <= self.generation <= 0xFFFFFFFF:
            raise ValueError("generation必须位于32位无符号整数范围内。")
        if self.error is not None and not isinstance(
            self.error,
            str,
        ):
            raise TypeError("error必须是字符串或None。")


class _NullAudioSink:
    """默认空播放端，不触碰音频设备。"""

    def play(self, chunk: Any) -> None:
        """接收音频块但什么也不做。"""


class InterruptibleTTSPlayer:
    """通过依赖注入播放按块生成的TTS音频。"""

    def __init__(
        self,
        *,
        backend: TTSBackend,
        cancel_scope: CancelScope,
        audio_sink=None,
    ) -> None:
        self._backend = backend
        self._cancel_scope = cancel_scope
        self._audio_sink = (
            _NullAudioSink()
            if audio_sink is None
            else audio_sink
        )

    def speak(self, text: str) -> TTSPlaybackResult:
        """播放一段文本；外部服务失败时返回失败结果而不是抛异常。"""

        if not isinstance(text, str):
            raise TypeError("text必须是字符串。")

        generation = self._cancel_scope.generation
        chunks_played = 0

        try:
            for chunk in self._backend.synthesize(text):
                if self._cancel_scope.is_stale(generation):
                    return TTSPlaybackResult(
                        text=text,
                        status=TTSPlaybackStatus.CANCELLED,
                        chunks_played=chunks_played,
                        generation=generation,
                        error=None,
                    )

                self._play_chunk(chunk)
                chunks_played += 1
        except Exception as error:
            return TTSPlaybackResult(
                text=text,
                status=TTSPlaybackStatus.FAILED,
                chunks_played=chunks_played,
                generation=generation,
                error=str(error),
            )

        return TTSPlaybackResult(
            text=text,
            status=TTSPlaybackStatus.COMPLETED,
            chunks_played=chunks_played,
            generation=generation,
            error=None,
        )

    def _play_chunk(self, chunk) -> None:
        """把一个块交给注入的sink；Fake可使用play方法或可调用对象。"""

        if callable(self._audio_sink):
            self._audio_sink(chunk)
            return

        self._audio_sink.play(chunk)
