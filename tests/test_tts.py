import unittest
from dataclasses import FrozenInstanceError
from enum import Enum
from unittest.mock import patch

import numpy as np

from src.audio.cancel_scope import CancelScope
from src.audio.tts_backend import TTSBackend
from src.audio.tts_factory import create_tts_backend
from src.audio.tts_player import (
    InterruptibleTTSPlayer,
    TTSPlaybackResult,
    TTSPlaybackStatus,
)


class FakeBackend:
    def __init__(self, chunks=None, error=None, sample_rate=16_000):
        self.chunks = list(chunks or [])
        self.error = error
        self.sample_rate = sample_rate
        self.calls = []

    def synthesize(self, text):
        self.calls.append(text)
        if self.error is not None:
            raise self.error
        yield from self.chunks


class IncompleteBackend:
    def synthesize(self, text):
        yield np.array([1], dtype=np.int16)


class FakeSink:
    def __init__(self, cancel_scope=None, cancel_after=None):
        self.chunks = []
        self.cancel_scope = cancel_scope
        self.cancel_after = cancel_after

    def play(self, chunk):
        self.chunks.append(chunk)
        if (
            self.cancel_scope is not None
            and self.cancel_after == len(self.chunks)
        ):
            self.cancel_scope.cancel()


class TTSBackendContractTests(unittest.TestCase):
    def test_protocol_accepts_structural_fake(self):
        self.assertIsInstance(FakeBackend(), TTSBackend)

    def test_runtime_checkable_protocol_rejects_incomplete_fake(self):
        self.assertNotIsInstance(IncompleteBackend(), TTSBackend)


class CancelScopeTests(unittest.TestCase):
    def test_cancel_marks_captured_generation_stale(self):
        scope = CancelScope()
        generation = scope.generation

        scope.cancel()

        self.assertTrue(scope.is_stale(generation))
        self.assertEqual(scope.generation, 1)

    def test_new_response_advances_generation(self):
        scope = CancelScope()
        generation = scope.generation

        scope.new_response()

        self.assertTrue(scope.is_stale(generation))
        self.assertEqual(scope.generation, 1)

    def test_reset_returns_generation_to_zero(self):
        scope = CancelScope()
        scope.cancel()
        scope.new_response()

        scope.reset()

        self.assertEqual(scope.generation, 0)

    def test_generation_wraps_at_32_bits(self):
        scope = CancelScope()
        scope._generation = 0xFFFFFFFF

        scope.cancel()

        self.assertEqual(scope.generation, 0)


class InterruptibleTTSPlayerTests(unittest.TestCase):
    def test_normal_playback_completes_with_all_chunks(self):
        chunks = [
            np.array([1], dtype=np.int16),
            np.array([2], dtype=np.int16),
            np.array([3], dtype=np.int16),
        ]
        backend = FakeBackend(chunks)
        sink = FakeSink()
        player = InterruptibleTTSPlayer(
            backend=backend,
            cancel_scope=CancelScope(),
            audio_sink=sink,
        )

        result = player.speak("你好")

        self.assertEqual(result.status, TTSPlaybackStatus.COMPLETED)
        self.assertEqual(result.chunks_played, 3)
        self.assertEqual(result.generation, 0)
        self.assertIsNone(result.error)
        self.assertEqual(sink.chunks, chunks)

    def test_cancel_during_kth_chunk_stops_before_following_chunk(self):
        scope = CancelScope()
        chunks = [
            np.array([1], dtype=np.int16),
            np.array([2], dtype=np.int16),
            np.array([3], dtype=np.int16),
        ]
        sink = FakeSink(scope, cancel_after=2)
        player = InterruptibleTTSPlayer(
            backend=FakeBackend(chunks),
            cancel_scope=scope,
            audio_sink=sink,
        )

        result = player.speak("可打断")

        self.assertEqual(result.status, TTSPlaybackStatus.CANCELLED)
        self.assertEqual(result.chunks_played, 2)
        self.assertEqual(sink.chunks, chunks[:2])

    def test_cancelled_generation_does_not_residue_into_new_playback(self):
        scope = CancelScope()
        first_sink = FakeSink(scope, cancel_after=1)
        player = InterruptibleTTSPlayer(
            backend=FakeBackend([
                np.array([1], dtype=np.int16),
                np.array([2], dtype=np.int16),
            ]),
            cancel_scope=scope,
            audio_sink=first_sink,
        )

        first_result = player.speak("第一段")
        second_sink = FakeSink()
        second_player = InterruptibleTTSPlayer(
            backend=FakeBackend([
                np.array([3], dtype=np.int16),
                np.array([4], dtype=np.int16),
            ]),
            cancel_scope=scope,
            audio_sink=second_sink,
        )

        second_result = second_player.speak("第二段")

        self.assertEqual(first_result.status, TTSPlaybackStatus.CANCELLED)
        self.assertEqual(second_result.status, TTSPlaybackStatus.COMPLETED)
        self.assertEqual(second_result.chunks_played, 2)
        self.assertEqual(len(second_sink.chunks), 2)

    def test_backend_exception_becomes_failed_result(self):
        player = InterruptibleTTSPlayer(
            backend=FakeBackend(error=RuntimeError("合成失败")),
            cancel_scope=CancelScope(),
            audio_sink=FakeSink(),
        )

        result = player.speak("失败")

        self.assertEqual(result.status, TTSPlaybackStatus.FAILED)
        self.assertEqual(result.chunks_played, 0)
        self.assertEqual(result.error, "合成失败")

    def test_empty_text_is_passed_to_backend_and_completes(self):
        backend = FakeBackend()
        player = InterruptibleTTSPlayer(
            backend=backend,
            cancel_scope=CancelScope(),
        )

        result = player.speak("")

        self.assertEqual(result.status, TTSPlaybackStatus.COMPLETED)
        self.assertEqual(result.chunks_played, 0)
        self.assertEqual(backend.calls, [""])

    def test_zero_chunks_completes_without_touching_sink(self):
        sink = FakeSink()
        player = InterruptibleTTSPlayer(
            backend=FakeBackend([]),
            cancel_scope=CancelScope(),
            audio_sink=sink,
        )

        result = player.speak("没有音频")

        self.assertEqual(result.status, TTSPlaybackStatus.COMPLETED)
        self.assertEqual(result.chunks_played, 0)
        self.assertEqual(sink.chunks, [])

    def test_sink_exception_is_contained_as_failed_result(self):
        class FailingSink:
            def play(self, chunk):
                raise RuntimeError("播放失败")

        player = InterruptibleTTSPlayer(
            backend=FakeBackend([
                np.array([1], dtype=np.int16),
            ]),
            cancel_scope=CancelScope(),
            audio_sink=FailingSink(),
        )

        result = player.speak("播放失败")

        self.assertEqual(result.status, TTSPlaybackStatus.FAILED)
        self.assertEqual(result.chunks_played, 0)
        self.assertEqual(result.error, "播放失败")

    def test_callable_sink_is_supported_for_simple_fakes(self):
        played = []
        player = InterruptibleTTSPlayer(
            backend=FakeBackend([
                np.array([1], dtype=np.int16),
            ]),
            cancel_scope=CancelScope(),
            audio_sink=played.append,
        )

        result = player.speak("可调用")

        self.assertEqual(result.status, TTSPlaybackStatus.COMPLETED)
        self.assertEqual(len(played), 1)

    def test_playback_result_is_frozen_and_validated(self):
        result = TTSPlaybackResult(
            text="测试",
            status=TTSPlaybackStatus.COMPLETED,
            chunks_played=0,
            generation=0,
            error=None,
        )

        with self.assertRaises(FrozenInstanceError):
            result.text = "修改"

        with self.assertRaisesRegex(ValueError, "chunks_played"):
            TTSPlaybackResult(
                text="测试",
                status=TTSPlaybackStatus.COMPLETED,
                chunks_played=-1,
                generation=0,
                error=None,
            )


class TTSFactoryTests(unittest.TestCase):
    def test_factory_creates_null_backend(self):
        backend = create_tts_backend(" NULL ")

        self.assertIsInstance(backend, TTSBackend)
        self.assertEqual(backend.sample_rate, 16_000)
        self.assertEqual(list(backend.synthesize("不发声")), [])

    def test_factory_rejects_unknown_backend(self):
        with self.assertRaisesRegex(ValueError, "TTS_BACKEND 不受支持"):
            create_tts_backend("kokoro")


if __name__ == "__main__":
    unittest.main()
