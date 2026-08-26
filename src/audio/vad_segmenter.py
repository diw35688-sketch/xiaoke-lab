"""纯 VAD 分段：把一整段音频按 Silero VAD 切成若干语音段（含句首预滚）。

与 ``VadAudioRecorder``（终端实时录音，检测到第一段即返回）不同，
本模块面向"完整音频已经在手"的场景（例如 web 端上传的整段 WAV），
一次返回输入里检测到的全部语音段。

设计目标：
- 不依赖麦克风（不 import sounddevice），因此 web 后端可以直接复用；
- 与终端共享同一份 Silero VAD 配置（``build_silero_vad_config``）和
  同一套预滚组装器（``TimelineSpeechAssembler``），保证两端分段行为一致；
- 支持注入 Fake VAD，便于单元测试（与 ``VadAudioRecorder`` 相同模式）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sherpa_onnx

from src.audio.pre_roll_timeline import PreRollSnapshot
from src.audio.timeline_speech_assembler import TimelineSpeechAssembler
from src.config import SAMPLE_RATE, VAD_MODEL_PATH


logger = logging.getLogger(__name__)


def build_silero_vad_config(
    *,
    model_path: Path | str,
    sample_rate: int,
) -> sherpa_onnx.VadModelConfig:
    """构建终端与 web 共享的 Silero VAD 配置（参数单一来源）。

    参数取值与终端 ``VadAudioRecorder`` 原实现一致：
    阈值 0.25、静音 2.0s、最短语音 0.3s、最长语音 30s、窗口 512。
    两端共用本函数后，调参只改一处。
    """

    config = sherpa_onnx.VadModelConfig()

    config.silero_vad.model = str(model_path)

    config.silero_vad.threshold = 0.25

    config.silero_vad.min_silence_duration = (
        2.0
    )

    config.silero_vad.min_speech_duration = (
        0.3
    )

    config.silero_vad.max_speech_duration = (
        30.0
    )

    config.silero_vad.window_size = 512

    config.sample_rate = sample_rate
    config.num_threads = 1

    return config


@dataclass(frozen=True)
class VoiceSegment:
    """一个检测到的语音段（含句首预滚），采样位置相对输入起点。

    ``samples`` 是"预滚 + 语音"拼接后的完整段音频
    （float32 单声道，可直接送 ASR）。
    """

    start_sample: int
    end_sample: int
    samples: np.ndarray
    sample_rate: int

    def __post_init__(self) -> None:
        if self.samples.ndim != 1:
            raise ValueError("samples 必须是一维单声道数组。")
        if self.samples.dtype != np.float32:
            raise TypeError("samples 必须是 float32 数组。")
        if self.start_sample < 0:
            raise ValueError("start_sample 不能小于 0。")
        if self.end_sample != self.start_sample + self.samples.size:
            raise ValueError("end_sample 必须等于 start_sample 加 samples 长度。")
        if self.sample_rate <= 0:
            raise ValueError("sample_rate 必须大于 0。")

    @property
    def start_seconds(self) -> float:
        return self.start_sample / self.sample_rate

    @property
    def end_seconds(self) -> float:
        return self.end_sample / self.sample_rate

    @property
    def duration_seconds(self) -> float:
        return self.samples.size / self.sample_rate


class VadSegmenter:
    """把完整音频切成多个语音段；只依赖 numpy + sherpa_onnx。"""

    def __init__(
        self,
        *,
        model_path: Path | str = VAD_MODEL_PATH,
        sample_rate: int = SAMPLE_RATE,
        pre_roll_seconds: float = 0.5,
        chunk_seconds: float = 0.1,
        vad=None,
    ) -> None:
        if pre_roll_seconds <= 0:
            raise ValueError("pre_roll_seconds 必须大于 0。")
        if chunk_seconds <= 0:
            raise ValueError("chunk_seconds 必须大于 0。")
        if sample_rate <= 0:
            raise ValueError("sample_rate 必须大于 0。")

        self._sample_rate = sample_rate
        self._pre_roll_samples = int(
            round(pre_roll_seconds * sample_rate)
        )
        self._chunk_samples = int(
            round(chunk_seconds * sample_rate)
        )
        self._assembler = TimelineSpeechAssembler()

        if vad is not None:
            self._vad = vad
            return

        model_path = Path(model_path)
        if not model_path.is_file():
            raise FileNotFoundError(
                f"找不到VAD模型：{model_path}"
            )

        config = build_silero_vad_config(
            model_path=model_path,
            sample_rate=sample_rate,
        )

        logger.info("正在加载VAD模型……")

        self._vad = sherpa_onnx.VoiceActivityDetector(
            config,
            buffer_size_in_seconds=30,
        )

        logger.info("VAD模型加载完成。")

    def segment_audio(
        self,
        samples: np.ndarray,
    ) -> list[VoiceSegment]:
        """把一段完整音频切成若干语音段；纯静音返回空列表。

        与终端相同按 0.1s 块喂入 VAD（配合其内部 30s 缓冲），
        全部喂完后一次性取出所有检测到的段。
        """

        full = self._validate_input(samples)

        self._vad.reset()
        try:
            for start in range(0, full.size, self._chunk_samples):
                self._vad.accept_waveform(
                    full[start : start + self._chunk_samples]
                )

            segments: list[VoiceSegment] = []
            while not self._vad.empty():
                vad_segment = self._vad.front
                segments.append(
                    self._assemble_one(full, vad_segment)
                )
                # sherpa 的 front 是队列底层数据视图；pop 后该对象可能立即
                # 失效。必须先复制/组装成项目自己的 VoiceSegment，再出队。
                self._vad.pop()
            return segments
        finally:
            self._vad.reset()

    def _assemble_one(
        self,
        full_input: np.ndarray,
        vad_segment,
    ) -> VoiceSegment:
        """为单个 VAD 段重建句首预滚并组装成完整段音频。

        预滚取"段起点之前最近 pre_roll_seconds 秒"的输入采样
        （段起点不足预滚长度时取到输入开头为止）。
        预滚区间与语音段在段起点相接（重叠为 0），
        走 ``TimelineSpeechAssembler`` 已验证的相接路径。
        """

        speech = np.asarray(vad_segment.samples, dtype=np.float32)
        if speech.ndim != 1:
            raise ValueError("VAD 段 samples 必须是一维单声道数组。")
        if speech.size == 0:
            raise ValueError("VAD 返回了空语音段。")

        start = int(vad_segment.start)
        if start < 0:
            raise ValueError("VAD 段起始采样位置不能小于 0。")

        pre_roll_end = min(start, full_input.size)
        pre_roll_start = max(
            0,
            pre_roll_end - self._pre_roll_samples,
        )

        pre_roll = PreRollSnapshot(
            samples=full_input[pre_roll_start:pre_roll_end],
            start_sample=pre_roll_start,
            end_sample=pre_roll_end,
        )

        audio = self._assembler.assemble(
            pre_roll=pre_roll,
            speech_segment=speech,
            speech_start_sample=pre_roll_end,
        )

        return VoiceSegment(
            start_sample=pre_roll_start,
            end_sample=pre_roll_end + speech.size,
            samples=audio,
            sample_rate=self._sample_rate,
        )

    @staticmethod
    def _validate_input(
        samples: np.ndarray,
    ) -> np.ndarray:
        array = np.asarray(samples)
        if array.ndim != 1:
            raise ValueError("samples 必须是一维单声道数组。")
        if not np.issubdtype(array.dtype, np.number):
            raise TypeError("samples 必须是数值数组。")
        if array.size == 0:
            raise ValueError("samples 不能为空。")
        if not np.all(np.isfinite(array)):
            raise ValueError("samples 必须全部是有限数值。")
        return np.array(array, dtype=np.float32, copy=True)
