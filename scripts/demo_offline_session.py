"""离线会话演示：用真实模块跑通一次实验记录对话。

不需要麦克风、ASR模型或网络。
ASR原文用固定文本代替，LLM用脚本化假客户端代替，
其余全部是项目真实代码：统一理解合同解析、意图命令解析、
待确认问题协调器。
"""

from __future__ import annotations

import json

from src.core.interaction_command import (
    InteractionCommandParser,
    InteractionCommandType,
)
from src.core.reply_coordinator import ReplyCoordinator
from src.core.unified_understanding import (
    UnifiedInputKind,
    UnifiedUnderstandingInput,
)
from src.llm.client import LLMClientError, LLMGenerationResult
from src.llm.unified_processor import UnifiedUnderstandingProcessor


SESSION_ID = "demo_20260811"


def experiment_payload(raw, normalized, entities, missing=(), question=None):
    full = {
        "action": None, "object": None, "instrument": None,
        "amount_value": None, "amount_unit": None, "concentration": None,
        "temperature": None, "duration": None,
        "condition": None, "observation": None,
    }
    full.update(entities)
    return {
        "input_kind": "experiment",
        "experiment": {"analysis": {
            "events": [{
                "event_type": "operation",
                "raw_text": raw,
                "normalized_text": normalized,
                "entities": full,
                "missing_fields": list(missing),
                "needs_confirmation": False,
                "confirmation_reason": None,
            }],
            "should_ask_follow_up": bool(missing),
            "follow_up_question": question,
            "assistant_reply": None if missing else "已记录。",
        }},
        "control": None,
        "uncertain": None,
    }


def control_payload(command_type):
    return {
        "input_kind": "control",
        "experiment": None,
        "control": {"intent": {
            "status": "matched",
            "command_type": command_type,
            "target_question_number": None,
            "answer_text": None,
            "reason": None,
        }},
        "uncertain": None,
    }


SCRIPT = {
    "加入五毫升缓冲液并搅拌。": experiment_payload(
        "加入五毫升缓冲液并搅拌。", "加入5毫升缓冲液并搅拌。",
        {"action": "加入并搅拌", "object": "缓冲液",
         "amount_value": "5", "amount_unit": "毫升"},
    ),
    "将溶液加热。": experiment_payload(
        "将溶液加热。", "将溶液加热。",
        {"action": "加热", "object": "溶液"},
        missing=("temperature", "duration"),
        question="请问加热的目标温度是多少？需要加热多长时间？",
    ),
    "加热到六十摄氏度，保持十分钟。": experiment_payload(
        "加热到六十摄氏度，保持十分钟。", "加热到60摄氏度，保持10分钟。",
        {"action": "加热", "object": "溶液",
         "temperature": "60摄氏度", "duration": "10分钟"},
    ),
    "查看待确认问题。": control_payload("review_pending"),
    "今天先记录到这里吧。": control_payload("end_session"),
}


class ScriptedLLMClient:
    """按原文返回固定响应，代替真实 DeepSeek 调用。"""

    def generate_json(self, *, system_prompt, user_prompt):
        for raw_text, payload in SCRIPT.items():
            if raw_text in user_prompt:
                return LLMGenerationResult(
                    content=json.dumps(payload, ensure_ascii=False),
                    attempts=1,
                    processing_seconds=0.42,
                )
        # 演示外的文本一律当作网络故障，用来展示降级路径。
        raise LLMClientError(
            "模拟网络超时", attempts=2, processing_seconds=30.0
        )


def main() -> None:
    processor = UnifiedUnderstandingProcessor(ScriptedLLMClient())
    coordinator = ReplyCoordinator()
    command_parser = InteractionCommandParser()

    print("=" * 62)
    print("  实验语音智能体 · 离线会话演示")
    print("  (唤醒词=小科小科；此处用文本代替麦克风与ASR)")
    print("=" * 62)
    print("\n[唤醒成功：小科小科]  会话开始\n")

    spoken = [
        "加入五毫升缓冲液并搅拌。",
        "将溶液加热。",
        "加热到六十摄氏度，保持十分钟。",
        "查看待确认问题。",
        "今天先记录到这里吧。",
        "这段用来演示网络故障。",
    ]

    for segment_id, raw_text in enumerate(spoken, start=1):
        print(f"── 第{segment_id}段 ──────────────────────────────")
        print(f"你说：{raw_text}")

        # 1. 先走本地精确命令快路径，命中就不调用LLM
        local = command_parser.parse(raw_text)
        if (
            local is not None
            and local.command_type is not None
            and local.command_type is not InteractionCommandType.NORMAL
        ):
            print(
                f"  [本地快路径] 精确命中控制命令 "
                f"{local.command_type.value}，本可跳过LLM"
            )

        outcome = processor.understand(UnifiedUnderstandingInput(
            raw_text=raw_text,
            session_active=True,
            session_id=SESSION_ID,
            segment_id=segment_id,
        ))
        result = outcome.value

        print(f"  [统一理解] 分支={result.input_kind.value}"
              f"  降级={outcome.degraded}"
              f"  耗时={outcome.llm_processing_seconds:.2f}s")

        if result.input_kind is UnifiedInputKind.EXPERIMENT:
            analysis = result.experiment.analysis
            for event in analysis.events:
                filled = {k: v for k, v in vars(event.entities).items() if v}
                print(f"  [结构化事件] {event.event_type.value} → {filled}")
                if event.missing_fields:
                    print(f"  [缺失字段] {tuple(event.missing_fields)}")
            coordinator.ingest_analysis(
                segment_id=segment_id,
                raw_text=raw_text,
                analysis=analysis,
            )
        elif result.input_kind is UnifiedInputKind.CONTROL:
            intent = result.control.intent
            print(f"  [控制命令] {intent.command_type.value}")

        reply = coordinator.pop_next_reply()
        if reply is not None:
            print(f"\n  🔊 助手追问：{reply.text}")
        print()

    print("── 会话结束 ──────────────────────────────")
    active = [c for c in coordinator.snapshot() if c.is_active] \
        if hasattr(coordinator, "snapshot") else []
    print(f"仍未解决的待确认问题：{len(active)} 条")
    print("\n说明：以上事件在真实运行时会落盘到 results/*.jsonl。")


if __name__ == "__main__":
    main()
