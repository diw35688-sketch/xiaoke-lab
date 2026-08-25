"""Exercise production streaming playback inside a real Chromium page."""

from __future__ import annotations

import asyncio
import json
import time

import httpx
import websockets


DEBUG_BASE = "http://127.0.0.1:9223"


async def main() -> None:
    async with httpx.AsyncClient(trust_env=False, timeout=5) as client:
        pages = (await client.get(DEBUG_BASE + "/json")).json()
    page = next(
        item for item in pages
        if item.get("type") == "page" and item.get("url", "").startswith("http://127.0.0.1:8767/")
    )
    websocket_url = page["webSocketDebuggerUrl"]
    next_id = 0

    async with websockets.connect(websocket_url, max_size=4 * 1024 * 1024) as socket:
        async def evaluate(expression: str, *, user_gesture: bool = False):
            nonlocal next_id
            next_id += 1
            command_id = next_id
            await socket.send(json.dumps({
                "id": command_id,
                "method": "Runtime.evaluate",
                "params": {
                    "expression": expression,
                    "returnByValue": True,
                    "awaitPromise": True,
                    "userGesture": user_gesture,
                },
            }))
            while True:
                message = json.loads(await socket.recv())
                if message.get("id") == command_id:
                    if "error" in message:
                        raise RuntimeError(message["error"])
                    result = message.get("result", {}).get("result", {})
                    if result.get("subtype") == "error":
                        raise RuntimeError(result.get("description", "浏览器执行失败"))
                    return result.get("value")

        await evaluate("document.readyState")
        await evaluate(
            """
            (() => {
              window.__voiceTimingSamples = [];
              window.__browserProbe = {started: false, finished: false, error: null};
              const stamp = performance.now();
              window.enqueueSpeech('浏览器流式播放测试。', {
                timing: {
                  intentId: 'browser-probe',
                  deliveryReceivedAt: stamp,
                  screenPublishedAt: stamp,
                  turnStartedAt: stamp,
                },
                onStarted() { window.__browserProbe.started = true; },
                onFinished() { window.__browserProbe.finished = true; },
                onFailed(error) { window.__browserProbe.error = String(error); },
              });
              return true;
            })()
            """,
            user_gesture=True,
        )

        deadline = time.monotonic() + 12
        result = None
        while time.monotonic() < deadline:
            result = await evaluate(
                "JSON.stringify({probe: window.__browserProbe, timing: window.__voiceTimingSamples})"
            )
            parsed = json.loads(result)
            if parsed["probe"]["finished"] or parsed["probe"]["error"]:
                print(json.dumps(parsed, ensure_ascii=False))
                return
            await asyncio.sleep(0.1)
        raise RuntimeError(f"浏览器12秒内未完成播放，最后状态：{result}")


if __name__ == "__main__":
    asyncio.run(main())
