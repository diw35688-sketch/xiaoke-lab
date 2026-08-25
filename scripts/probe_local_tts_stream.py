"""Measure the production /tts/stream endpoint without saving its audio."""

from __future__ import annotations

import sys
import time

import httpx


URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/tts/stream"


def run_once(number: int) -> None:
    started = time.perf_counter()
    first_chunk_at = None
    total_bytes = 0
    with httpx.stream(
        "POST",
        URL,
        json={"text": "语音和文字同步测试。"},
        timeout=httpx.Timeout(30, connect=5),
        trust_env=False,
    ) as response:
        headers_at = time.perf_counter()
        response.raise_for_status()
        for chunk in response.iter_bytes():
            if not chunk:
                continue
            if first_chunk_at is None:
                first_chunk_at = time.perf_counter()
            total_bytes += len(chunk)
    completed = time.perf_counter()
    if first_chunk_at is None:
        raise RuntimeError("本地流式接口没有返回音频")
    print(
        f"round={number} "
        f"headers_ms={round((headers_at - started) * 1000)} "
        f"first_audio_ms={round((first_chunk_at - started) * 1000)} "
        f"complete_ms={round((completed - started) * 1000)} "
        f"audio_bytes={total_bytes}"
    )


for round_number in (1, 2):
    run_once(round_number)
