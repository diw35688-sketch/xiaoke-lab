# -*- coding: utf-8 -*-
"""把网页端运行时设置接到 src 已验证的统一理解链上。

不重写提示词与解析：src/llm/unified_processor.py 的严格校验、保真降级、
统一理解合同都已有测试覆盖，这里只提供一个符合 LLMClient 协议的客户端，
让它改用网页设置里的密钥、地址和模型。

统一链一次调用同时分辨 input_kind（experiment/control/uncertain）并结构化；
web 只消费 experiment 分支的实体卡片，control/uncertain 只带回标签，
由前端提示，不执行任何控制动作。
"""

from __future__ import annotations

import json

from text_clean import clean_text

import domain  # noqa: F401  确保仓库根目录已在 sys.path
import settings_store
from src.core.unified_understanding import (
    UnifiedInputKind,
    UnifiedUnderstandingInput,
)
from src.llm.client import (
    LLMClientError,
    LLMGenerationResult,
    OpenAICompatibleLLMClient,
)
from src.llm.unified_processor import UnifiedUnderstandingProcessor


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

        # 网页端之前单独使用 openai/httpx，连接失败只剩一个笼统的
        # APIConnectionError，而且没有复用 src 客户端的网络错误分类。
        # 统一使用已验证的兼容客户端：连接/超时/429/5xx 会有限重试，
        # 最终错误还会保留尝试次数和耗时，供降级日志定位。
        client = OpenAICompatibleLLMClient(
            base_url=settings.base_url,
            api_key=settings.api_key,
            model=settings.model_name,
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
            retry_delay_seconds=0.5,
        )
        return client.generate_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )


_processor: UnifiedUnderstandingProcessor | None = None


def processor() -> UnifiedUnderstandingProcessor:
    global _processor
    if _processor is None:
        _processor = UnifiedUnderstandingProcessor(client=WebSettingsLLMClient())
    return _processor


def _event_view(event) -> dict:
    """把一张 ExperimentEvent 卡片转成前端可用的字典。"""
    return {
        "event_type": event.event_type.value,
        "raw_text": event.raw_text,
        "normalized_text": event.normalized_text,
        "entities": {
            name: getattr(event.entities, name)
            for name in event.entities.__dataclass_fields__
        },
        "missing_fields": list(event.missing_fields),
        "needs_confirmation": event.needs_confirmation,
        "confirmation_reason": event.confirmation_reason,
    }


def extract(
    transcript: str,
    session_id: str,
    segment_id: int,
    recent_context: tuple[str, ...] = (),
) -> dict:
    """把一段口述送进统一理解链；失败时保真降级为未分类记录。

    recent_context 是最近几条口述原文，供模型理解指代；
    web 没有"待确认问题编号"机制，因此编号上下文固定为空。
    """
    request = UnifiedUnderstandingInput(
        raw_text=transcript,
        session_active=True,
        session_id=session_id,
        segment_id=segment_id,
        recent_context=tuple(
            text.strip() for text in recent_context if text and text.strip()
        ),
        pending_question_numbers=(),
        current_question_number=None,
    )
    outcome = processor().understand(request)
    result = outcome.value
    if result.experiment is not None:
        analysis = result.experiment.analysis
        events = [_event_view(event) for event in analysis.events]
        should_ask_follow_up = analysis.should_ask_follow_up
        follow_up_question = analysis.follow_up_question
        assistant_reply = analysis.assistant_reply
    else:
        # control / uncertain：web 不执行动作，只带回标签，不产生实体卡片
        events = []
        should_ask_follow_up = False
        follow_up_question = None
        assistant_reply = None
    return {
        "events": events,
        "input_kind": result.input_kind.value,
        "degraded": outcome.degraded,
        "error": outcome.error,
        "llm_attempts": outcome.llm_attempts,
        "llm_seconds": round(outcome.llm_processing_seconds, 2),
        "should_ask_follow_up": should_ask_follow_up,
        "follow_up_question": follow_up_question,
        "assistant_reply": assistant_reply,
    }


_ALLOWED_STEP_FIELDS = frozenset({
    "action", "object", "amount_value", "amount_unit",
    "concentration", "temperature", "duration", "condition",
    "observation", "instrument",
})


def _sanitize_protocol_draft(draft: dict) -> dict:
    """清除 LLM 草稿里不合规的字段名和空值，防止 add_protocol 抛 ProtocolError。

    LLM 经常无视字段名约束，在 must_record / protocol_values / field_prompts
    里塞中文键或空值，或者把同一个字段同时放进 protocol_values 和 field_prompts
    （合同禁止：已有值就不需要追问），导致整个工具调用失败。
    Agent 拿到报错后就会陷入"要不要重新创建"的确认死循环。
    """
    for step in draft.get("steps", []):
        # must_record: 只保留合法字段名、去重
        mr = step.get("must_record")
        if isinstance(mr, list):
            seen = set()
            cleaned = []
            for v in mr:
                if isinstance(v, str) and v in _ALLOWED_STEP_FIELDS and v not in seen:
                    seen.add(v)
                    cleaned.append(v)
            step["must_record"] = cleaned
        else:
            step["must_record"] = []
        must_record_set = set(step["must_record"])

        # terms: 只保留非空字符串
        terms = step.get("terms")
        if isinstance(terms, list):
            step["terms"] = [v for v in terms if isinstance(v, str) and v.strip()]
        else:
            step["terms"] = []

        # protocol_values: 只保留合法键 + 非空值
        pv = step.get("protocol_values")
        if isinstance(pv, dict):
            step["protocol_values"] = {
                k: v for k, v in pv.items()
                if k in _ALLOWED_STEP_FIELDS and isinstance(v, str) and v.strip()
            }
        else:
            step["protocol_values"] = {}
        pv_set = set(step["protocol_values"].keys())

        # field_prompts: 合法键 + 非空值 + 必须在 must_record 里 + 不能已在 protocol_values 里
        fp = step.get("field_prompts")
        if isinstance(fp, dict):
            step["field_prompts"] = {
                k: v for k, v in fp.items()
                if k in _ALLOWED_STEP_FIELDS
                and isinstance(v, str) and v.strip()
                and k in must_record_set
                and k not in pv_set
            }
        else:
            step["field_prompts"] = {}
    return draft


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
    # 第一轮：直接用用户描述生成。
    result = client.generate_json(
        system_prompt=system_prompt,
        user_prompt=description,
    )
    try:
        return _sanitize_protocol_draft(clean_text(json.loads(result.content)))
    except (json.JSONDecodeError, ValueError):
        pass  # 降级重试

    # 第二轮：补全上下文后重试——解决描述太短导致 LLM 返回非法 JSON 的问题。
    enriched = (
        f"请根据以下描述生成一份完整实验方案（如果信息不足，按该实验的标准流程补齐）：\n{description}"
    )
    result = client.generate_json(
        system_prompt=system_prompt,
        user_prompt=enriched,
    )
    try:
        return _sanitize_protocol_draft(clean_text(json.loads(result.content)))
    except json.JSONDecodeError as error:
        raise ValueError(f"AI 返回的不是合法 JSON：{error}") from error


def generate_protocol_edit_draft(protocol_json: dict, instruction: str) -> dict:
    """根据当前方案上下文和用户修改要求，生成修订后的完整方案 JSON。"""

    client = WebSettingsLLMClient()
    system_prompt = (
        "你是实验方案修订助手。用户会给你一份现有实验方案和修改要求。"
        "请返回一份完整修订后的实验方案 JSON，不要 Markdown，不要解释。"
        "要求：protocol_id 保持不变；只修改用户要求的部分，其他步骤尽量保留；"
        "如果用户要新增步骤，在合适位置插入并重新编号。"
        "JSON 结构必须与现有方案完全一致："
        '{"protocol_id":"英文短横线id","title":"方案标题","source":"AI修订草稿","version":"1.0","schema_version":1,'
        '"steps":[{"step_number":1,"title":"步骤标题","instruction":"步骤说明","protocol_values":{"字段名":"值"},'
        '"must_record":["字段名"],"terms":["术语"],"hazard_note":"安全提示或null",'
        '"field_prompts":{"字段名":"追问话术"}}]}'
        "字段名只能使用：action, object, amount_value, amount_unit, concentration, "
        "temperature, duration, condition, observation, instrument。"
    )
    user_prompt = (
        "当前方案 JSON：\n" + json.dumps(protocol_json, ensure_ascii=False, indent=2)
        + "\n\n用户修改要求：\n" + instruction
    )
    result = client.generate_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    try:
        return clean_text(json.loads(result.content))
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
        return clean_text(json.loads(result.content))
    except json.JSONDecodeError as error:
        raise ValueError(f"AI 返回的不是合法 JSON：{error}") from error


def generate_reagent_prep_from_web_text(
    *,
    page_title: str,
    page_text: str,
    source_url: str,
) -> dict:
    """从抓取的网页正文提取/整理一条试剂配制方案。

    与 generate_reagent_prep_draft 不同：必须依据网页正文，不允许编造步骤；
    来源字段会由调用方强制覆盖为「网络检索（临时）」，source_url 保留真实网址。
    """
    client = WebSettingsLLMClient()
    system_prompt = (
        "你是实验室试剂配制助手。下面给你一个从互联网抓取的网页标题和正文，"
        "请从正文中提取/整理该网页描述的试剂配制方法。\n"
        "硬性要求：\n"
        "1. 只能使用网页正文里实际出现的信息；正文没有的浓度、体积、步骤不要编造，"
        "  无法确定就填 null 或省略。\n"
        "2. 只输出 JSON，不要 Markdown，不要解释。\n"
        "3. JSON 结构必须是："
        '{"name_zh":"试剂中文名","purpose":"用途",'
        '"target_concentration":"目标浓度或null","target_volume":"目标体积或null","solvent":"溶剂或null",'
        '"steps":["步骤1","步骤2"],"storage_condition":"保存条件或null","expiry":"有效期或null",'
        '"hazard_reagents":["涉及危险试剂中文名"],"source":"网络检索（临时）",'
        '"source_url":"' + source_url.replace('"', '\\"') + '",'
        '"review_status":"UNREVIEWED"}\n'
        "步骤至少 2 步；如果正文太短或根本不是配方，输出 {\"error\":\"该网页没有可提取的完整配方信息\"}。"
    )
    user_prompt = f"网页标题：{page_title}\n\n网页正文：\n{page_text[:6000]}"
    result = client.generate_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    try:
        return clean_text(json.loads(result.content))
    except json.JSONDecodeError as error:
        raise ValueError(f"AI 返回的不是合法 JSON：{error}") from error


def generate_prep_bench_draft(
    *,
    protocol_title: str,
    step_text: str,
    reagent_items: list[dict],
    scale_input: str | None,
) -> dict:
    """让 AI 推断实验的计量方式、默认规模，并为每个试剂项推断用量/耗时/时效。

    只做"推理"：计量方式靠它判断，用量靠它估算，耗时/时效靠它推断。
    "要什么"由 checklist_service 的规则层决定，不在这里重复。
    返回纯草稿，不落盘。
    """

    client = WebSettingsLLMClient(max_attempts=1, timeout_seconds=30.0)
    system_prompt = (
        "你是实验室准备台助手。用户会给你一份实验方案的步骤文本和已抽取的试剂清单。"
        "请据此推断这份实验的计量方式、推荐默认规模，并为每个试剂估算本次用量、"
        "配制耗时和时效要求。只输出 JSON，不要 Markdown，不要解释。\n\n"
        "你要回答的核心问题——这个实验的用量自然按什么变量缩放：\n"
        "- 配缓冲液/培养基/溶液 → 按「总体积 mL 或 L」\n"
        "- PCR、ELISA、加样 → 按「反应数 / 样本数」\n"
        "- 细胞培养 → 按「培养面积 / 细胞数」\n"
        "- Western blot → 按「胶数 / 膜数」\n"
        "- 提取、纯化 → 按「样本数」\n\n"
        "JSON 结构必须是：\n"
        '{"scale_unit":"自然计量单位（如 总体积 mL / 样本数 / 反应数）",'
        '"scale_basis":"为什么这么判断（一句话）",'
        '"default_scale":"推荐默认规模（如 500 mL / 96 个样本 / 8 块胶）",'
        '"items":[{"id":0,"quantity":"按默认规模估算的本次用量（如 500 mL / 60.5 g）",'
        '"estimated_minutes":10,"time_sensitivity":"normal"}]}\n\n'
        "time_sensitivity 只能是：normal（普通）/ prechill（需预冷）/ overnight（需过夜）/"
        "fresh（现配现用）。\n"
        "estimated_minutes 只对需要现配的试剂填整数分钟，现成可用的填 null。"
    )
    payload = {
        "protocol_title": protocol_title,
        "scale_input": scale_input,
        "reagent_items": reagent_items,
    }
    result = client.generate_json(
        system_prompt=system_prompt,
        user_prompt=step_text + "\n\n" + json.dumps(payload, ensure_ascii=False),
    )
    try:
        return clean_text(json.loads(result.content))
    except json.JSONDecodeError as error:
        raise ValueError(f"AI 返回的不是合法 JSON：{error}") from error
