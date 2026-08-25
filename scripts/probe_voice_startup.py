"""Read voice prewarm timing from a real Chromium page through CDP."""

from __future__ import annotations

import asyncio
import json
import os
import time

import httpx
import websockets


DEBUG_BASE = os.environ.get("VOICE_PROBE_DEBUG_BASE", "http://127.0.0.1:9224")


async def main() -> None:
    async with httpx.AsyncClient(trust_env=False, timeout=5) as client:
        pages = (await client.get(DEBUG_BASE + "/json")).json()
    page = next(
        item for item in pages
        if item.get("type") == "page"
        and item.get("url", "").startswith("http://127.0.0.1:8000/")
    )

    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=4 * 1024 * 1024) as socket:
        command_id = 0

        async def evaluate(expression: str):
            nonlocal command_id
            command_id += 1
            await socket.send(json.dumps({
                "id": command_id,
                "method": "Runtime.evaluate",
                "params": {"expression": expression, "returnByValue": True},
            }))
            while True:
                message = json.loads(await socket.recv())
                if message.get("id") == command_id:
                    return message["result"]["result"].get("value")

        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            raw = await evaluate("JSON.stringify(window.__voiceStartupTimings || {})")
            timing = json.loads(raw or "{}")
            if (
                "voice_stack_total_ms" in timing
                and "silero_permission_init_ms" in timing
            ):
                resources = json.loads(await evaluate("JSON.stringify(performance.getEntriesByType('resource').filter(x => x.name.includes('voice/') || x.name.includes('/asr/warmup') || x.name.includes('/tts/warmup')).map(x => x.name))"))
                external = [item for item in resources if not item.startswith("http://127.0.0.1:8000/")]
                startup_card = await evaluate("document.querySelector('[data-block-id$=\"voice-startup\"]')?.innerText || ''")
                voice_samples = json.loads(await evaluate("JSON.stringify(window.__voiceTimingSamples || [])"))
                print(json.dumps({
                    "timing": timing,
                    "startup_card": startup_card,
                    "voice_samples": voice_samples,
                    "external_voice_resources": external,
                }, ensure_ascii=False))
                return
            await asyncio.sleep(0.2)
        raise RuntimeError("45秒内没有得到完整的语音栈与麦克风初始化计时")


if __name__ == "__main__":
    asyncio.run(main())
