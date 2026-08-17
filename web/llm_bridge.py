# -*- coding: utf-8 -*-
"""把网页端运行时设置接到 src 已验证的 LLM 处理链上。

不重写提示词与解析：src/llm/processor.py 的严格校验、保真降级、
实体合同都已有测试覆盖，这里只提供一个符合 LLMClient 协议的客户端，
让它改用网页设置里的密钥、地址和模型。
"""

from __future__ import annotations

import json
import time

import domain  # noqa: F401  确保仓库根目录已在 sys.path
import settings_store
from src.llm.client import LLMClientError, LLMGenerationResult
from src.llm.processor import ExperimentLLMProcessor


class WebSettingsLLMClient:
    """满足 src.llm.client.LLMClient 协议，配置来自网页设置。"""

    def __init__(self, max_attempts: int = 2, timeout_seconds: float = 45.0) -> None:
        self.max_attempts = max_attempts
        self.timeout_seconds = timeout_seconds

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> LLMGenerationResult:
        settings = settings_store.current()
        if not settings.is_ready():
            raise LLMClientError(
                "尚未配置模型：" + "；".join(settings.missing()),
                attempts=0,
                processing_seconds=0.0,
            )

        from openai import OpenAI

        client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=self.timeout_seconds,
            max_retries=0,
        )

        started = time.monotonic()
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = client.chat.completions.create(
                    model=settings.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0,
                )
                content = response.choices[0].message.content or ""
                return LLMGenerationResult(
                    content=content,
                    attempts=attempt,
                    processing_seconds=time.monotonic() - started,
                )
            except Exception as error:
                last_error = error
                if attempt >= self.max_attempts:
                    break
                time.sleep(0.5)

        raise LLMClientError(
            f"{type(last_error).__name__}: {last_error}",
            attempts=self.max_attempts,
            processing_seconds=time.monotonic() - started,
        )


_processor: ExperimentLLMProcessor | None = None


def processor() -> ExperimentLLMProcessor:
    global _processor
    if _processor is None:
        _processor = ExperimentLLMProcessor(client=WebSettingsLLMClient())
    return _processor


def extract(transcript: str, session_id: str, segment_id: int) -> dict:
    """把一段口述转成结构化实体；失败时保真降级为未分类记录。"""
    outcome = processor().analyze_segment(
        raw_text=transcript,
        session_id=session_id,
        segment_id=segment_id,
    )
    analysis = outcome.value
    events = []
    for event in analysis.events:
        events.append({
            "event_type": event.event_type.value,
            "raw_text": event.raw_text,
            "normalized_text": event.normalized_text,
            "entities": {
                name: getattr(event.entities, name)
                for name in event.entities.__dataclass_fields__
            },
            "needs_confirmation": event.needs_confirmation,
            "confirmation_reason": event.confirmation_reason,
        })
    return {
        "events": events,
        "degraded": outcome.degraded,
        "error": outcome.error,
        "llm_attempts": outcome.llm_attempts,
        "llm_seconds": round(outcome.llm_processing_seconds, 2),
        "assistant_reply": analysis.assistant_reply,
    }


def generate_protocol_draft(description: str) -> dict:
    """用 LLM 生成一份实验方案草稿（不落盘，由前端让用户确认后再保存）。"""
    client = WebSettingsLLMClient()
    system_prompt = (
        "你是实验方案编写助手。请根据用户描述生成一份完整实验方案，只输出 JSON，不要 Markdown，不要解释。"
        "JSON 结构必须是："
        '{"protocol_id":"英文短横线id","title":"方案标题","source":"AI生成草稿","version":"1.0","schema_version":1,'
        '"steps":[{"step_number":1,"title":"步骤标题","instruction":"步骤说明","protocol_values":{"字段名":"值"},'
        '"must_record":["字段名"],"terms":["术语"],"hazard_note":"安全提示或null","field_prompts":{"字段名":"追问话术"}}]}'
        "步骤至少 2 步，字段名只能使用：action, object, amount_value, amount_unit, concentration, temperature, duration, condition, observation, instrument。"
    )
    result = client.generate_json(
        system_prompt=system_prompt,
        user_prompt=description,
    )
    try:
        return json.loads(result.content)
    except json.JSONDecodeError as error:
        raise ValueError(f"AI 返回的不是合法 JSON：{error}") from error


def generate_reagent_prep_draft(description: str) -> dict:
    """用 LLM 生成一条试剂配置草稿（不落盘，确认后才保存）。"""

    client = WebSettingsLLMClient()
    system_prompt = (
        "你是实验室试剂配制助手。请根据用户描述生成一条试剂配制方案，只输出 JSON，不要 Markdown，不要解释。"
        "JSON 结构必须是："
        '{"reagent_prep_id":"英文短横线id","name_zh":"试剂中文名","purpose":"用途",'
        '"target_concentration":"目标浓度或null","target_volume":"目标体积或null","solvent":"溶剂或null",'
        '"steps":["步骤1","步骤2"],"storage_condition":"保存条件或null","expiry":"有效期或null",'
        '"hazard_reagents":["涉及危险试剂中文名"],"source":"AI生成草稿","source_url":null,'
        '"review_status":"UNREVIEWED"}'
        "步骤至少 2 步。"
    )
    result = client.generate_json(
        system_prompt=system_prompt,
        user_prompt=description,
    )
    try:
        return json.loads(result.content)
    except json.JSONDecodeError as error:
        raise ValueError(f"AI 返回的不是合法 JSON：{error}") from error
