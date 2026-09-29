# -*- coding: utf-8 -*-
"""实验室能力工具集：每个能力自描述、自注册，模型可直接调用。

本文件是 facade：注册机制在 lab_tools_registry.py，
各功能区块拆分到 lab_tools_project / lab_tools_protocol / ... 等模块。
新增能力：在对应功能模块里加一个 @tool 即可。
"""

from __future__ import annotations

from lab_tools_registry import (
    _REGISTRY, tool, PresentedToolResult, _attach_artifact,
    present_call, present_result, openai_tools, call, names,
    experiment_command_names, experiment_command_catalog,
    domain, RecordCommand,
)

# 导入各功能模块，触发 @tool 注册
import lab_tools_project  # noqa: E402,F401
import lab_tools_protocol  # noqa: E402,F401
import lab_tools_record  # noqa: E402,F401
import lab_tools_time  # noqa: E402,F401
import lab_tools_reagent  # noqa: E402,F401
import lab_tools_kb  # noqa: E402,F401
import lab_tools_calc  # noqa: E402,F401
import lab_tools_storage  # noqa: E402,F401
import lab_tools_community  # noqa: E402,F401
import lab_tools_prep  # noqa: E402,F401

# 兼容旧测试/调用方：把部分内部符号重新暴露在 lab_tools 命名空间
from lab_tools_record import _build_record_service  # noqa: E402,F401

__all__ = [
    "tool", "PresentedToolResult", "_attach_artifact",
    "present_call", "present_result", "openai_tools", "call", "names",
    "experiment_command_names", "experiment_command_catalog",
    "domain", "RecordCommand", "_build_record_service",
]
