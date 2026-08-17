import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.audio.vad_segmenter import VadSegmenter, VoiceSegment

SAMPLE_RATE = 16_000
PRE_ROLL_SAMPLES = 8_000  # 0.5s @ 16kHz
CHUNK_SAMPLES = 1_600  # 0.1s @ 16kHz


class FakeSegment:
    def __init__(self, *, samples, start):
        self.samples = np.array(samples, dtype=np.float32)
        self.start = start


class FakeVad:
    """模拟 sherpa_onnx 流式 VAD：接受音频、按队列吐段。"""

    def __init__(self, segments):
        self._segments = list(segments)
        self.accepted = []
        self.reset_count = 0
        self.pop_count = 0

    def reset(self):
        self.reset_count += 1

    def accept_waveform(self, samples):
        self.accepted.append(np.array(samples, dtype=np.float32))

    def empty(self):
        return not self._segments

    @property
    def front(self):
        return self._segments[0]

    def pop(self):
        self.pop_count += 1
        self._segments.pop(0)


def make_segmenter(**kwargs):
    kwargs.setdefault("vad", FakeVad([]))
    return VadSegmenter(
        sample_rate=SAMPLE_RATE,
        pre_roll_seconds=0.5,
        chunk_seconds=0.1,
        **kwargs,
    )


class VadSegmenterBasicTests(unittest.TestCase):
    def test_single_segment_includes_pre_roll(self):
        audio = np.zeros(SAMPLE_RATE, dtype=np.float32)
        vad = FakeVad([FakeSegment(samples=[0.9, 0.8, 0.7], start=8_000)])
        segments = make_segmenter(vad=vad).segment_audio(audio)

        self.assertEqual(len(segments), 1)
        segment = segments[0]
        self.assertEqual(segment.start_sample, 0)
        self.assertEqual(segment.end_sample, 8_003)
        np.testing.assert_array_equal(
            segment.samples,
            np.concatenate(
                (
                    np.zeros(8_000, dtype=np.float32),
                    np.array([0.9, 0.8, 0.7], dtype=np.float32),
                )
            ),
        )
        self.assertEqual(segment.duration_seconds, 8_003 / SAMPLE_RATE)

    def test_multiple_segments_each_with_own_pre_roll(self):
        audio = np.zeros(32_000, dtype=np.float32)
        vad = FakeVad(
            [
                FakeSegment(samples=[1.0, 1.0, 1.0], start=8_000),
                FakeSegment(samples=[2.0, 2.0, 2.0], start=24_000),
            ]
        )
        segments = make_segmenter(vad=vad).segment_audio(audio)

        self.assertEqual(len(segments), 2)
        first, second = segments
        # 第一段：预滚从输入起点开始（0 ~ 8000），接语音 3 采样。
        self.assertEqual(first.start_sample, 0)
        self.assertEqual(first.end_sample, 8_003)
        np.testing.assert_array_equal(
            first.samples,
            np.concatenate(
                (
                    np.zeros(8_000, dtype=np.float32),
                    np.ones(3, dtype=np.float32),
                )
            ),
        )
        # 第二段：预滚是最近 0.5s（16000 ~ 24000），接语音 3 采样。
        self.assertEqual(second.start_sample, 16_000)
        self.assertEqual(second.end_sample, 24_003)
        self.assertEqual(second.start_seconds, 1.0)
        self.assertEqual(second.end_seconds, 24_003 / SAMPLE_RATE)
        np.testing.assert_array_equal(
            second.samples,
            np.concatenate(
                (
                    np.zeros(8_000, dtype=np.float32),
                    np.full(3, 2.0, dtype=np.float32),
                )
            ),
        )
        self.assertEqual(vad.pop_count, 2)

    def test_speech_at_input_start_has_empty_pre_roll(self):
        audio = np.zeros(8_000, dtype=np.float32)
        vad = FakeVad([FakeSegment(samples=[5.0, 6.0], start=0)])
        segment = make_segmenter(vad=vad).segment_audio(audio)[0]

        self.assertEqual(segment.start_sample, 0)
        np.testing.assert_array_equal(
            segment.samples,
            np.array([5.0, 6.0], dtype=np.float32),
        )

    def test_pre_roll_truncated_when_segment_near_input_start(self):
        audio = np.zeros(16_000, dtype=np.float32)
        vad = FakeVad([FakeSegment(samples=[1.0], start=4_000)])
        segment = make_segmenter(vad=vad).segment_audio(audio)[0]

        # 段起点距输入起点只有 4000 采样，预滚只能取到输入开头。
        self.assertEqual(segment.start_sample, 0)
        self.assertEqual(segment.samples.size, 4_001)

    def test_segment_at_input_end_keeps_pre_roll(self):
        audio = np.zeros(16_000, dtype=np.float32)
        vad = FakeVad([FakeSegment(samples=[7.0, 8.0], start=16_000)])
        segment = make_segmenter(vad=vad).segment_audio(audio)[0]

        self.assertEqual(segment.start_sample, 8_000)
        self.assertEqual(segment.end_sample, 16_002)
        np.testing.assert_array_equal(
            segment.samples,
            np.concatenate(
                (
                    np.zeros(8_000, dtype=np.float32),
                    np.array([7.0, 8.0], dtype=np.float32),
                )
            ),
        )

    def test_silence_produces_no_segments(self):
        audio = np.zeros(SAMPLE_RATE, dtype=np.float32)
        segments = make_segmenter(vad=FakeVad([])).segment_audio(audio)

        self.assertEqual(segments, [])

    def test_feeds_audio_in_chunks_and_resets_twice(self):
        audio = np.zeros(SAMPLE_RATE, dtype=np.float32)
        vad = FakeVad([])
        make_segmenter(vad=vad).segment_audio(audio)

        self.assertEqual(len(vad.accepted), SAMPLE_RATE // CHUNK_SAMPLES)
        self.assertTrue(
            all(chunk.size == CHUNK_SAMPLES for chunk in vad.accepted)
        )
        np.testing.assert_array_equal(
            np.concatenate(vad.accepted),
            audio,
        )
        self.assertEqual(vad.reset_count, 2)


class VadSegmenterInputValidationTests(unittest.TestCase):
    def test_empty_input_rejected(self):
        with self.assertRaisesRegex(ValueError, "samples 不能为空"):
            make_segmenter().segment_audio(np.array([], dtype=np.float32))

    def test_multi_channel_input_rejected(self):
        with self.assertRaisesRegex(ValueError, "一维单声道"):
            make_segmenter().segment_audio(
                np.zeros((100, 2), dtype=np.float32)
            )

    def test_non_numeric_input_rejected(self):
        with self.assertRaisesRegex(TypeError, "数值数组"):
            make_segmenter().segment_audio(
                np.array(["a", "b"], dtype=object)
            )

    def test_non_finite_input_rejected(self):
        with self.assertRaisesRegex(ValueError, "有限数值"):
            make_segmenter().segment_audio(
                np.array([0.0, np.nan], dtype=np.float32)
            )

    def test_int_input_is_converted_to_float32(self):
        audio = np.zeros(4_000, dtype=np.int16)
        segments = make_segmenter(vad=FakeVad([])).segment_audio(audio)

        self.assertEqual(segments, [])


class VadSegmenterConfigValidationTests(unittest.TestCase):
    def test_zero_pre_roll_rejected(self):
        with self.assertRaisesRegex(ValueError, "pre_roll_seconds"):
            VadSegmenter(
                pre_roll_seconds=0,
                vad=FakeVad([]),
            )

    def test_zero_chunk_rejected(self):
        with self.assertRaisesRegex(ValueError, "chunk_seconds"):
            VadSegmenter(
                chunk_seconds=0,
                vad=FakeVad([]),
            )

    def test_missing_model_file_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                VadSegmenter(
                    model_path=Path(directory) / "missing.onnx",
                    vad=None,
                )


class VoiceSegmentContractTests(unittest.TestCase):
    def test_negative_start_rejected(self):
        with self.assertRaisesRegex(ValueError, "start_sample"):
            VoiceSegment(
                start_sample=-1,
                end_sample=1,
                samples=np.array([1.0], dtype=np.float32),
                sample_rate=SAMPLE_RATE,
            )

    def test_end_must_match_start_plus_length(self):
        with self.assertRaisesRegex(ValueError, "end_sample"):
            VoiceSegment(
                start_sample=0,
                end_sample=5,
                samples=np.array([1.0], dtype=np.float32),
                sample_rate=SAMPLE_RATE,
            )

    def test_non_float_samples_rejected(self):
        with self.assertRaisesRegex(TypeError, "float32"):
            VoiceSegment(
                start_sample=0,
                end_sample=1,
                samples=np.array([1.0]),
                sample_rate=SAMPLE_RATE,
            )

    def test_zero_sample_rate_rejected(self):
        with self.assertRaisesRegex(ValueError, "sample_rate"):
            VoiceSegment(
                start_sample=0,
                end_sample=1,
                samples=np.array([1.0], dtype=np.float32),
                sample_rate=0,
            )


if __name__ == "__main__":
    unittest.main()
