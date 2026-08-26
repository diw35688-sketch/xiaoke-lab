import unittest
import wave
from pathlib import Path

import numpy as np

from src.audio.vad_segmenter import VadSegmenter
from src.config import VAD_MODEL_PATH


ROOT = Path(__file__).resolve().parent.parent
REFERENCE_WAV = ROOT / "web" / "voice" / "reference.wav"
TARGET_RATE = 16_000


def _load_reference_at_16k() -> np.ndarray:
    with wave.open(str(REFERENCE_WAV), "rb") as source:
        if source.getnchannels() != 1 or source.getsampwidth() != 2:
            raise AssertionError("reference.wav 必须是单声道 16-bit PCM。")
        source_rate = source.getframerate()
        samples = np.frombuffer(
            source.readframes(source.getnframes()),
            dtype="<i2",
        ).astype(np.float32) / 32768.0

    target_size = round(samples.size * TARGET_RATE / source_rate)
    source_positions = np.arange(samples.size, dtype=np.float64)
    target_positions = np.linspace(
        0,
        samples.size - 1,
        target_size,
        dtype=np.float64,
    )
    return np.interp(
        target_positions,
        source_positions,
        samples,
    ).astype(np.float32)


@unittest.skipUnless(VAD_MODEL_PATH.is_file(), "本地 Silero VAD 模型未安装")
class VadRealModelRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.segmenter = VadSegmenter()

    def test_tracked_speech_fixture_produces_nonempty_segment(self):
        speech = _load_reference_at_16k()
        # 流式模型需要明确尾静音才能结束当前段；该尾部属于测试输入合同。
        sample = np.concatenate(
            (speech, np.zeros(3 * TARGET_RATE, dtype=np.float32))
        )

        segments = self.segmenter.segment_audio(sample)

        self.assertGreaterEqual(len(segments), 1)
        self.assertTrue(all(segment.samples.size > 0 for segment in segments))
        self.assertTrue(all(segment.sample_rate == TARGET_RATE for segment in segments))

    def test_fixed_silence_produces_no_segment(self):
        silence = np.zeros(2 * TARGET_RATE, dtype=np.float32)

        self.assertEqual(self.segmenter.segment_audio(silence), [])

    def test_seeded_low_level_broadband_noise_produces_no_segment(self):
        generator = np.random.default_rng(20260824)
        noise = generator.normal(
            loc=0.0,
            scale=0.02,
            size=3 * TARGET_RATE,
        ).astype(np.float32)

        self.assertEqual(self.segmenter.segment_audio(noise), [])


if __name__ == "__main__":
    unittest.main()
