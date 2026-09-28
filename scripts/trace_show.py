# -*- coding: utf-8 -*-
"""Bad case 回放：按时间顺序打印某条 trace 的完整链路。

用法（在项目根目录运行）：
    python -m scripts.trace_show <trace_id>
    python -m scripts.trace_show --last          # 打印最近一条 trace
    python -m scripts.trace_show --list          # 列出最近 20 条 trace
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许直接运行脚本，也允许 python -m scripts.trace_show
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "web") not in sys.path:
    sys.path.insert(0, str(_ROOT / "web"))

from tracing import list_traces, read_trace  # noqa: E402

STAGE_LABELS = {
    "start": "开始",
    "intent": "意图判定",
    "tool_select": "工具选择",
    "tool_exec": "工具执行",
    "generate": "生成回复",
    "degrade": "降级",
    "step_limit": "步数耗尽",
}


def _fmt(value) -> str:
    import json
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def print_trace(trace_id: str) -> int:
    rows = read_trace(trace_id)
    if not rows:
        print(f"找不到 trace：{trace_id}")
        print("提示：先运行系统产生对话，或用 python -m scripts.trace_show --list 查看可回放的 trace。")
        return 1
    print(f"trace_id={trace_id}  共 {len(rows)} 个节点\n")
    for i, row in enumerate(rows, 1):
        stage = row.get("stage", "?")
        label = STAGE_LABELS.get(stage, stage)
        ok = row.get("ok", True)
        mark = "✅" if ok else "❌"
        print(f"[{i:02d}] {row.get('ts', '')}  {label}  {mark}")
        if row.get("input") is not None:
            print(f"    入参: {_fmt(row['input'])}")
        if row.get("output") is not None:
            print(f"    出参: {_fmt(row['output'])}")
        meta = []
        if row.get("latency_ms") is not None:
            meta.append(f"耗时 {row['latency_ms']}ms")
        if row.get("tokens") is not None:
            meta.append(f"tokens {row['tokens']}")
        if row.get("model"):
            meta.append(f"模型 {row['model']}")
        if row.get("conversation_id"):
            meta.append(f"会话 {row['conversation_id']}")
        if meta:
            print(f"    {(' | '.join(meta))}")
        print()
    return 0


def print_list() -> None:
    traces = list_traces(20)
    if not traces:
        print("trace.jsonl 还是空的。先跑一次对话（web/logs/trace.jsonl 会自动生成）。")
        return
    print("最近 20 条 trace：")
    for t in traces:
        stages = " → ".join(str(s) for s in t.get("stages", []))
        mark = "OK" if t.get("ok") else "BAD"
        print(f"  {t['trace_id']}  {t.get('start_ts','')}  [{mark}]  {stages}")


def main() -> int:
    parser = argparse.ArgumentParser(description="小科 trace 回放工具")
    parser.add_argument("trace_id", nargs="?", help="trace id（12 位 hex）")
    parser.add_argument("--last", action="store_true", help="打印最近一条 trace")
    parser.add_argument("--list", action="store_true", help="列出最近 20 条 trace")
    args = parser.parse_args()

    if args.list:
        print_list()
        return 0
    if args.last:
        traces = list_traces(1)
        if not traces:
            print("trace.jsonl 还是空的。")
            return 1
        return print_trace(traces[0]["trace_id"])
    if not args.trace_id:
        parser.print_help()
        return 2
    return print_trace(args.trace_id)


if __name__ == "__main__":
    raise SystemExit(main())
