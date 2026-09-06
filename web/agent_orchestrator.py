# -*- coding: utf-8 -*-
"""实验助手的 Planner / Executor / Reflector 编排边界。

这是产品级 Agent 六层架构中的“编排层”落点：
  - Planner   : 判断当前请求该走“直接实验数据读取”还是“复杂后台 Agent”。
  - Executor  : 按计划执行，返回统一文本结果。
  - Reflector : 校验结果；失败有限重试后降级到人工兜底。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Callable, Mapping

logger = logging.getLogger(__name__)

_DIRECT_KEYWORDS = (
    "当前实验", "现在做到哪一步", "现在进行", "哪一步", "当前步骤",
    "可选实验方案", "有哪些方案", "实验方案列表", "当前方案",
    "这个实验用了什么", "这个实验的材料", "这个实验的计算",
    "我记过什么", "实验记忆",
)


@dataclass(frozen=True)
class Plan:
    kind: str  # "direct" | "assistant"
    detail: str = ""


@dataclass(frozen=True)
class ExecutionResult:
    ok: bool
    answer: str
    detail: str = ""
    attempts: int = 1


class Planner:
    """用轻量启发式规则做第一层路由；未来可换小模型路由。"""

    def plan(self, instruction: str) -> Plan:
        text = str(instruction or "")
        for keyword in _DIRECT_KEYWORDS:
            if keyword in text:
                return Plan(kind="direct", detail=keyword)
        return Plan(kind="assistant")


class Executor:
    """执行 Plan。direct 直接读领域数据；assistant 走后台 Chat/Turn。"""

    def __init__(
        self,
        *,
        domain=None,
        submit_assistant: Callable[[str], tuple[str, str]] | None = None,
    ) -> None:
        self._domain = domain
        self._submit_assistant = submit_assistant

    def execute(self, plan: Plan, instruction: str) -> ExecutionResult:
        if plan.kind == "direct":
            return self._execute_direct(instruction)
        return self._execute_assistant(instruction)

    def _execute_direct(self, instruction: str) -> ExecutionResult:
        domain = self._domain
        if domain is None:
            return ExecutionResult(False, "", "未配置领域读取能力")
        try:
            state = domain.session()
            if "方案" in instruction or "protocol" in instruction.lower():
                protocols = []
                for protocol in domain.protocols().list_all():
                    protocols.append({
                        "id": protocol.protocol_id,
                        "title": protocol.title,
                        "total_steps": len(protocol.steps),
                    })
                if protocols:
                    return ExecutionResult(True, json.dumps({
                        "type": "protocol_list",
                        "items": protocols,
                    }, ensure_ascii=False))
            view = domain.all_steps_view(state)
            step = view.get("step") or {}
            result = {
                "type": "current_experiment",
                "mode": view.get("mode"),
                "step": step,
                "all_steps": view.get("all_steps", []),
                "safety": view.get("safety", []),
            }
            return ExecutionResult(True, json.dumps(result, ensure_ascii=False))
        except Exception as error:  # noqa: BLE001
            logger.exception("executor_direct_failed")
            return ExecutionResult(False, "", str(error))

    def _execute_assistant(self, instruction: str) -> ExecutionResult:
        if self._submit_assistant is None:
            return ExecutionResult(False, "", "未配置后台 Agent")
        try:
            answer, conversation_id = self._submit_assistant(instruction)
            return ExecutionResult(True, answer)
        except Exception as error:  # noqa: BLE001
            logger.exception("executor_assistant_failed")
            return ExecutionResult(False, "", str(error))


class Reflector:
    """校验结果；失败可重试一次，仍失败则人工兜底。"""

    def __init__(self, *, max_attempts: int = 2) -> None:
        self.max_attempts = max_attempts

    def run(self, plan: Plan, instruction: str, executor: Executor) -> ExecutionResult:
        last: ExecutionResult | None = None
        for attempt in range(self.max_attempts):
            last = executor.execute(plan, instruction)
            if last.ok and last.answer:
                return last
            if attempt < self.max_attempts - 1:
                logger.warning("reflector_retry attempt=%s detail=%s", attempt + 1, last.detail)
        return ExecutionResult(
            False,
            "后台处理暂时不可用，请稍后重试或到实验本查看。",
            last.detail if last else "",
            attempts=self.max_attempts,
        )


def create_default_orchestrator(*, domain=None, submit_assistant=None):
    """装配默认编排层。"""
    planner = Planner()
    executor = Executor(domain=domain, submit_assistant=submit_assistant)
    reflector = Reflector()
    return planner, executor, reflector
