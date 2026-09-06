# -*- coding: utf-8 -*-
"""Agent Loop / Harness：多工具循环 + 上下文引擎 + 多智能体路由。

对应 OpenClaw 的：
- context engine：组装系统提示、记忆、任务上下文
- embedded agent runner：模型可以多轮调用工具，直到给出最终答复
- multi-agent routing：按任务类型选择不同的子智能体（heartbeat/reflection/...）
"""

from __future__ import annotations

import json
from typing import Callable

import httpx
import settings_store
from openai import OpenAI
from settings_store import current as current_settings


class AgentContextEngine:
    """上下文引擎：把记忆、任务、工具说明组装成 messages。"""

    def __init__(self) -> None:
        self._memory = ""

    def load_memory(self) -> None:
        from database.crud import list_memories
        try:
            memories = list_memories()
            if memories:
                self._memory = "\n".join(
                    f"- [{item.get('category') or 'general'}] {item.get('content')}"
                    for item in memories
                )
            else:
                self._memory = "当前没有长期记忆。"
        except Exception:
            self._memory = "记忆读取失败。"

    def assemble(
        self,
        *,
        system_prompt: str,
        user_text: str,
        extra_context: str | None = None,
        task_kind: str = "general",
    ) -> list[dict]:
        self.load_memory()
        system_parts = [
            system_prompt,
            "",
            "【长期记忆】",
            self._memory,
        ]
        if extra_context:
            system_parts += ["", "【当前上下文】", extra_context]
        content = user_text
        if task_kind == "heartbeat":
            content = f"[OpenClaw heartbeat poll]\n\n{user_text}"
        elif task_kind == "reflection":
            content = f"[OpenClaw reflection poll]\n\n{user_text}"
        return [
            {"role": "system", "content": "\n".join(system_parts)},
            {"role": "user", "content": content},
        ]


class EmbeddedAgentRunner:
    """嵌入式 Agent Runner：模型可多轮调用工具，直到最终答复。"""

    def __init__(self, max_steps: int = 6) -> None:
        self.max_steps = max_steps

    def _client(self) -> OpenAI:
        s = settings_store.current()
        if not s.api_key:
            raise ValueError("尚未配置模型密钥。")
        return OpenAI(
            api_key=s.api_key,
            base_url=s.base_url,
            timeout=httpx.Timeout(60, connect=10),
            max_retries=3,
            http_client=httpx.Client(trust_env=False),
        )

    def _extra_body(self) -> dict:
        s = current_settings()
        if s.voice_disable_thinking:
            return {"thinking": {"type": "disabled"}}
        if s.thinking_level == "disabled":
            return {"thinking": {"type": "disabled"}}
        if s.thinking_level == "low":
            return {"reasoning_effort": "low", "thinking": {"type": "enabled"}}
        if s.thinking_level == "medium":
            return {"reasoning_effort": "medium", "thinking": {"type": "enabled"}}
        if s.thinking_level == "high":
            return {"reasoning_effort": "high", "thinking": {"type": "enabled"}}
        # auto：不强制，交给模型/服务商决定
        return {}

    def run(
        self,
        *,
        system_prompt: str,
        user_text: str,
        tools: dict[str, dict],
        extra_context: str | None = None,
        task_kind: str = "general",
        terminal_tools: set[str] | None = None,
    ) -> dict:
        """执行 Agent Loop。

        tools: name -> {"schema": {...}, "execute": Callable[[dict], str]}
        terminal_tools: 调用后直接结束循环的工具名（如 heartbeat_respond）。
        """
        context_engine = AgentContextEngine()
        messages = context_engine.assemble(
            system_prompt=system_prompt,
            user_text=user_text,
            extra_context=extra_context,
            task_kind=task_kind,
        )
        client = self._client()
        terminal = terminal_tools or set()
        openai_tools = [
            {"type": "function", "function": spec["schema"]}
            for spec in tools.values()
        ]

        for step in range(self.max_steps):
            response = client.chat.completions.create(
                model=current_settings().model_name,
                messages=messages,
                tools=openai_tools or None,
                extra_body=self._extra_body(),
            )
            message = response.choices[0].message
            tool_calls = message.tool_calls or []

            if not tool_calls:
                return {
                    "finished": True,
                    "steps": step + 1,
                    "text": (message.content or "").strip(),
                    "tool_results": [],
                }

            # 终端工具：执行后直接返回结果（OpenClaw heartbeat_respond 语义）。
            if len(tool_calls) == 1 and tool_calls[0].function.name in terminal:
                args = _parse_args(tool_calls[0].function.arguments)
                name = tool_calls[0].function.name
                result = tools[name]["execute"](args)
                return {
                    "finished": True,
                    "steps": step + 1,
                    "terminal_tool": name,
                    "args": args,
                    "result": result,
                    "tool_results": [result],
                }

            # 普通工具：执行并把结果追加回对话，让模型继续。
            messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            })
            for tc in tool_calls:
                name = tc.function.name
                if name not in tools:
                    output = f"错误：未知工具 {name}"
                else:
                    try:
                        args = _parse_args(tc.function.arguments)
                        output = tools[name]["execute"](args)
                    except Exception as error:
                        output = f"工具执行失败：{error}"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": output if isinstance(output, str) else json.dumps(output, ensure_ascii=False),
                })

        return {
            "finished": False,
            "steps": self.max_steps,
            "text": "Agent 步数达到上限，未给出最终答复。",
            "tool_results": [],
        }


class MultiAgentRouter:
    """多智能体路由：按任务类型选择子智能体。"""

    AGENTS = {
        "heartbeat": {
            "label": "心跳监控",
            "system_prompt": (
                "你是实验助手的心跳监控器。你可以调用工具查看今日计划、库存、记录，"
                "最后必须调用 heartbeat_respond 决定是否打扰用户。"
                "没有需要用户注意的事时 notify=false；有则 notify=true 并给出简短 notificationText。"
            ),
        },
        "reflection": {
            "label": "晚间反思",
            "system_prompt": (
                "你是实验助手的晚间反思器。你可以调用工具查看今天的实验记录、计划、库存，"
                "最后必须调用 reflection_respond 决定是否生成反思。"
                "今天没有实验内容时 notify=false；有则 notify=true 并给出反思和明日建议。"
            ),
        },
        "planner": {
            "label": "实验规划",
            "system_prompt": "你是实验规划师，负责把实验目标拆成可执行的方案与准备清单。",
        },
        "experimenter": {
            "label": "实验执行",
            "system_prompt": "你是实验执行助手，负责按方案推进步骤、记录操作、提醒安全。",
        },
        "general": {
            "label": "通用助手",
            "system_prompt": "你是实验助手，负责正常聊天、查询和解释。",
        },
    }

    @classmethod
    def route(cls, task_kind: str) -> dict:
        return cls.AGENTS.get(task_kind, cls.AGENTS["general"])


def _parse_args(raw: str | None) -> dict:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
