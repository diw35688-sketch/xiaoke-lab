import os
import struct
import sys
import tempfile
import unittest
import wave
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from asr_application_service import (  # noqa: E402
    ASRApplicationService,
    AudioValidationError,
)
from src.asr.schemas import ASRResult  # noqa: E402


def _wav_payload(rate=16000, channels=1, width=2):
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(struct.pack("<" + "h" * 160, *([0] * 160)))
    return buffer.getvalue()


class _Backend:
    def __init__(self, *, fail=False):
        self.calls = 0
        self.fail = fail

    def recognize(self, audio_path, *, language="zh"):
        self.calls += 1
        if self.fail:
            raise RuntimeError("fake asr failed")
        return ASRResult(
            asr_transcript="温度八十摄氏度",
            asr_model_raw_text="温度八十摄氏度",
            audio_path=str(audio_path),
            audio_duration_seconds=0.01,
            recognition_seconds=0.02,
            model="fake",
            language=language,
            is_final=True,
        )


class ASRApplicationServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_validates_exact_web_wav_contract(self):
        service = ASRApplicationService(audio_root=self.root, backend_factory=_Backend)
        for payload in (b"not wav", _wav_payload(rate=8000), _wav_payload(channels=2)):
            with self.assertRaises(AudioValidationError):
                service.validate_wav(payload)

    def test_recognizes_moves_and_returns_complete_evidence(self):
        backend = _Backend()
        service = ASRApplicationService(
            audio_root=self.root, backend_factory=lambda: backend
        )
        payload = _wav_payload()
        recognized = service.recognize_upload(
            payload, conversation_id="c/1", request_id="r/1",
            lab_session_id="lab/1",
        )
        stored = self.root / recognized.audio_rel_path
        self.assertTrue(stored.is_file())
        self.assertEqual(stored.read_bytes(), payload)
        self.assertEqual(recognized.result.audio_path, str(stored))
        self.assertEqual(recognized.evidence()["payload"]["schema_version"], 2)
        self.assertEqual(backend.calls, 1)
        self.assertFalse(any((self.root / ".pending").glob("*.wav")))

    def test_failure_removes_pending_and_nonretained_removes_final(self):
        failing = ASRApplicationService(
            audio_root=self.root, backend_factory=lambda: _Backend(fail=True)
        )
        with self.assertRaises(RuntimeError):
            failing.recognize_upload(
                _wav_payload(), conversation_id="c", request_id="r",
                lab_session_id=None,
            )
        self.assertFalse(any((self.root / ".pending").glob("*.wav")))

        service = ASRApplicationService(audio_root=self.root, backend_factory=_Backend)
        recognized = service.recognize_upload(
            _wav_payload(), conversation_id="c", request_id="r2",
            lab_session_id=None, retain=False,
        )
        self.assertFalse((self.root / recognized.audio_rel_path).exists())

    def test_cleanup_only_old_unreferenced_pending(self):
        pending = self.root / ".pending"
        pending.mkdir()
        old = pending / "old.wav"
        kept = pending / "kept.wav"
        old.write_bytes(b"x")
        kept.write_bytes(b"x")
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        os.utime(old, (old_time.timestamp(), old_time.timestamp()))
        os.utime(kept, (old_time.timestamp(), old_time.timestamp()))
        service = ASRApplicationService(audio_root=self.root, backend_factory=_Backend)
        removed = service.cleanup_pending(
            referenced_paths=[".pending/kept.wav"],
            now=datetime.now(timezone.utc),
        )
        self.assertEqual(removed, 1)
        self.assertFalse(old.exists())
        self.assertTrue(kept.exists())


if __name__ == "__main__":
    unittest.main()
