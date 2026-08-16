"""根据集中配置创建程序级TTS后端。"""

from src.audio.null_tts_backend import NullTTSBackend
from src.audio.tts_backend import TTSBackend
from src.config import SAMPLE_RATE, TTS_BACKEND


SUPPORTED_TTS_BACKENDS = frozenset({
    "null",
})


def create_tts_backend(
    backend_name: str | None = None,
) -> TTSBackend:
    """创建指定后端；未知名称在连接真实引擎前明确失败。"""

    normalized_name = (
        TTS_BACKEND
        if backend_name is None
        else backend_name
    ).strip().lower()

    if normalized_name == "null":
        return NullTTSBackend(
            _sample_rate=SAMPLE_RATE,
        )

    raise ValueError(
        "TTS_BACKEND 不受支持："
        f"{normalized_name!r}；可选值为："
        f"{sorted(SUPPORTED_TTS_BACKENDS)}"
    )
