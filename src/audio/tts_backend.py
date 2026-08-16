"""模型无关的TTS后端合同。"""

from typing import Iterator, Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class TTSBackend(Protocol):
    """所有语音合成后端必须提供的最小能力。"""

    @property
    def sample_rate(self) -> int: ...

    def synthesize(self, text: str) -> Iterator[np.ndarray]:
        """把文本合成为按块产出的int16单声道音频。"""
