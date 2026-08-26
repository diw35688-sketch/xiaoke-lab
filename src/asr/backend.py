"""模型无关的ASR后端合同。"""

from pathlib import Path
from typing import Protocol, runtime_checkable

from src.asr.schemas import ASRResult


@runtime_checkable
class ASRBackend(Protocol):
    """所有语音识别后端必须提供的最小能力。"""

    def recognize(
        self,
        audio_path: Path,
        *,
        language: str = "zh",
    ) -> ASRResult:
        """识别一个音频文件并返回项目统一结果；默认中文，评测可显式传 auto。"""

