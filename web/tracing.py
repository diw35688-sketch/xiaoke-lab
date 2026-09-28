# -*- coding: utf-8 -*-
"""执行留痕（tracing）：把一次 turn 的关键链路写成 JSONL，支持 bad case 回放。

设计目标：
- 统一 trace_id：一次 agent turn（从用户消息到最终回复/降级）生成一个 id。
- 关键节点写一行 JSONL：{ts, trace_id, stage, input, output, latency_ms, tokens, ok, ...}
  贯穿「意图判定 → 工具选择 → 检索/工具执行 → 生成 → 降级」。
- 写失败（只读目录 / 打包环境）时静默降级，绝不影响主流程。
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

TRACE_DIR = Path(__file__).resolve().parent / "logs"
TRACE_FILE = TRACE_DIR / "trace.jsonl"

_lock = threading.Lock()
_cache: dict[str, bool] = {}


def _writable() -> bool:
    if "writable" in _cache:
        return _cache["writable"]
    ok = False
    try:
        TRACE_DIR.mkdir(parents=True, exist_ok=True)
        with TRACE_FILE.open("a", encoding="utf-8") as probe:
            probe.write("")
        ok = True
    except OSError:
        ok = False
    _cache["writable"] = ok
    return ok


def _clip(value, max_chars: int = 500):
    """摘要截断：太长会把 trace 文件撑爆，也会泄漏完整敏感内容。"""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            text = str(value)
    else:
        text = str(value)
    if len(text) <= max_chars:
        return value if isinstance(value, (str, int, float, bool)) or value is None else text[:max_chars]
    if isinstance(value, str):
        return value[:max_chars] + f"…({len(value)}字符)"
    return text[:max_chars] + f"…({len(text)}字符)"


def new_trace_id() -> str:
    """生成短 trace id：12 位 hex，兼顾可读性与唯一性。"""
    return uuid.uuid4().hex[:12]


def record(trace_id: str, stage: str, *, input=None, output=None,
           latency_ms=None, tokens=None, ok=True, **extra) -> None:
    """写一行 trace 记录。所有参数都可选，写失败静默跳过。"""
    if not _writable():
        return
    line = {
        "ts": datetime.now().isoformat(timespec="milliseconds"),
        "trace_id": trace_id,
        "stage": stage,
        "input": _clip(input),
        "output": _clip(output),
        "latency_ms": latency_ms,
        "tokens": tokens,
        "ok": ok,
    }
    for key, value in extra.items():
        line[key] = _clip(value)
    try:
        with _lock:
            with TRACE_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        _cache["writable"] = False


def read_trace(trace_id: str) -> list[dict]:
    """按写入顺序读取某条 trace 的全部记录（回放用）。"""
    if not TRACE_FILE.exists():
        return []
    rows: list[dict] = []
    try:
        with TRACE_FILE.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("trace_id") == trace_id:
                    rows.append(row)
    except OSError:
        return []
    rows.sort(key=lambda r: r.get("ts", ""))
    return rows


def list_traces(limit: int = 20) -> list[dict]:
    """列出最近 N 个 trace 的摘要（按出现顺序取最后 N 个 trace_id）。"""
    if not TRACE_FILE.exists():
        return []
    seen: dict[str, dict] = {}
    try:
        with TRACE_FILE.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                tid = row.get("trace_id")
                if not tid:
                    continue
                if tid not in seen:
                    seen[tid] = {
                        "trace_id": tid,
                        "start_ts": row.get("ts", ""),
                        "stages": [],
                        "ok": True,
                    }
                seen[tid]["stages"].append(row.get("stage"))
                seen[tid]["ok"] = seen[tid]["ok"] and bool(row.get("ok", True))
                seen[tid]["end_ts"] = row.get("ts", "")
    except OSError:
        return []
    traces = list(seen.values())
    traces.sort(key=lambda t: t.get("start_ts", ""), reverse=True)
    return traces[:limit]


def timed():
    """毫秒级计时起点，返回开始时间戳（秒）。"""
    return time.time()


def elapsed_ms(start: float) -> int:
    """从 timed() 的起点计算耗时（毫秒，取整）。"""
    return max(0, int((time.time() - start) * 1000))
