"""Shared Web ASR lifecycle and source-audio evidence handling."""

from __future__ import annotations

import hashlib
import os
import re
import threading
import time
import uuid
import wave
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable

from config import AUDIO_STORAGE_ROOT
from src.asr.backend import ASRBackend
from src.asr.factory import create_asr_backend
from src.asr.schemas import ASRResult


class AudioValidationError(ValueError):
    """The uploaded bytes are not the Web Turn PCM contract."""


@dataclass(frozen=True)
class RecognizedAudio:
    result: ASRResult
    audio_rel_path: str
    audio_sha256: str
    audio_bytes: int

    def evidence(self) -> dict[str, object]:
        return {
            "payload": self.result.to_dict(),
            "audio_rel_path": self.audio_rel_path,
            "audio_sha256": self.audio_sha256,
            "audio_bytes": self.audio_bytes,
        }


def _safe_segment(value: str) -> str:
    readable = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")[:48]
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    return f"{readable or 'id'}-{digest}"


def _rebind_audio_path(result: ASRResult, audio_path: Path) -> ASRResult:
    payload = result.to_dict()
    payload["audio_path"] = str(audio_path)
    return ASRResult.from_dict(payload)


class ASRApplicationService:
    """Own backend reuse, WAV validation, hashing and audio file lifecycle only."""

    def __init__(
        self,
        *,
        audio_root: Path = AUDIO_STORAGE_ROOT,
        backend_factory: Callable[[], ASRBackend] = create_asr_backend,
    ) -> None:
        self.audio_root = Path(audio_root)
        self._backend_factory = backend_factory
        self._backend: ASRBackend | None = None
        self._load_error: str | None = None
        self._load_ms: int | None = None
        self._lock = threading.Lock()

    def status(self) -> dict[str, object]:
        return {
            "loaded": self._backend is not None,
            "error": self._load_error,
            "engine": "SenseVoiceSmall",
            "load_ms": self._load_ms,
        }

    def warmup(self) -> dict[str, object]:
        self._get_backend()
        return self.status()

    def _get_backend(self) -> ASRBackend:
        with self._lock:
            if self._backend is not None:
                return self._backend
            if self._load_error is not None:
                raise RuntimeError(self._load_error)
            started = time.perf_counter()
            try:
                self._backend = self._backend_factory()
            except Exception as error:
                self._load_error = f"{type(error).__name__}: {error}"
                raise RuntimeError(self._load_error) from error
            self._load_ms = round((time.perf_counter() - started) * 1000)
            return self._backend

    @staticmethod
    def validate_wav(payload: bytes) -> None:
        if not payload:
            raise AudioValidationError("音频为空。")
        try:
            from io import BytesIO

            with wave.open(BytesIO(payload), "rb") as wav:
                channels = wav.getnchannels()
                sample_rate = wav.getframerate()
                sample_width = wav.getsampwidth()
                frames = wav.getnframes()
        except (EOFError, wave.Error) as error:
            raise AudioValidationError("音频必须是有效 WAV 文件。") from error
        if channels != 1 or sample_rate != 16000 or sample_width != 2:
            raise AudioValidationError("音频必须是 16 kHz、单声道、16-bit PCM WAV。")
        if frames <= 0:
            raise AudioValidationError("WAV 不包含音频帧。")

    def recognize_upload(
        self,
        payload: bytes,
        *,
        conversation_id: str,
        request_id: str,
        lab_session_id: str | None,
        retain: bool = True,
        on_phase: Callable[[str], None] | None = None,
    ) -> RecognizedAudio:
        self.validate_wav(payload)
        digest = hashlib.sha256(payload).hexdigest()
        pending_dir = self.audio_root / ".pending"
        pending_dir.mkdir(parents=True, exist_ok=True)
        pending_path = pending_dir / f"{_safe_segment(request_id)}-{uuid.uuid4().hex}.wav"
        pending_path.write_bytes(payload)
        if on_phase is not None:
            on_phase("audio_saved")
        final_path: Path | None = None
        try:
            if on_phase is not None:
                on_phase("asr_started")
            result = self._get_backend().recognize(pending_path)
            if on_phase is not None:
                on_phase("asr_completed")
            if not result.is_final:
                raise RuntimeError("ASR backend 没有返回最终结果。")
            conversation_dir = (
                self.audio_root / "conversations" / _safe_segment(conversation_id)
            )
            if lab_session_id is not None:
                conversation_dir = (
                    conversation_dir / "sessions" / _safe_segment(lab_session_id)
                )
            final_path = conversation_dir / f"{_safe_segment(request_id)}.wav"
            final_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(pending_path, final_path)
            rebound = _rebind_audio_path(result, final_path)
            relative = final_path.relative_to(self.audio_root).as_posix()
            recognized = RecognizedAudio(rebound, relative, digest, len(payload))
            if not retain:
                final_path.unlink(missing_ok=True)
            return recognized
        except Exception:
            pending_path.unlink(missing_ok=True)
            if final_path is not None and final_path.exists():
                final_path.unlink(missing_ok=True)
            raise

    def delete_audio(self, audio_rel_path: str) -> bool:
        path = (self.audio_root / audio_rel_path).resolve()
        root = self.audio_root.resolve()
        if root not in path.parents:
            raise ValueError("音频路径越过存储根目录。")
        existed = path.exists()
        path.unlink(missing_ok=True)
        return existed

    def cleanup_pending(
        self,
        *,
        referenced_paths: Iterable[str] = (),
        now: datetime | None = None,
        max_age: timedelta = timedelta(hours=24),
    ) -> int:
        pending_dir = self.audio_root / ".pending"
        if not pending_dir.exists():
            return 0
        referenced = {Path(value).as_posix() for value in referenced_paths}
        threshold = (now or datetime.now(timezone.utc)).timestamp() - max_age.total_seconds()
        removed = 0
        for path in pending_dir.glob("*.wav"):
            relative = path.relative_to(self.audio_root).as_posix()
            if relative in referenced or path.stat().st_mtime >= threshold:
                continue
            path.unlink(missing_ok=True)
            removed += 1
        return removed


_shared_service = ASRApplicationService()


def get_asr_application_service() -> ASRApplicationService:
    return _shared_service
