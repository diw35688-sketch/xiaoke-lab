# -*- coding: utf-8 -*-
"""小科固定回归集评测报告。

用法（在项目根目录运行）：
    python -m scripts.eval_report

两部分：
1. 工具路由回归（离线，不调模型）：给定用户消息，检查 build_tools 是否包含预期工具。
2. trace 统计（读 web/logs/trace.jsonl）：任务成功率 / 工具调用正确率 /
   平均步数 / P50 时延 / 平均 token / 降级率。
"""
from __future__ import annotations

import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "web") not in sys.path:
    sys.path.insert(0, str(_ROOT / "web"))

import tool_router  # noqa: E402
from tracing import TRACE_FILE  # noqa: E402

#: usage 分桶字段 —— 与 web/agent/core.py 的 USAGE_BUCKETS 对齐。
#: 命名遵循 OTel GenAI（gen_ai.client.token.usage，input|output 必分）
#: 与 Langfuse（cache_read / cache_write / reasoning 独立计价）。
USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
)

#: 缓存读相对输入价的折扣系数。
#: Langfuse 收录的 OpenAI / Anthropic / Gemini 定价全部是 10:1（cache read = 10% of input），
#: 没配单价时缓存读的默认折算系数。
#: 业界常见是 10%（Langfuse 收录的 OpenAI / Anthropic / Gemini 都是 10:1）。
#: 注意各家差别很大 —— DeepSeek V4.1-Flash 官方是 $0.006 vs $0.30，只有 2%。
#: 配了 model_prices 就按配置算，没配才用这个兜底值。
CACHE_READ_DISCOUNT = 0.1


def _load_price_table() -> dict:
    """读 web/settings.json 里的 model_prices（每百万 token 单价）。

    结构示例（键为模型名前缀，最长的匹配优先）：
        "model_prices": {
          "deepseek-v4-flash": {"input": 0.30, "cache_read": 0.006,
                                "output": 1.20, "currency": "USD"}
        }
    没配就返回空 —— 此时只报「等效全价 token」，不编造金额。
    """
    try:
        settings = json.loads((_ROOT / "web" / "settings.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    table = settings.get("model_prices")
    return table if isinstance(table, dict) else {}


def current_price() -> dict | None:
    """取当前模型的单价条目（按前缀最长匹配）。取不到返回 None。"""
    table = _load_price_table()
    if not table:
        return None
    try:
        import settings_store
        model = settings_store.current().model_name or ""
    except Exception:
        model = ""
    for name in sorted(table, key=len, reverse=True):
        value = table[name]
        if not isinstance(value, dict):
            continue
        if model and (model == name or model.startswith(name)):
            return value
    return None


def cache_read_discount() -> float:
    """缓存读相对输入价的系数：优先用配置的单价，否则用业界兜底值。"""
    price = current_price()
    if price:
        try:
            base = float(price.get("input") or 0)
            cached = float(price.get("cache_read", base))
            if base > 0:
                return cached / base
        except (TypeError, ValueError):
            pass
    return CACHE_READ_DISCOUNT


def billable_equivalent(buckets: dict, discount: float | None = None) -> float:
    """把分桶折算成「等效全价 token」——缓存读按折扣系数计。

    这样不同缓存命中率的两组实验可以直接比大小。
    discount 省略时按当前模型配置的单价推算。
    """
    if discount is None:
        discount = cache_read_discount()
    cache_read = buckets.get("cache_read_tokens", 0)
    total = buckets.get("total_tokens")
    if total:
        # total 里已经含了缓存读部分，把那部分的差价扣掉
        return float(total) - cache_read * (1 - discount)
    plain = (buckets.get("input_tokens", 0) - cache_read
             + buckets.get("output_tokens", 0))
    return plain + cache_read * discount


def estimate_cost(buckets: dict) -> dict | None:
    """按配置的单价估算成本。没配单价返回 None。

    返回 {"amount": float, "currency": str, "discount": float}
    """
    price = current_price()
    if not price:
        return None
    per_million = 1_000_000.0
    try:
        base = float(price.get("input") or 0)
        cached = float(price.get("cache_read", base))
        out = float(price.get("output") or 0)
    except (TypeError, ValueError):
        return None
    cache_read = buckets.get("cache_read_tokens", 0)
    plain_input = max(0, buckets.get("input_tokens", 0) - cache_read)
    amount = (plain_input * base + cache_read * cached
              + buckets.get("output_tokens", 0) * out) / per_million
    return {
        "amount": round(amount, 6),
        "currency": str(price.get("currency") or ""),
        "discount": (cached / base) if base else 0.0,
    }



# core.py 内建工具（不在 lab_tools.openai_tools() 里），build_tools 需要 extra_tools 传入。
CORE_EXTRA_TOOLS = [
    {"type": "function", "function": {"name": "calculate", "description": "基础计算", "parameters": {"type": "object", "properties": {"expression": {"type": "string"}}, "required": ["expression"]}}},
    {"type": "function", "function": {"name": "list_experiments", "description": "列出实验", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "check_conflicts", "description": "检查冲突", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "propose_experiment", "description": "提案实验", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "confirm_create_experiment", "description": "确认创建实验", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "propose_memory", "description": "提案记忆", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "confirm_save_memory", "description": "确认保存记忆", "parameters": {"type": "object", "properties": {}}}},
]

# (用户消息, 必须出现的工具, 必须激活的 skill 组或 None)
ROUTING_CASES = [
    ("算一下 0.5 乘以 1.56", ["calculate"], None),
    ("ABC 的引物是什么", ["search_knowledge_base"], None),
    ("帮我计时 10 分钟", ["start_timer"], None),
    ("查一下储存库有什么", ["list_storage_items"], "storage"),
    ("新建一个 PCR 方案", ["create_protocol_from_text"], "protocol_edit"),
    ("怎么配 5M NaCl", ["create_reagent_prep_from_text"], "reagent_edit"),
    ("帮我安排下午的实验时间", ["plan_clock_schedule"], "time_planning"),
    ("记住这个：我以后都用 1.5ml 离心管", ["propose_memory"], "experiment_mgmt"),
]


def _tool_names(tools: list[dict]) -> set[str]:
    return {t["function"]["name"] for t in tools}


def run_routing_suite() -> tuple[int, int, list[str]]:
    passed = 0
    failures: list[str] = []
    for message, required_tools, expected_skill in ROUTING_CASES:
        tools = tool_router.build_tools(None, message, extra_tools=CORE_EXTRA_TOOLS)
        names = _tool_names(tools)
        missing = [t for t in required_tools if t not in names]
        ok = not missing
        # 期望技能组检测：工具出现即算命中（不单独校验 skill 名，避免重复计数）
        if ok:
            passed += 1
        else:
            failures.append(f"「{message}」缺少工具: {missing}（实际 {len(names)} 个工具）")
    return passed, len(ROUTING_CASES), failures


def load_trace_rows() -> list[dict]:
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
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows


def run_trace_stats(rows: list[dict]) -> dict:
    traces: dict[str, list[dict]] = {}
    for row in rows:
        traces.setdefault(row.get("trace_id", "?"), []).append(row)

    total = len(traces)
    if total == 0:
        return {"total_traces": 0}

    succeeded = 0
    degraded = 0
    tool_exec_rows = []
    latencies = []         # 工具执行耗时（tool_exec 行）
    e2e_latencies = []     # 端到端时延（一条 trace 首尾时间戳差）← Q69 问的"响应时延"
    token_values = []      # 每次模型调用的 token（诊断用）
    task_tokens = []       # 每个任务(一条 trace)的总 token ← Q69 要的"一次任务花多少"
    step_counts = []
    for tid, items in traces.items():
        stages = [r.get("stage") for r in items]
        has_generate = "generate" in stages and all(
            r.get("ok", True) for r in items if r.get("stage") == "generate"
        )
        has_degrade = any(r.get("stage") in ("degrade", "step_limit") for r in items)
        if has_generate:
            succeeded += 1
        if has_degrade:
            degraded += 1
        step_counts.append(sum(1 for s in stages if s == "tool_exec"))
        _ts = sorted(r.get("ts", "") for r in items if r.get("ts"))
        if len(_ts) >= 2:
            try:
                e2e_latencies.append(int(
                    (datetime.fromisoformat(_ts[-1]) - datetime.fromisoformat(_ts[0]))
                    .total_seconds() * 1000))
            except (ValueError, TypeError):
                pass
        trace_tokens = 0
        for r in items:
            if r.get("stage") == "tool_exec":
                tool_exec_rows.append(r)
            if r.get("latency_ms") is not None:
                latencies.append(r["latency_ms"])
            if r.get("tokens") is not None:
                token_values.append(r["tokens"])
                trace_tokens += int(r["tokens"])
        if trace_tokens:
            task_tokens.append(trace_tokens)

    tool_ok = sum(1 for r in tool_exec_rows if r.get("ok", True))
    tool_total = len(tool_exec_rows)

    def pct(part, whole):
        return round(100.0 * part / whole, 1) if whole else 0.0

    def p50(values):
        if not values:
            return None
        return statistics.median(sorted(values))

    # ---- usage 分桶（对齐 OTel GenAI + Langfuse）----
    # 只算 total 无法换算成本：输入/输出/缓存读单价不同。
    bucket_sums = {field: 0 for field in USAGE_FIELDS}
    for r in rows:
        for field in USAGE_FIELDS:
            value = r.get(field)
            if value is not None:
                try:
                    bucket_sums[field] += int(value)
                except (TypeError, ValueError):
                    pass
    total_input = bucket_sums["input_tokens"]
    cache_read = bucket_sums["cache_read_tokens"]
    # 缓存命中率：命中缓存的输入占全部输入的比例。
    # OpenAI 语义下 input(prompt_tokens) 已包含 cached 部分，故分母就是 input。
    cache_hit_rate = pct(cache_read, total_input) if total_input else 0.0

    return {
        "total_traces": total,
        "task_success_rate": pct(succeeded, total),
        "tool_correct_rate": pct(tool_ok, tool_total),
        "avg_steps": round(statistics.mean(step_counts), 2) if step_counts else 0,
        "p50_latency_ms": p50(e2e_latencies),
        "p50_tool_ms": p50(latencies),
        "avg_tokens": round(statistics.mean(task_tokens), 1) if task_tokens else 0,
        "p50_tokens": p50(task_tokens),
        "avg_tokens_per_call": round(statistics.mean(token_values), 1) if token_values else 0,
        "degradation_rate": pct(degraded, total),
        "buckets": bucket_sums,
        "cache_hit_rate": cache_hit_rate,
        "billable_equivalent": round(billable_equivalent(bucket_sums), 1),
        "cost": estimate_cost(bucket_sums),
    }


def main() -> int:
    print("=" * 60)
    print("小科 固定回归集评测报告")
    print("=" * 60)

    print("\n【1】工具路由回归（离线）")
    passed, total, failures = run_routing_suite()
    for msg, required, _ in ROUTING_CASES:
        tools = tool_router.build_tools(None, msg, extra_tools=CORE_EXTRA_TOOLS)
        names = _tool_names(tools)
        missing = [t for t in required if t not in names]
        mark = "✅" if not missing else "❌"
        print(f"  {mark} {msg}")
        if missing:
            print(f"      缺少: {missing}")
    print(f"  → {passed}/{total} 通过")

    print("\n【2】trace 统计（web/logs/trace.jsonl）")
    rows = load_trace_rows()
    if not rows:
        print("  trace.jsonl 为空。先跑一次对话再来看报告。")
        return 0
    stats = run_trace_stats(rows)
    print(f"  trace 总数        : {stats['total_traces']}")
    print(f"  任务成功率        : {stats['task_success_rate']}%")
    print(f"  工具调用正确率    : {stats['tool_correct_rate']}%")
    print(f"  平均步数          : {stats['avg_steps']}")
    print(f"  P50 时延(端到端)  : {stats.get('p50_latency_ms')}ms")
    print(f"  P50 工具执行      : {stats.get('p50_tool_ms')}ms")
    print(f"  平均 token/任务   : {stats.get('avg_tokens')}")
    print(f"  P50 token/任务    : {stats.get('p50_tokens')}")
    print(f"  平均 token/调用   : {stats.get('avg_tokens_per_call')}")
    print(f"  降级率            : {stats['degradation_rate']}%")

    # ---- usage 分桶（OTel GenAI + Langfuse）----
    b = stats["buckets"]
    calls = sum(1 for r in rows if r.get("tokens") is not None)
    traces = stats["total_traces"] or 1
    print("\n  --- token 分桶（OTel gen_ai.client.token.usage / Langfuse）---")
    print(f"  输入 input        : {b['input_tokens']:,}")
    print(f"  输出 output       : {b['output_tokens']:,}")
    print(f"  缓存读 cache_read : {b['cache_read_tokens']:,}"
          f"   （命中率 {stats['cache_hit_rate']}%）")
    if b["cache_write_tokens"]:
        print(f"  缓存写 cache_write: {b['cache_write_tokens']:,}")
    if b["reasoning_tokens"]:
        print(f"  思维链 reasoning  : {b['reasoning_tokens']:,}"
              f"   （占输出 {round(100*b['reasoning_tokens']/max(1,b['output_tokens']),1)}%）")
    discount = cache_read_discount()
    print(f"  等效全价 token    : {stats['billable_equivalent']:,.0f}"
          f"   （缓存读按输入价的 {discount*100:.1f}% 折算；共 {calls} 次调用）")
    cost = stats.get("cost")
    if cost:
        symbol = "$" if cost["currency"].upper() == "USD" else (
            "¥" if cost["currency"] in ("CNY", "RMB") else "")
        unit = f"{symbol}{cost['amount']:.4f}{'' if symbol else ' ' + cost['currency']}"
        print(f"  估算成本          : {unit}（本批 {calls} 次调用，"
              f"折合 {symbol}{cost['amount']/traces:.6f}{'' if symbol else ' ' + cost['currency']}/任务）")
        if cost["currency"].upper() == "USD":
            import os as _os
            rate = _os.environ.get("USD_CNY") or "7.1"
            try:
                print(f"                    ≈ ¥{cost['amount']*float(rate):.4f}"
                      f"（按 1 USD = {rate} CNY）")
            except ValueError:
                pass
    else:
        print("  估算成本          : 未配置单价（在 web/settings.json 加 model_prices 后可用）")

    print("\n" + "=" * 60)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
