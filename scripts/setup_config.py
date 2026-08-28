# -*- coding: utf-8 -*-
"""交互式配置向导：检查并填写 .env，不必手工编辑文件。

设计原则：
- 密钥只写入 .env（已被 .gitignore 忽略），终端里始终掩码显示，不打印全文。
- 可选做一次真实连通性测试，确认密钥、地址和模型名都可用。
- 不修改 src/main.py，不改变程序运行逻辑，只负责配置。

用法：
    .venv/Scripts/python.exe -B scripts/setup_config.py           # 交互式
    .venv/Scripts/python.exe -B scripts/setup_config.py --check   # 只体检不修改
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_DIR / ".env"

FIELDS = [
    ("LLM_API_KEY", "大模型 API 密钥（DeepSeek 控制台获取）", "", True),
    ("LLM_BASE_URL", "大模型接口地址", "https://api.deepseek.com", False),
    ("LLM_MODEL", "模型名称", "deepseek-chat", False),
    ("ASR_BACKEND", "语音识别后端", "sensevoice", False),
    ("ASR_SENSEVOICE_MODEL", "语音识别模型", "iic/SenseVoiceSmall", False),
    ("TTS_BACKEND", "语音合成后端（null=不发声）", "null", False),
    ("TTS_ENABLED", "是否启用语音播报", "false", False),
    ("MODELSCOPE_CACHE", "模型缓存目录（C 盘紧张时指向 D 盘）", "", False),
]


def mask(value):
    """敏感值掩码，避免密钥出现在终端记录或截图里。"""
    if not value:
        return "（空）"
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * 8 + value[-4:]


def read_env():
    if not ENV_FILE.is_file():
        return {}
    result = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip()
    return result


def write_env(values):
    """整体重写 .env，保留说明注释，密钥不回显。"""
    known = set()
    lines = [
        "# 本机配置，不提交（.gitignore 已忽略）",
        "# 由 scripts/setup_config.py 生成，也可手工编辑",
        "",
    ]
    for name, description, _default, _secret in FIELDS:
        known.add(name)
        value = values.get(name, "")
        if not value:
            continue
        lines.append("# " + description)
        lines.append(name + "=" + value)
        lines.append("")
    extra = {k: v for k, v in values.items() if k not in known}
    if extra:
        lines.append("# 其他配置")
        for key in sorted(extra):
            lines.append(key + "=" + extra[key])
        lines.append("")
    ENV_FILE.write_text("\n".join(lines), encoding="utf-8")


def check(values):
    """返回缺失或明显不对的配置项说明。"""
    problems = []
    api_key = values.get("LLM_API_KEY", "")
    if not api_key:
        problems.append("LLM_API_KEY 为空 —— 主程序会在启动时直接失败")
    elif api_key.startswith("replace-with"):
        problems.append("LLM_API_KEY 还是示例占位值，不是真实密钥")
    if not values.get("LLM_BASE_URL"):
        problems.append("LLM_BASE_URL 为空")
    if not values.get("LLM_MODEL"):
        problems.append("LLM_MODEL 为空")
    return problems


def test_connection(values, timeout=30.0):
    """用最小请求验证密钥、地址和模型名是否真的可用。"""
    base = values.get("LLM_BASE_URL", "").rstrip("/")
    key = values.get("LLM_API_KEY", "")
    model = values.get("LLM_MODEL", "")
    if not (base and key and model):
        return False, "配置不完整，跳过连通性测试"

    payload = json.dumps({
        "model": model,
        "thinking": {"type": "disabled"},
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }).encode("utf-8")
    request = urllib.request.Request(
        base + "/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status == 200:
                return True, "密钥、地址和模型名均可用"
            return False, "服务返回 HTTP " + str(response.status)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")[:180]
        if error.code == 401:
            return False, "密钥无效（HTTP 401）：" + detail
        if error.code == 404:
            return False, "地址或模型名不对（HTTP 404）：" + detail
        return False, "HTTP " + str(error.code) + "：" + detail
    except Exception as error:
        return False, type(error).__name__ + ": " + str(error)


def show(values):
    print("\n当前配置：")
    for name, description, default, secret in FIELDS:
        value = values.get(name, "")
        if secret:
            shown = mask(value)
        else:
            shown = value or ("（未设置，默认 " + (default or "无") + "）")
        print("  {:22} {}".format(name, shown))
        print("  {:22} └ {}".format("", description))


def main():
    only_check = "--check" in sys.argv
    values = read_env()

    print("=" * 62)
    print("  实验语音助手 · 配置向导")
    print("=" * 62)
    print("配置文件：" + str(ENV_FILE))
    if not ENV_FILE.is_file():
        print("（尚不存在，将新建）")

    show(values)

    problems = check(values)
    print("\n体检结果：")
    if problems:
        for item in problems:
            print("  ❌ " + item)
    else:
        print("  ✅ 必填项齐全")

    if only_check:
        if problems:
            print("\n用不带 --check 的方式运行本脚本即可逐项填写。")
        sys.exit(1 if problems else 0)

    if not sys.stdin.isatty():
        print("\n当前不是交互式终端，无法逐项输入。")
        print("请在 PowerShell 里运行：")
        print(r"  .\.venv\Scripts\python.exe -B scripts\setup_config.py")
        sys.exit(1)

    print("\n逐项填写（直接回车表示保持不变）：")
    for name, description, default, secret in FIELDS:
        current = values.get(name, "")
        shown = mask(current) if secret else current
        hint = shown or default or "空"
        entered = input("  {}（{}）[{}]: ".format(name, description, hint)).strip()
        if entered:
            values[name] = entered
        elif not current and default:
            values[name] = default

    write_env(values)
    print("\n已写入 " + str(ENV_FILE))

    remaining = check(values)
    if remaining:
        for item in remaining:
            print("  ❌ " + item)
        return

    print("\n正在做一次真实连通性测试……")
    ok, message = test_connection(values)
    print(("  ✅ " if ok else "  ❌ ") + message)
    if ok:
        print("\n现在可以启动主程序：")
        print(r"  .\.venv\Scripts\python.exe -B -m src.main")


if __name__ == "__main__":
    main()
