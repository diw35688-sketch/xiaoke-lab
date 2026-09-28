# -*- coding: utf-8 -*-
"""评测跑批：驱动 stream_agent 走真实链路，产生 trace 供 eval_report 统计。

与 eval_report.py 配套：
    1) python -m scripts.eval_run --provider custom --limit 10        # 产生 trace
    2) python -m scripts.eval_report                                  # 出指标

--provider 只在内存里切（不动 settings.json）：custom / deepseek / ustc …

用例 30 条，按真实使用分层：
  实验记录 4 / 试剂配比 5 / 计算换算 4 / 知识检索 3 / 工具操作 6
  多轮指代 2（负样本）/ 越界闲聊 3（负样本）/ 信息缺失 3（负样本，应反问）
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
for _p in (str(_ROOT), str(_ROOT / "web")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import settings_store  # noqa: E402
from agent.core import stream_agent  # noqa: E402


def use_provider(provider_id: str | None) -> str:
    """把一个 provider 覆盖到 settings_store.current()（进程内，不落盘）。"""
    base = settings_store.current()
    if not provider_id:
        return f"{base.base_url} / {base.model_name}  (settings.json 原样)"
    prof = (base.provider_profiles or {}).get(provider_id)
    key = (base.api_keys or {}).get(provider_id)
    if not prof or not key:
        raise SystemExit(f"provider「{provider_id}」未配置（profiles={list(base.provider_profiles)}）")
    override = replace(base, api_key=key, base_url=prof["base_url"], model_name=prof["model"])
    settings_store.current = lambda: override
    return f"{prof['base_url']} / {prof['model']}  (provider={provider_id})"


# (消息, 分类, 是否负样本)
CASES: list[tuple[str, str, bool]] = [
    # ── 实验记录（主路径）──
    ("记一下：刚加了 5 克无水硫酸铜", "实验记录", False),
    ("这一步做完了，现象是溶液变蓝", "实验记录", False),
    ("记录：室温 25 度，静置 30 分钟", "实验记录", False),
    ("帮我记一下这个结果", "实验记录", False),
    # ── 试剂配比（高风险，错误代价最高）──
    ("怎么配 5M NaCl", "试剂配比", False),
    ("配 100ml 的 1M Tris 要多少克", "试剂配比", False),
    ("0.5M EDTA 怎么配", "试剂配比", False),
    ("五水硫酸铜要称多少才能得到 2 克无水", "试剂配比", False),
    ("这个试剂有毒吗", "试剂配比", False),
    # ── 计算换算 ──
    ("算一下 0.5 乘以 1.56", "计算换算", False),
    ("把 100 微升换算成毫升", "计算换算", False),
    ("稀释 10 倍要加多少水", "计算换算", False),
    ("3 毫克每毫升等于多少微克每微升", "计算换算", False),
    # ── 知识检索 ──
    ("ABC 的引物是什么", "知识检索", False),
    ("PCR 的反应体系是什么", "知识检索", False),
    ("这个蛋白的分子量是多少", "知识检索", False),
    # ── 工具操作 ──
    ("帮我计时 10 分钟", "工具操作", False),
    ("查一下储存库有什么", "工具操作", False),
    ("帮我安排下午的实验时间", "工具操作", False),
    ("现在几点了", "工具操作", False),
    ("显示当前步骤", "工具操作", False),
    ("这个方案总共几步", "工具操作", False),
    # ── 负样本：多轮指代 ──
    ("把它加到刚才那个里", "指代不明", True),
    ("再来一次", "指代不明", True),
    # ── 负样本：越界闲聊 ──
    ("今天天气怎么样", "越界闲聊", True),
    ("帮我写一首诗", "越界闲聊", True),
    ("推荐一部电影", "越界闲聊", True),
    # ── 负样本：信息缺失（应反问而不是瞎编）──
    ("加一点就行", "信息缺失", True),
    ("那个东西准备好了吗", "信息缺失", True),
    ("按老规矩来", "信息缺失", True),
]


def run_case(message: str, conversation_id: str) -> dict:
    history = [{"role": "user", "content": message}]
    text_parts: list[str] = []
    tools: list[str] = []
    started = time.time()
    error = None
    try:
        for chunk in stream_agent(history, conversation_id, None, None, allow_tools=True):
            if not isinstance(chunk, str):
                continue
            if chunk.startswith("[[LABTHINK]]"):
                continue
            if chunk.startswith("[[LABCARD]]"):
                try:
                    card = json.loads(chunk[len("[[LABCARD]]"):])
                except json.JSONDecodeError:
                    continue
                name = card.get("name") or card.get("tool") or card.get("title")
                if name and str(name) not in tools:
                    tools.append(str(name))
                continue
            text_parts.append(chunk)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
    return {
        "message": message,
        "reply": "".join(text_parts).strip(),
        "tools": tools,
        "elapsed_ms": int((time.time() - started) * 1000),
        "error": error,
        "trace_id": conversation_id,
    }


def main() -> int:
    args = sys.argv[1:]
    provider = None
    if "--provider" in args:
        i = args.index("--provider")
        provider = args[i + 1] if i + 1 < len(args) else None
    def opt(name, default):
        if name in args:
            i = args.index(name)
            if i + 1 < len(args):
                try:
                    return int(args[i + 1])
                except ValueError:
                    return default
        return default

    skip = opt("--skip", 0)
    limit = opt("--limit", len(CASES))
    delay = opt("--delay", 3)
    retries = opt("--retries", 3)

    target = use_provider(provider)
    cases = CASES[skip:skip + limit]

    print("=" * 78)
    print(f"评测跑批：{len(cases)} 条（第 {skip+1} ~ {skip+len(cases)} 条）")
    print(f"模型：{target}")
    print(f"间隔 {delay}s，403 限流重试 {retries} 次")
    print("=" * 78)

    results = []
    stamp = int(time.time())
    for i, (msg, cat, neg) in enumerate(cases, 1):
        cid = f"eval-{stamp}-{skip+i:02d}"
        r = None
        for attempt in range(1, retries + 1):
            print(f"\n[{skip+i}/{len(CASES)}] {cat}{'（负样本）' if neg else ''}  ←  {msg}")
            r = run_case(msg, cid + ("" if attempt == 1 else f"-r{attempt}"))
            if r["error"] and "403" in r["error"] and attempt < retries:
                wait = 15 * attempt
                print(f"    ~ 403 限流，等 {wait}s 重试（{attempt}/{retries-1}）")
                time.sleep(wait)
                continue
            break
        r["category"] = cat
        r["negative"] = neg
        results.append(r)
        if r["error"]:
            print(f"    X {r['error'][:130]}")
        else:
            print(f"    OK {r['elapsed_ms']}ms  工具={r['tools'] or '—'}")
            print(f"    -> {r['reply'][:110]}")
        if i < len(cases):
            time.sleep(delay)

    ok = sum(1 for r in results if not r["error"])
    print("\n" + "=" * 78)
    print(f"完成 {ok}/{len(results)}")
    print("下一步：python -m scripts.eval_report")
    print("=" * 78)
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
