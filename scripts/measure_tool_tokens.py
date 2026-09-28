# -*- coding: utf-8 -*-
"""用真实 API 的 prompt_tokens 量化「工具按需注入」的收益。

tiktoken 词表下不动（墙），改用模型自己的分词器：
发两次同样的请求，只差工具列表（全量 vs 按需注入），读回 prompt_tokens 相减。
"""
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(r"D:\me\ai107")
for p in (str(ROOT), str(ROOT / "web")):
    if p not in sys.path:
        sys.path.insert(0, p)

import lab_tools  # noqa: E402
import tool_router  # noqa: E402
from agent.core import TOOLS  # noqa: E402

cfg = json.load(open(ROOT / "web" / "settings.json", encoding="utf-8"))
KEY = cfg["api_keys"]["custom"]
URL = cfg["provider_profiles"]["custom"]["base_url"].rstrip("/")
MODEL = cfg["provider_profiles"]["custom"]["model"]

core_only = [t for t in TOOLS if t["function"]["name"] not in lab_tools.names()]

MSG = "算一下 0.5 乘以 1.56"


def full_tools():
    seen, out = set(), []
    for t in list(lab_tools.openai_tools()) + core_only:
        n = t["function"]["name"]
        if n not in seen:
            seen.add(n)
            out.append(t)
    return out


def probe(tools, tag):
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "你是实验助手。"},
            {"role": "user", "content": MSG},
        ],
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": 16,
    }
    try:
        r = httpx.post(URL + "/chat/completions",
                       headers={"Authorization": "Bearer " + KEY,
                                "Content-Type": "application/json"},
                       json=body, timeout=60)
        if r.status_code != 200:
            print(f"  [{tag}] HTTP {r.status_code}  {r.text[:160]}")
            return None
        u = r.json().get("usage", {})
        pt = u.get("prompt_tokens")
        print(f"  [{tag}] {len(tools):3d} 个工具 → prompt_tokens = {pt}")
        return pt
    except Exception as e:  # noqa: BLE001
        print(f"  [{tag}] FAIL {type(e).__name__} {str(e)[:120]}")
        return None


print("=" * 80)
print("工具按需注入：token 收益实测（用模型自己的分词器）")
print("=" * 80)
alltools = full_tools()
inj = tool_router.build_tools(None, MSG, extra_tools=core_only)
print(f"  全量工具 {len(alltools)} 个 / 注入工具 {len(inj)} 个\n")

base = probe(alltools, "全集")
cur = probe(inj, "按需注入")

print()
if base and cur:
    saved = base - cur
    print(f"  → 单轮 prompt 从 {base} 降到 {cur} token，省 {saved} token/轮 "
          f"({saved / base * 100:.0f}%)")
    print(f"  → 结合实测：一次任务平均 2 轮模型调用，即省约 {saved * 2} token/任务")
else:
    print("  未拿到完整对照数据")
