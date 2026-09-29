# -*- coding: utf-8 -*-
from __future__ import annotations

"""工具注册表与展示层：@tool 注册、openai_tools/call/names 统一分发。

由 lab_tools.py 的拆分生成：这是所有工具模块共享的注册中心。
"""

import json
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import domain
import llm_bridge
import settings_store
from record_service import RecordCommand, SharedRecordService
from time_engine import (
    generate_schedule, format_schedule_brief,
    get_remaining_schedule, format_remaining_brief,
    get_step_profile, get_next_passive_window,
    plan_multi_protocols, format_multi_protocol_brief,
    plan_clock_schedule,
)
from src.core.presentation_delivery import (
    PresentationDeliveryPlan,
    build_delivery_plan,
)
from src.core.rule_entity_extraction import extract_entities
from database.lab_record_store import (
    current_session_id,
    list_records,
    next_segment_id,
    save_record,
)
from database.crud import save_protocol_preference, get_protocol_preference

_REGISTRY: dict = {}


@dataclass(frozen=True)
class PresentedToolResult:
    """Tool payload plus its deterministic, backend-owned presentation plan."""

    payload: Mapping[str, object]
    presentation_plan: PresentationDeliveryPlan

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
        if not isinstance(self.presentation_plan, PresentationDeliveryPlan):
            raise TypeError("presentation_plan 必须是 PresentationDeliveryPlan。")

# 计时器（内存态，足够单机网页演示使用）
_timers: dict = {}
_timers_lock = threading.Lock()
_record_lock = threading.Lock()

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO_ROOT / "results"
STEP_IMPROVEMENTS_FILE = RESULTS_DIR / "step_improvements.jsonl"


def tool(name: str, description: str, parameters: dict,
         kind: str = "other", title: str = "", present=None,
         experiment_command: bool = False, artifact_type: str = ""):
    """把一个函数注册成模型可调用的工具。

    参考 deepseek-harness 的 presentCall/presentResult 范式：工具自己声明
    「这次调用在界面上长什么样」，UI 按统一词汇渲染卡片，不为每个工具写特例。

    kind  取 read / execute / search / other，决定卡片图标与配色。
    title 是卡片标题模板，可用 {参数名} 占位。
    present 可选，接收 (args, result) 返回卡片摘要行列表。
    artifact_type 可选，显式覆盖 artifact.type（默认由 kind 推导），用于
    让前端按统一语义渲染，而不是在每个界面按工具名写特例。
    """
    def wrapper(func):
        _REGISTRY[name] = {
            "name": name,
            "description": description,
            "parameters": parameters,
            "handler": func,
            "kind": kind,
            "title": title or name,
            "present": present,
            "experiment_command": bool(experiment_command),
            "artifact_type": str(artifact_type or "").strip(),
        }
        return func
    return wrapper


def _artifact_type(kind: str) -> str:
    """把工具类别映射成稳定的 artifact 语义类型，不绑定具体业务功能。"""
    return {
        "read": "lookup",
        "search": "search",
        "execute": "action",
    }.get(str(kind or ""), "result")


def _attach_artifact(
    view: dict,
    *,
    name: str,
    result: object = None,
    override_type: str = "",
) -> dict:
    """为每张工具卡片附加统一 artifact 合同。

    旧的 title/lines/ui_action 字段继续保留，保证老前端兼容；artifact 是
    后续各个 UI（聊天、实验画布、记录本）共同消费的新入口。
    """
    action = view.get("ui_action")
    view["artifact"] = {
        "version": 1,
        "type": override_type or _artifact_type(view.get("kind")),
        "tool": name,
        "title": view.get("title") or name,
        "status": view.get("status") or "pending",
        "summary": list(view.get("lines") or [])[:1],
        "lines": list(view.get("lines") or []),
        "actions": [action] if isinstance(action, dict) else [],
        "data": result if isinstance(result, (dict, list, str, int, float, bool)) else None,
    }
    return view


def present_call(name: str, arguments: dict) -> dict:
    """待执行卡片：模型刚决定调用、还没执行时显示。"""
    item = _REGISTRY.get(name)
    if item is None:
        return _attach_artifact(
            {"card": "generic", "kind": "other", "title": name, "status": "pending"},
            name=name,
        )
    title = item["title"]
    for key, value in (arguments or {}).items():
        title = title.replace("{" + key + "}", str(value))
    # 清除残留的 {占位符}，避免模板变量名泄漏到卡片标题。
    title = re.sub(r"\{[^}]+\}", "", title).strip()
    return _attach_artifact(
        {"card": "generic", "kind": item["kind"], "title": title,
         "raw_input": arguments or {}, "status": "pending"},
        name=name,
        override_type=item.get("artifact_type"),
    )


def present_result(name: str, arguments: dict, outcome: dict) -> dict:
    """完成卡片：执行后显示结果摘要，失败时显示错误。"""
    view = present_call(name, arguments)
    item = _REGISTRY.get(name) or {}
    override = item.get("artifact_type")
    if not outcome.get("ok"):
        view.update(status="error", lines=[str(outcome.get("error"))])
        return _attach_artifact(view, name=name, result=None, override_type=override)
    item = _REGISTRY.get(name) or {}
    presenter = item.get("present")
    lines = []
    if presenter:
        try:
            lines = presenter(arguments or {}, outcome.get("result"))
        except Exception:
            lines = []
    view.update(status="done", lines=lines or [])
    result = outcome.get("result")
    if isinstance(result, dict) and isinstance(result.get("ui_action"), dict):
        view["ui_action"] = result["ui_action"]
    # 列出方案/试剂库时直接打开对应卡片页，避免只给文字列表。
    if outcome.get("ok") and name == "list_protocols":
        view["ui_action"] = {"type": "navigate", "view": "protocols"}
    elif outcome.get("ok") and name == "list_reagent_preps":
        view["ui_action"] = {"type": "navigate", "view": "reagent_prep"}
    elif outcome.get("ok") and name == "get_reagent_prep":
        prep_id = (outcome.get("result") or {}).get("reagent_prep_id")
        view["ui_action"] = {"type": "open_reagent_prep", "id": prep_id}
    return _attach_artifact(view, name=name, result=result, override_type=override)


def openai_tools(*, experiment_commands_only: bool = False) -> list:
    """导出成 OpenAI function-calling 格式。"""
    return [
        {
            "type": "function",
            "function": {
                "name": item["name"],
                "description": item["description"],
                "parameters": item["parameters"],
            },
        }
        for item in _REGISTRY.values()
        if not experiment_commands_only or item["experiment_command"]
    ]


def call(name: str, arguments: dict) -> dict:
    """分发工具调用；未知工具与执行异常都返回结构化错误，不抛给主流程。"""
    item = _REGISTRY.get(name)
    if item is None:
        return {"ok": False, "error": "未注册的工具：" + str(name)}
    try:
        result = item["handler"](**(arguments or {}))
        if isinstance(result, PresentedToolResult):
            return {
                "ok": True,
                "result": dict(result.payload),
                "presentation_plan": result.presentation_plan,
            }
        return {"ok": True, "result": result}
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {error}"}


def names() -> list:
    return list(_REGISTRY.keys())


def experiment_command_names() -> frozenset[str]:
    """Return tools that explicitly opt in to addressed experiment commands."""

    return frozenset(
        name for name, item in _REGISTRY.items()
        if item["experiment_command"]
    )


def experiment_command_catalog(*, include_catalog_tool: bool = False) -> list[dict]:
    """Build the user-visible catalog from the same experiment permission facts."""

    return [
        {
            "name": name,
            "title": item["title"],
            "description": item["description"],
            "kind": item["kind"],
        }
        for name, item in _REGISTRY.items()
        if item["experiment_command"]
        and (include_catalog_tool or name != "list_experiment_commands")
    ]


