"""同条件比较直接 HTTP 与 OpenAI SDK 两种 LLM 客户端。

默认只打印测试计划，不访问网络。显式传入 ``--run`` 后，才会把三条
人工测试文本发送给当前 Web 设置中的模型服务。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Callable, Iterable


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "web"
for path in (ROOT, WEB_ROOT):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)

import settings_store  # noqa: E402
from src.config import LLM_MAX_TOKENS, LLM_TIMEOUT_SECONDS  # noqa: E402
from src.core.unified_prompts import (  # noqa: E402
    UNIFIED_UNDERSTANDING_SYSTEM_PROMPT,
    build_unified_understanding_user_prompt,
)
from src.core.unified_understanding import (  # noqa: E402
    UnifiedUnderstandingInput,
    parse_unified_understanding,
)
from src.llm.client import OpenAICompatibleLLMClient  # noqa: E402


@dataclass(frozen=True)
class ComparisonCase:
    case_id: str
    text: str
    pending_question_numbers: tuple[int, ...] = ()
    current_question_number: int | None = None

    def request(self) -> UnifiedUnderstandingInput:
        return UnifiedUnderstandingInput(
            raw_text=self.text,
            session_active=True,
            session_id="llm-client-comparison",
            segment_id=1,
            pending_question_numbers=self.pending_question_numbers,
            current_question_number=self.current_question_number,
        )


CASES = (
    ComparisonCase("measurement", "温度升到八十摄氏度。"),
    ComparisonCase("missing_fields", "将溶液加热。"),
    ComparisonCase(
        "control_defer",
        "我先跳过这个问题。",
        pending_question_numbers=(1,),
        current_question_number=1,
    ),
)


@dataclass(frozen=True)
class PlannedCall:
    round_number: int
    case_id: str
    client: str


@dataclass(frozen=True)
class CallResult:
    round_number: int
    case_id: str
    client: str
    elapsed_ms: int
    output_chars: int
    output_sha256: str | None
    parse_ok: bool
    input_kind: str | None
    error_type: str | None


def build_plan(repeats: int) -> tuple[PlannedCall, ...]:
    if repeats <= 0:
        raise ValueError("repeats必须是正整数。")
    calls: list[PlannedCall] = []
    for round_number in range(1, repeats + 1):
        for case_index, case in enumerate(CASES):
            clients = (
                ("direct_http", "openai_sdk")
                if (round_number + case_index) % 2
                else ("openai_sdk", "direct_http")
            )
            calls.extend(
                PlannedCall(round_number, case.case_id, client)
                for client in clients
            )
    return tuple(calls)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def request_fingerprint(case: ComparisonCase, max_tokens: int) -> dict[str, object]:
    user_prompt = build_unified_understanding_user_prompt(case.request())
    return {
        "case_id": case.case_id,
        "system_prompt_chars": len(UNIFIED_UNDERSTANDING_SYSTEM_PROMPT),
        "system_prompt_sha256": _sha256(UNIFIED_UNDERSTANDING_SYSTEM_PROMPT),
        "user_prompt_chars": len(user_prompt),
        "user_prompt_sha256": _sha256(user_prompt),
        "temperature": 0,
        "response_format": "json_object",
        "thinking": "disabled",
        "max_tokens": max_tokens,
        "max_attempts": 1,
    }


def _prompts(case: ComparisonCase) -> tuple[str, str]:
    return (
        UNIFIED_UNDERSTANDING_SYSTEM_PROMPT,
        build_unified_understanding_user_prompt(case.request()),
    )


def direct_http_call(case: ComparisonCase, *, settings, max_tokens: int) -> str:
    system_prompt, user_prompt = _prompts(case)
    client = OpenAICompatibleLLMClient(
        base_url=settings.base_url,
        api_key=settings.api_key,
        model=settings.model_name,
        timeout_seconds=LLM_TIMEOUT_SECONDS,
        max_tokens=max_tokens,
        max_attempts=1,
        retry_delay_seconds=0,
    )
    return client.generate_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    ).content


def openai_sdk_call(case: ComparisonCase, *, settings, max_tokens: int) -> str:
    from openai import OpenAI

    system_prompt, user_prompt = _prompts(case)
    client = OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=LLM_TIMEOUT_SECONDS,
        max_retries=0,
    )
    response = client.chat.completions.create(
        model=settings.model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=max_tokens,
        extra_body={"thinking": {"type": "disabled"}},
    )
    content = response.choices[0].message.content or ""
    if not content.strip():
        raise ValueError("模型返回了空内容。")
    return content


def run_one(
    planned: PlannedCall,
    *,
    settings,
    max_tokens: int,
    callers: dict[str, Callable[..., str]],
) -> CallResult:
    case = next(item for item in CASES if item.case_id == planned.case_id)
    started = time.perf_counter()
    content = ""
    try:
        content = callers[planned.client](
            case, settings=settings, max_tokens=max_tokens
        )
        understood = parse_unified_understanding(
            content,
            expected_raw_text=case.text,
            session_id="llm-client-comparison",
            segment_id=1,
        )
        return CallResult(
            planned.round_number,
            planned.case_id,
            planned.client,
            round((time.perf_counter() - started) * 1000),
            len(content),
            _sha256(content),
            True,
            understood.input_kind.value,
            None,
        )
    except Exception as error:
        return CallResult(
            planned.round_number,
            planned.case_id,
            planned.client,
            round((time.perf_counter() - started) * 1000),
            len(content),
            _sha256(content) if content else None,
            False,
            None,
            type(error).__name__,
        )


def summarize(results: Iterable[CallResult]) -> list[dict[str, object]]:
    items = tuple(results)
    summary: list[dict[str, object]] = []
    for client in ("direct_http", "openai_sdk"):
        selected = [item for item in items if item.client == client]
        successful = [item for item in selected if item.parse_ok]
        elapsed = [item.elapsed_ms for item in successful]
        summary.append({
            "client": client,
            "calls": len(selected),
            "parse_ok": len(successful),
            "failures": len(selected) - len(successful),
            "median_ms": round(median(elapsed)) if elapsed else None,
            "min_ms": min(elapsed) if elapsed else None,
            "max_ms": max(elapsed) if elapsed else None,
        })
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="同条件比较直接HTTP与OpenAI SDK客户端；默认不访问网络。"
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="真正发送人工测试文本；不传时只显示计划。",
    )
    parser.add_argument("--repeats", type=int, default=3, help="每个用例重复次数。")
    parser.add_argument(
        "--max-tokens", type=int, default=LLM_MAX_TOKENS, help="两端共同的输出上限。"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="结果文件；默认写入results/diagnostics。",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.repeats <= 0 or args.max_tokens <= 0:
        raise SystemExit("--repeats和--max-tokens必须是正整数。")

    plan = build_plan(args.repeats)
    settings = settings_store.current()
    print("LLM客户端同条件对照")
    print(f"模型：{settings.model_name or '未配置'}")
    print(f"测试：{len(CASES)}条人工文本 × {args.repeats}轮 × 2客户端 = {len(plan)}次")
    print("共同参数：temperature=0, thinking=disabled, "
          f"max_tokens={args.max_tokens}, max_attempts=1")
    print("请求指纹（不含密钥和完整提示词）：")
    print(json.dumps(
        [request_fingerprint(case, args.max_tokens) for case in CASES],
        ensure_ascii=False,
        indent=2,
    ))

    if not args.run:
        print("\nDRY_RUN：未访问网络。确认后使用 --run 才会发送以上人工文本。")
        return 0
    if not settings.is_ready():
        raise SystemExit("当前Web模型配置不完整，无法运行对照。")

    callers = {
        "direct_http": direct_http_call,
        "openai_sdk": openai_sdk_call,
    }
    results: list[CallResult] = []
    for index, planned in enumerate(plan, start=1):
        print(
            f"[{index}/{len(plan)}] 第{planned.round_number}轮 "
            f"{planned.case_id} / {planned.client}"
        )
        result = run_one(
            planned,
            settings=settings,
            max_tokens=args.max_tokens,
            callers=callers,
        )
        results.append(result)
        status = "OK" if result.parse_ok else f"FAIL({result.error_type})"
        print(f"  {status} {result.elapsed_ms}ms chars={result.output_chars}")

    report = {
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "model": settings.model_name,
        "base_url_host": settings.base_url.split("//", 1)[-1].split("/", 1)[0],
        "repeats": args.repeats,
        "max_tokens": args.max_tokens,
        "results": [asdict(item) for item in results],
        "summary": summarize(results),
    }
    output = args.output or (
        ROOT / "results" / "diagnostics"
        / f"llm_client_comparison_{datetime.now():%Y%m%d_%H%M%S}.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n汇总：")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"本地结果：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
