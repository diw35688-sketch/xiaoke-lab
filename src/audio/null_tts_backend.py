"""不发声的TTS占位后端。"""

from dataclasses import dataclass
from typing import Iterator

import numpy as np


@dataclass(frozen=True)
class NullTTSBackend:
    """用于主流程联调的空TTS后端，不生成也不播放任何音频。"""

    _sample_rate: int = 16_000

    def __post_init__(self) -> None:
        if not isinstance(self._sample_rate, int) or isinstance(
            self._sample_rate,
            bool,
        ):
            raise TypeError("sample_rate必须是整数。")
        if self._sample_rate <= 0:
            raise ValueError("sample_rate必须大于0。")

    @property
    def sample_rate(self) -> int:
        """返回占位后端约定的采样率。"""

        return self._sample_rate

    def synthesize(self, text: str) -> Iterator[np.ndarray]:
        """接受文本但不产生音频，保持真实后端的生成器形状。"""

        if not isinstance(text, str):
            raise TypeError("text必须是字符串。")

        return
        yield np.empty(0, dtype=np.int16)
