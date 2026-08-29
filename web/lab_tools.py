# -*- coding: utf-8 -*-
"""实验室能力工具集：每个能力自描述、自注册，模型可直接调用。

参考 deepseek-harness 的「everything is a plugin」范式：
能力 = 名称 + 用途说明 + 参数 schema + 处理函数，集中注册、统一分发，
而不是把工具定义硬编码在调用处。新增能力只需在此文件加一个 @tool。

安全边界：
- 只读类工具（查安全、查步骤）可直接执行。
- 会改变会话状态的工具（切方案、推进步骤）也执行，但结果回传给用户可见。
- 任何工具都不写业务文件、不产生不可撤销副作用。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import domain
import llm_bridge
import settings_store
from record_service import RecordCommand, SharedRecordService
from src.core.presentation_delivery import (
    PresentationDeliveryPlan,
    build_delivery_plan,
)
from src.core.rule_entity_extraction import extract_entities
from datetime import datetime, timedelta
import threading
import uuid

from database.lab_record_store import (
    current_session_id,
    list_records,
    next_segment_id,
    save_record,
)

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
         experiment_command: bool = False):
    """把一个函数注册成模型可调用的工具。

    参考 deepseek-harness 的 presentCall/presentResult 范式：工具自己声明
    「这次调用在界面上长什么样」，UI 按统一词汇渲染卡片，不为每个工具写特例。

    kind  取 read / execute / search / other，决定卡片图标与配色。
    title 是卡片标题模板，可用 {参数名} 占位。
    present 可选，接收 (args, result) 返回卡片摘要行列表。
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
        }
        return func
    return wrapper


def present_call(name: str, arguments: dict) -> dict:
    """待执行卡片：模型刚决定调用、还没执行时显示。"""
    item = _REGISTRY.get(name)
    if item is None:
        return {"card": "generic", "kind": "other", "title": name, "status": "pending"}
    title = item["title"]
    for key, value in (arguments or {}).items():
        title = title.replace("{" + key + "}", str(value))
    return {"card": "generic", "kind": item["kind"], "title": title,
            "raw_input": arguments or {}, "status": "pending"}


def present_result(name: str, arguments: dict, outcome: dict) -> dict:
    """完成卡片：执行后显示结果摘要，失败时显示错误。"""
    view = present_call(name, arguments)
    if not outcome.get("ok"):
        view.update(status="error", lines=[str(outcome.get("error"))])
        return view
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
    return view


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


# ---------------- 通用项目/研发调研工具（只读） ----------------

_SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "results", "web/tools/avatar_eye_frames"}
_SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".wav", ".mp3", ".onnx", ".wasm", ".mjs", ".ico", ".db", ".db-shm", ".db-wal", ".zip", ".exe", ".bat", ".woff", ".ttf"}
_SKIP_FILES = {"page_dump.html", "restart_web.bat"}




def _upload_dir() -> Path:
    d = REPO_ROOT / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


@tool(
    "read_uploaded_file",
    "读取用户通过对话框上传的文件内容（文本类）；PDF/图片会提示走 MinerU/OCR 识别。只读。",
    {"type": "object", "properties": {"file_id": {"type": "string", "description": "上传返回的 file_id 或文件名片段"}},
     "required": ["file_id"], "additionalProperties": False},
    kind="read", title="读取上传文件：{file_id}",
    present=lambda a, r: [f"文件：{r['name']}", f"大小：{r['size']} 字节", r.get("preview") or r.get("note") or ""],
)
def _read_uploaded_file(file_id: str):
    import re
    directory = _upload_dir()
    key = str(file_id or "").strip()
    if not key:
        raise ValueError("file_id 不能为空")
    matches = [p for p in directory.iterdir() if key in p.name]
    if not matches:
        raise ValueError("没有找到该上传文件，请重新上传")
    target = matches[0]
    if target.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}:
        return {
            "name": target.name, "size": target.stat().st_size,
            "note": "这是二进制/文档文件，建议调用文档解析（MinerU/OCR）接口识别内容。",
        }
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError as error:
        raise ValueError("读取失败：" + str(error))
    preview = text[:1200]
    return {"name": target.name, "size": target.stat().st_size, "preview": preview}


def _sandbox_dir() -> Path:
    d = REPO_ROOT / "sandbox"
    d.mkdir(parents=True, exist_ok=True)
    return d


@tool(
    "run_bash",
    "在受限沙箱中执行 shell 命令（只读项目资源，超时 10 秒），用于处理文件、查看环境、运行简单脚本。",
    {"type": "object", "properties": {"command": {"type": "string", "description": "要执行的 shell 命令"}},
     "required": ["command"], "additionalProperties": False},
    kind="execute", title="沙箱执行：{command}",
    present=lambda a, r: r.get("stdout", "").splitlines()[-5:],
)
def _run_bash(command: str):
    import subprocess
    cmd = str(command or "").strip()
    if not cmd:
        raise ValueError("命令不能为空")
    if len(cmd) > 2000:
        raise ValueError("命令过长")
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=str(_sandbox_dir()),
            timeout=10,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": "命令执行超过 10 秒，已终止。"}
    except Exception as error:
        return {"exit_code": -1, "stdout": "", "stderr": f"{type(error).__name__}: {error}"}
    return {
        "exit_code": result.returncode,
        "stdout": (result.stdout or "")[:8000],
        "stderr": (result.stderr or "")[:4000],
    }

def _safe_project_path(rel: str) -> Path:
    root = REPO_ROOT.resolve()
    if not rel or rel == ".":
        return root
    candidate = (REPO_ROOT / str(rel)).resolve()
    if not str(candidate).startswith(str(root)):
        raise ValueError("路径超出项目仓库范围：" + str(rel))
    return candidate


@tool(
    "list_project_files",
    "列出项目目录里的文件和子目录，用于了解项目结构。只读，不修改任何文件。",
    {"type": "object", "properties": {"path": {"type": "string", "description": "相对项目根目录的路径，默认 ."}},
     "required": [], "additionalProperties": False},
    kind="search", title="查看项目文件：{path}",
    present=lambda a, r: [f"路径：{r['path']}", f"共 {r['count']} 项"]
    + [f"· {x['type']} {x['name']}" for x in r["items"][:10]],
)
def _list_project_files(path: str = "."):
    root = _safe_project_path(path)
    if not root.is_dir():
        raise ValueError("目录不存在：" + str(path))
    entries = sorted(
        root.iterdir(),
        key=lambda x: (not x.is_dir(), x.name.lower()),
    )
    items = []
    for entry in entries:
        if entry.name in _SKIP_DIRS:
            continue
        if entry.is_dir():
            items.append({"name": entry.name, "type": "dir"})
        else:
            if entry.name in _SKIP_FILES or entry.suffix.lower() in _SKIP_SUFFIXES:
                continue
            try:
                size = entry.stat().st_size
            except OSError:
                size = 0
            items.append({"name": entry.name, "type": "file", "size": size})
    return {"path": str(path) or ".", "count": len(items), "items": items[:300]}


@tool(
    "read_project_file",
    "读取项目内的文本文件（代码、JSON、Markdown等），用于查看实现。只读。",
    {"type": "object", "properties": {
        "path": {"type": "string", "description": "相对项目根目录的文件路径"},
        "offset": {"type": "integer", "description": "从第几行开始读，默认 1"},
        "limit": {"type": "integer", "description": "最多读多少行，默认 200"}
     }, "required": ["path"], "additionalProperties": False},
    kind="read", title="读取项目文件：{path}",
    present=lambda a, r: [f"文件：{r['path']}", f"共 {r['total_lines']} 行，当前 {r['offset']}-{r['offset'] + len(r['lines']) - 1}"]
    + r["lines"][:6],
)
def _read_project_file(path: str, offset: int = 1, limit: int = 200):
    target = _safe_project_path(path)
    if not target.is_file():
        raise ValueError("文件不存在：" + str(path))
    if target.suffix.lower() in _SKIP_SUFFIXES:
        raise ValueError("不支持读取二进制文件：" + str(path))
    try:
        all_lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as error:
        raise ValueError("读取失败：" + str(error))
    start = max(1, int(offset or 1))
    count = max(1, min(500, int(limit or 200)))
    lines = all_lines[start - 1:start - 1 + count]
    return {
        "path": str(path),
        "total_lines": len(all_lines),
        "offset": start,
        "limit": count,
        "lines": lines,
    }


@tool(
    "search_project_text",
    "在项目文本文件里用正则搜索关键词，用于找实现/文档线索。只读。",
    {"type": "object", "properties": {
        "query": {"type": "string", "description": "正则表达式或关键词"},
        "path": {"type": "string", "description": "相对项目根目录的目录，默认 ."}
     }, "required": ["query"], "additionalProperties": False},
    kind="search", title="搜索项目文本：{query}",
    present=lambda a, r: [f"搜索：{r['query']}", f"命中 {r['count']} 条"]
    + [f"· {x['path']}:{x['line']}" for x in r["results"][:8]],
)
def _search_project_text(query: str, path: str = "."):
    import re
    root = _safe_project_path(path)
    if not root.is_dir() and not root.is_file():
        raise ValueError("路径不存在：" + str(path))
    try:
        pattern = re.compile(query, re.IGNORECASE)
    except re.error as error:
        raise ValueError("正则表达式错误：" + str(error))
    results = []
    files = [root] if root.is_file() else sorted(root.rglob("*"))
    for fp in files:
        if not fp.is_file():
            continue
        if any(part in _SKIP_DIRS for part in fp.parts):
            continue
        if fp.name in _SKIP_FILES or fp.suffix.lower() in _SKIP_SUFFIXES:
            continue
        if fp.stat().st_size > 2_000_000:
            continue
        try:
            for line_no, line in enumerate(
                fp.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
            ):
                if pattern.search(line):
                    rel = fp.relative_to(REPO_ROOT)
                    results.append({
                        "path": str(rel),
                        "line": line_no,
                        "text": line.strip()[:160],
                    })
                    break
        except OSError:
            continue
        if len(results) >= 200:
            break
    return {"query": query, "count": len(results), "results": results[:200]}


@tool(
    "list_project_docs",
    "列出项目 docs 目录下的文档，用于快速找到交接/架构/开发文档。只读。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="search", title="查看项目文档",
    present=lambda a, r: [f"共 {r['count']} 篇"] + [f"· {x}" for x in r["items"][:12]],
)
def _list_project_docs():
    root = REPO_ROOT / "docs"
    if not root.is_dir():
        return {"count": 0, "items": []}
    items = []
    for fp in sorted(root.rglob("*.md")):
        rel = fp.relative_to(REPO_ROOT)
        items.append(str(rel))
    return {"count": len(items), "items": items}


@tool(
    "check_project_environment",
    "检查项目运行环境：Python版本、Git分支、关键依赖是否安装。只读。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="read", title="检查项目环境",
    present=lambda a, r: [
        f"Python：{r['python']}",
        f"Git 分支：{r['git_branch']}",
        f"工作目录：{r['working_dir']}",
        "依赖：" + ("、".join(k for k, v in r["dependencies"].items() if v) or "无"),
    ],
)
def _check_project_environment():
    import importlib.util
    import sys
    import subprocess
    branch = "unknown"
    try:
        branch = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip() or "unknown"
    except Exception:
        pass
    deps = {}
    for name in ["fastapi", "uvicorn", "openai", "httpx", "numpy", "multipart", "sounddevice", "sherpa_onnx", "torch", "funasr"]:
        deps[name] = importlib.util.find_spec(name) is not None
    return {
        "python": sys.version.split()[0],
        "git_branch": branch,
        "working_dir": str(REPO_ROOT),
        "dependencies": deps,
    }



# ---------------- 实验方案 ----------------

@tool(
    "create_protocol_from_text",
    "根据用户的自然语言描述创建一份新的实验方案。只有用户明确要求创建方案时调用。",
    {
        "type": "object",
        "properties": {"description": {"type": "string"}},
        "required": ["description"],
        "additionalProperties": False,
    },
    kind="execute",
    title="AI 创建实验方案",
    present=lambda a, r: [f"已创建方案：{r['title']}", f"共 {len(r['steps'])} 步"],
)
def _create_protocol_from_text(description):
    draft = llm_bridge.generate_protocol_draft(description)
    saved = domain.add_protocol(draft)
    saved["ui_action"] = {"type": "navigate", "view": "protocols"}
    return saved


@tool(
    "list_protocols",
    "列出所有可选的实验方案，包含方案名称、步骤总数和来源。用户问有哪些实验、想做什么实验时调用。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="search", title="查看可选实验方案",
    present=lambda a, r: [f"共 {len(r)} 份方案，已在方案库展示全部"] + [f"{i}. {x['title']}（{x['total_steps']} 步）" for i, x in enumerate(r[:6], start=1)],
)
def _list_protocols():
    return [
        {
            "protocol_id": p.protocol_id,
            "title": p.title,
            "total_steps": len(p.steps),
            "source": p.source,
        }
        for p in domain.protocols().list_all()
    ]


@tool(
    "select_protocol",
    "选择一份实验方案开始实验；protocol_id 传 null 表示自由记录模式（不按方案）。"
    "用户说要做某个实验时调用。",
    {
        "type": "object",
        "properties": {"protocol_id": {"type": ["string", "null"],
                                       "description": "方案ID，null表示自由记录"}},
        "required": ["protocol_id"],
        "additionalProperties": False,
    },
    kind="execute", title="选择实验方案 {protocol_id}",
    present=lambda a, r: ([f"已进入自由记录模式"] if r.get("mode") == "free" else
                          [f"方案：{r['protocol']['title']}",
                           f"共 {r['protocol']['total_steps']} 步，当前第 {r['step']['number']} 步：{r['step']['title']}"]),
)
def _select_protocol(protocol_id=None):
    result = domain.step_view(domain.start_session(protocol_id or None))
    result["ui_action"] = {"type": "navigate", "view": "run"}
    return result


@tool(
    "create_reagent_prep_from_text",
    "根据用户的自然语言描述创建一条试剂配置。只有用户明确要求创建配方时调用。",
    {
        "type": "object",
        "properties": {"description": {"type": "string"}},
        "required": ["description"],
        "additionalProperties": False,
    },
    kind="execute",
    title="AI 创建试剂配置",
    present=lambda a, r: [f"已创建：{r['name_zh']}", f"共 {len(r['steps'])} 个配制步骤"],
)
def _create_reagent_prep_from_text(description):
    draft = llm_bridge.generate_reagent_prep_draft(description)
    saved = domain.add_reagent_prep(draft)
    saved["ui_action"] = {"type": "navigate", "view": "reagent_prep"}
    return saved


@tool(
    "list_reagent_preps",
    "列出所有可配制的试剂/缓冲液配方。用户在实验前问“要先配什么”“有什么溶液要准备”时调用。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="search", title="查看试剂配置库", experiment_command=True,
    present=lambda a, r: [f"共 {len(r['items'])} 条试剂配置，已在配置库展示全部"]
    + [f"{i}. {x['name_zh']}（{x['target_concentration'] or '工作液'}）" for i, x in enumerate(r["items"][:8], start=1)],
)
def _list_reagent_preps():
    return {
        "items": [domain.reagent_prep_view(p) for p in domain.reagent_preps().list_all()]
    }


@tool(
    "get_reagent_prep",
    "查看某一种试剂/缓冲液的具体配制方法、保存条件和危险提示。"
    "用户问“怎么配 50× TAE”“PBS 怎么配”时调用。",
    {
        "type": "object",
        "properties": {"reagent_prep_id": {"type": "string", "description": "试剂配置ID"}},
        "required": ["reagent_prep_id"],
        "additionalProperties": False,
    },
    kind="read", title="查看试剂配方 {reagent_prep_id}", experiment_command=True,
    present=lambda a, r: [f"配方：{r['name_zh']}", f"目标：{r['target_concentration'] or '未指定'}，溶剂：{r['solvent'] or '未指定'}"]
    + [f"步骤 {i}. {s}" for i, s in enumerate(r["steps"], start=1)]
    + [f"⚠ {s['name']}：{'；'.join(s['statements'][:1])}" for s in r.get("safety", []) if s.get("critical")],
)
def _get_reagent_prep(reagent_prep_id):
    prep = domain.reagent_preps().get_by_id(reagent_prep_id)
    if prep is None:
        raise ValueError("没有这种试剂配置：" + str(reagent_prep_id))
    return domain.reagent_prep_view(prep)


@tool(
    "update_reagent_prep",
    "按ID更新一条试剂配置。用户明确要求“改一下配方/修正某某配法”时调用。",
    {
        "type": "object",
        "properties": {
            "reagent_prep_id": {"type": "string", "description": "试剂配置ID"},
            "reagent_prep": {"type": "object", "description": "完整的新配方 JSON，字段与 create_reagent_prep_from_text 生成的草稿一致"}
        },
        "required": ["reagent_prep_id", "reagent_prep"],
        "additionalProperties": False,
    },
    kind="execute", title="更新试剂配置：{reagent_prep_id}",
    present=lambda a, r: [f"已更新：{r['name_zh']}", f"共 {len(r['steps'])} 个配制步骤"],
)
def _update_reagent_prep(reagent_prep_id, reagent_prep):
    saved = domain.update_reagent_prep(reagent_prep_id, reagent_prep)
    saved["ui_action"] = {"type": "refresh"}
    return saved


@tool(
    "delete_reagent_prep",
    "按ID删除一条试剂配置。用户明确要求“删掉这个配方”时调用。",
    {
        "type": "object",
        "properties": {"reagent_prep_id": {"type": "string", "description": "试剂配置ID"}},
        "required": ["reagent_prep_id"],
        "additionalProperties": False,
    },
    kind="execute", title="删除试剂配置：{reagent_prep_id}",
    present=lambda a, r: [f"已删除：{r['reagent_prep_id']}"],
)
def _delete_reagent_prep(reagent_prep_id):
    result = domain.delete_reagent_prep(reagent_prep_id)
    result["ui_action"] = {"type": "navigate", "view": "reagent_prep"}
    return result


@tool(
    "get_protocol_prep_requirements",
    "查看当前所选实验方案在开始前需要准备哪些试剂/缓冲液。"
    "用户问“做这个实验前要先配什么”时调用。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="read", title="查看实验前准备材料", experiment_command=True,
    present=lambda a, r: ([f"方案 {r['protocol_id']} 需要准备："]
                          + [f"· {x['name_zh']}：{x['purpose']}" for x in r["items"]])
    if r["items"] else ["当前没有可用的准备材料清单。"],
)
def _get_protocol_prep_requirements():
    state = domain.session()
    protocol_id = state.selection.protocol.protocol_id if state.selection.protocol else None
    return domain.protocol_prep_requirements(protocol_id)


@tool(
    "get_current_step",
    "查看当前实验进行到第几步、这一步必须现场记录什么、已经记录了什么、还缺什么、"
    "当前状态如何，以及涉及试剂的安全提示。用户问“现在做到哪了”“这步还差什么”，"
    "或用户说“完成了/好了/做完了”时调用——用本工具核对确定性进度，不要自己猜。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="read", title="查看当前步骤", experiment_command=True,
    present=lambda a, r: ([f"当前为自由记录模式"] if r.get("mode") == "free" else
                          [f"第 {r['step']['number']}/{r['protocol']['total_steps']} 步：{r['step']['title']}",
                           f"现场必测：{'、'.join(r['step']['must_record']) or '无'}"]
                          + (lambda p: ([f"状态：{p['status']}",
                                         f"已记录：{'、'.join(p['recorded']) or '无'}",
                                         f"还缺：{'、'.join(p['missing']) or '无'}"]
                                        if p else []))(r.get("progress"))
                          + [f"⚠ {s['name']}：{'；'.join(s['statements'][:1])}" for s in r.get("safety", []) if s.get("critical")]),
)
def _get_current_step():
    view = domain.step_view(domain.session())
    view["progress"] = domain.step_progress_view(domain.session())
    return view


@tool(
    "move_step",
    "推进实验步骤。action 取 next（下一步）、prev（上一步）或 jump（跳到指定步）。"
    "只有用户明确表示要换步骤时才调用，不要自己猜测用户做到哪一步了。",
    {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["next", "prev", "jump"]},
            "step_number": {"type": ["integer", "null"], "description": "jump 时的目标步号"},
        },
        "required": ["action", "step_number"],
        "additionalProperties": False,
    },
    kind="execute", title="推进步骤 {action}",
    present=lambda a, r: ([f"当前为自由记录模式"] if r.get("mode") == "free" else
                          [f"已到第 {r['step']['number']}/{r['protocol']['total_steps']} 步：{r['step']['title']}"]),
)
def _move_step(action, step_number=None):
    result = domain.step_view(domain.move(action, step_number))
    result["ui_action"] = {"type": "navigate", "view": "run"}
    return result


@tool(
    "navigate_view",
    "打开软件中的指定页面。用户说查看方案、查看安全库、打开设置或返回实验进行中时调用。",
    {
        "type": "object",
        "properties": {
            "view": {
                "type": "string",
                "enum": ["run", "protocols", "reagent_prep", "reagents", "records", "settings"],
            }
        },
        "required": ["view"],
        "additionalProperties": False,
    },
    kind="read",
    title="打开页面 {view}",
    present=lambda a, r: ["已打开目标页面"],
)
def _navigate_view(view):
    return {"ui_action": {"type": "navigate", "view": view}}


@tool(
    "get_protocol_detail",
    "查看一份实验方案的完整步骤、准备材料和安全提示。",
    {
        "type": "object",
        "properties": {"protocol_id": {"type": "string"}},
        "required": ["protocol_id"],
        "additionalProperties": False,
    },
    kind="read", experiment_command=True,
    title="查看方案 {protocol_id}",
    present=lambda a, r: [f"方案：{r['protocol']['title']}", f"共 {len(r['steps'])} 步"],
)
def _get_protocol_detail(protocol_id):
    result = domain.protocol_detail(protocol_id)
    result["ui_action"] = {"type": "navigate", "view": "protocols"}
    return result


@tool(
    "add_protocol_step",
    "在指定实验方案的某一步之后添加新步骤。",
    {
        "type": "object",
        "properties": {
            "protocol_id": {"type": "string"},
            "after_step_number": {"type": ["integer", "null"]},
            "title": {"type": "string"},
            "instruction": {"type": "string"},
        },
        "required": ["protocol_id", "after_step_number", "title", "instruction"],
        "additionalProperties": False,
    },
    kind="execute",
    title="添加方案步骤 {title}",
    present=lambda a, r: ["步骤已添加，方案版本已更新"],
)
def _add_protocol_step(protocol_id, after_step_number, title, instruction):
    result = domain.add_protocol_step({
        "protocol_id": protocol_id,
        "after_step_number": after_step_number,
        "title": title,
        "instruction": instruction,
        "must_record": [],
        "terms": [],
    })
    result["ui_action"] = {"type": "navigate", "view": "protocols"}
    return result


@tool(
    "update_protocol_step",
    "修改指定实验方案中某一步的标题、说明或安全提示。只传需要修改的字段。",
    {
        "type": "object",
        "properties": {
            "protocol_id": {"type": "string"},
            "step_number": {"type": "integer"},
            "title": {"type": ["string", "null"]},
            "instruction": {"type": ["string", "null"]},
            "hazard_note": {"type": ["string", "null"]},
        },
        "required": ["protocol_id", "step_number", "title", "instruction", "hazard_note"],
        "additionalProperties": False,
    },
    kind="execute",
    title="修改方案步骤 {step_number}",
    present=lambda a, r: ["步骤已修改，方案版本已更新"],
)
def _update_protocol_step(protocol_id, step_number, title=None, instruction=None, hazard_note=None):
    result = domain.update_step({
        "protocol_id": protocol_id,
        "step_number": step_number,
        "title": title,
        "instruction": instruction,
        "hazard_note": hazard_note,
    })
    result["ui_action"] = {"type": "navigate", "view": "protocols"}
    return result


@tool(
    "delete_protocol_step",
    "删除指定实验方案中的某一步。只有用户明确要求删除时调用。",
    {
        "type": "object",
        "properties": {
            "protocol_id": {"type": "string"},
            "step_number": {"type": "integer"},
        },
        "required": ["protocol_id", "step_number"],
        "additionalProperties": False,
    },
    kind="execute",
    title="删除方案步骤 {step_number}",
    present=lambda a, r: ["步骤已删除，后续步骤已重新编号"],
)
def _delete_protocol_step(protocol_id, step_number):
    result = domain.delete_protocol_step(protocol_id, step_number)
    result["ui_action"] = {"type": "navigate", "view": "protocols"}
    return result


# ---------------- 实验记录 ----------------

def _current_terms() -> tuple[str, ...]:
    step = domain.session().current_step()
    return tuple(step.terms) if step is not None else ()


def _next_record_segment(session_id: str) -> int:
    with _record_lock:
        return next_segment_id(session_id)


def _save_record_locked(item: dict[str, object]):
    with _record_lock:
        return save_record(item)


def _build_record_service() -> SharedRecordService:
    """Bind tool/runtime dependencies to the shared record application service."""

    return SharedRecordService(
        current_session_id=current_session_id,
        next_segment_id=_next_record_segment,
        list_records=list_records,
        extract_entities_llm=llm_bridge.extract,
        extract_entities_rule=extract_entities,
        current_terms=_current_terms,
        evaluate=domain.evaluate,
        step_view=lambda: domain.step_view(domain.session()),
        save_record=_save_record_locked,
        clock=datetime.now,
        request_id_factory=lambda: f"tool-{uuid.uuid4().hex[:12]}",
    )

@tool(
    "record_observation",
    "记录一段实验口述，系统会抽取其中的数量、单位、浓度、温度、时长等实测值，"
    "并按当前方案判断还缺什么、有没有偏离方案规定值。"
    "用户描述自己刚做了什么操作、测到什么数据时调用。",
    {
        "type": "object",
        "properties": {"transcript": {"type": "string", "description": "用户口述原文"}},
        "required": ["transcript"],
        "additionalProperties": False,
    },
    kind="execute", title="记录实验口述",
    present=lambda a, r: ([f"抽取：{'、'.join(f'{k}={v}' for k, v in r['entities'].items()) or '未抽到结构化字段'}"]
                          + ([f"缺失：{'、'.join(r['missing_fields'])}"] if r["missing_fields"] else ["本步记录已完整"])
                          + [f"⚠ 偏差：{d['field']} 实际 {d['actual_value']}，方案 {d['protocol_value']}" for d in r["deviations"]]),
)
def _record_observation(transcript):
    result = _build_record_service().record(RecordCommand(transcript=transcript))
    observation = result.observation_result
    saved_evaluation = result.saved_record.get("evaluation")
    evaluation = saved_evaluation if isinstance(saved_evaluation, dict) else {}
    payload = {
        "transcript": (
            observation.transcript
            if observation is not None
            else result.saved_record["transcript"]
        ),
        "entities": dict(
            observation.entities
            if observation is not None
            else result.saved_record.get("entities") or {}
        ),
        "missing_fields": list(
            observation.missing_fields
            if observation is not None
            else evaluation.get("missing_fields") or ()
        ),
        "follow_up_question": (
            observation.follow_up_question
            if observation is not None
            else evaluation.get("follow_up_question")
        ),
        "deviations": list(
            observation.deviations
            if observation is not None
            else evaluation.get("deviations") or ()
        ),
    }
    return PresentedToolResult(
        payload=payload,
        presentation_plan=build_delivery_plan(
            result.intents, ui_mode="user",
            speech_rate=settings_store.current().tts_speed,
        ),
    )


# ---------------- 时间 / 计时 ----------------

@tool(
    "get_current_time",
    "获取当前日期和本地时间。用户问现在几点、今天几号、实验时间安排时调用。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="read", title="查看当前时间", experiment_command=True,
    present=lambda a, r: [f"当前时间：{r['now']}（{r['weekday']}）"],
)
def _get_current_time():
    now = datetime.now()
    return {
        "now": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "weekday": "星期" + "一二三四五六日"[now.weekday()],
        "unix_seconds": int(now.timestamp()),
    }


@tool(
    "start_timer",
    "启动一个计时器。用户说“计时X分钟/秒”“帮我定时”时调用。",
    {
        "type": "object",
        "properties": {
            "duration_seconds": {"type": "integer", "description": "计时时长（秒）"},
            "label": {"type": "string", "description": "计时器备注，如：水浴加热"},
        },
        "required": ["duration_seconds"],
        "additionalProperties": False,
    },
    kind="execute", title="启动计时器 {label}", experiment_command=True,
    present=lambda a, r: [f"计时器已启动：{r['label'] or '未命名'}，{r['duration_seconds']} 秒后结束"],
)
def _start_timer(duration_seconds, label=None):
    if not isinstance(duration_seconds, int) or duration_seconds <= 0:
        raise ValueError("duration_seconds 必须是正整数")
    timer_id = str(uuid.uuid4())[:8]
    now = datetime.now()
    end_at = now + timedelta(seconds=duration_seconds)
    timer = {
        "timer_id": timer_id,
        "label": label or "",
        "duration_seconds": duration_seconds,
        "started_at": now.isoformat(timespec="seconds"),
        "end_at": end_at.isoformat(timespec="seconds"),
    }
    with _timers_lock:
        _timers[timer_id] = timer
    return timer


@tool(
    "check_timer",
    "查询计时器剩余时间。用户问“还有多久”“时间到了吗”时调用。",
    {
        "type": "object",
        "properties": {"timer_id": {"type": "string", "description": "start_timer 返回的 timer_id"}},
        "required": ["timer_id"],
        "additionalProperties": False,
    },
    kind="read", title="查看计时器", experiment_command=True,
    present=lambda a, r: [f"计时器 {r['label'] or r['timer_id']}：{r['remaining_seconds']} 秒剩余"],
)
def _check_timer(timer_id):
    with _timers_lock:
        timer = _timers.get(timer_id)
        if timer is None:
            return {"found": False, "message": "没有找到这个计时器，请重新启动一个。"}
        end_at = datetime.fromisoformat(timer["end_at"])
        remaining = max(0, int((end_at - datetime.now()).total_seconds()))
        return {
            "found": True,
            "timer_id": timer_id,
            "label": timer["label"],
            "duration_seconds": timer["duration_seconds"],
            "started_at": timer["started_at"],
            "end_at": timer["end_at"],
            "remaining_seconds": remaining,
            "finished": remaining <= 0,
        }


@tool(
    "list_experiment_commands",
    "列出实验记录过程中当前允许小科调用的全部工具。用户问“小科你能做什么”、"
    "“有哪些工具”或“支持什么功能”时调用。清单直接来自工具注册表。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="read", title="查看小科当前可用工具", experiment_command=True,
    present=lambda a, r: [
        f"{item['title']}：{item['description']}" for item in r["tools"]
    ] or ["当前没有开放的实验工具。"],
)
def _list_experiment_commands():
    tools = experiment_command_catalog()
    return {"count": len(tools), "tools": tools}


@tool(
    "suggest_step_improvement",
    "当用户发现当前实验步骤有更好的做法、更贴近本实验室的操作，或想记录改进建议时调用。"
    "只负责记录，不直接修改方案。",
    {
        "type": "object",
        "properties": {"text": {"type": "string", "description": "用户提出的改进建议原文"}},
        "required": ["text"],
        "additionalProperties": False,
    },
    kind="execute", title="记录步骤改进建议",
    present=lambda a, r: [f"已记录：{r['text']}"],
)
def _suggest_step_improvement(text):
    text = str(text or "").strip()
    if not text:
        raise ValueError("改进建议不能为空")
    state = domain.session()
    step = state.current_step()
    protocol = state.selection.protocol
    item = {
        "at": datetime.now().isoformat(timespec="seconds"),
        "protocol_id": protocol.protocol_id if protocol else None,
        "protocol_title": protocol.title if protocol else None,
        "step_number": step.step_number if step else None,
        "step_title": step.title if step else None,
        "text": text,
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    with STEP_IMPROVEMENTS_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item


# ---------------- 试剂安全 ----------------

@tool(
    "check_reagent_safety",
    "查询试剂的危险性信息，包含 CAS 号、GHS 危险性说明和高危提示。"
    "用户问某个试剂有没有毒、要注意什么、能不能直接倒掉时调用。"
    "数据来自 PubChem，未经实验室安全负责人复核，不能替代 MSDS。",
    {
        "type": "object",
        "properties": {"reagent": {"type": "string", "description": "试剂中文名，如 氢氧化钠"}},
        "required": ["reagent"],
        "additionalProperties": False,
    },
    kind="read", title="查询试剂安全：{reagent}", experiment_command=True,
    present=lambda a, r: ([r["message"]] if not r.get("found") else
                          [f"{r['name']}（CAS {r['cas'] or '未获取'}）"]
                          + ([f"⚠ 高危 {'/'.join(r['critical_codes'])}"] if r["critical"] else ["无高危项"])
                          + r["statements"][:3]),
)
def _check_reagent_safety(reagent):
    store = domain.hazmat()
    found = store.find(reagent) or (store.find_in_text(reagent) or [None])[0]
    if found is None:
        return {
            "found": False,
            "message": "知识库中没有这种试剂，不能据此认为它安全。请查阅 MSDS。",
        }
    return {
        "found": True,
        "name": found.name_zh,
        "cas": found.cas,
        "molecular_formula": found.molecular_formula,
        "critical": found.is_critical,
        "critical_codes": list(found.critical_codes),
        "statements": [s.text for s in found.hazard_statements],
        "disclaimer": store.authority_note,
    }


# ---------------- 分子量计算 ----------------

# 常用元素原子量（实验室常见范围，足够覆盖现有危化品/试剂库）
_ATOMIC_MASS = {
    "H": 1.008, "He": 4.003, "Li": 6.94, "Be": 9.012, "B": 10.81,
    "C": 12.011, "N": 14.007, "O": 15.999, "F": 18.998, "Ne": 20.180,
    "Na": 22.990, "Mg": 24.305, "Al": 26.982, "Si": 28.085, "P": 30.974,
    "S": 32.06, "Cl": 35.45, "Ar": 39.948, "K": 39.098, "Ca": 40.078,
    "Sc": 44.956, "Ti": 47.867, "V": 50.942, "Cr": 51.996, "Mn": 54.938,
    "Fe": 55.845, "Co": 58.933, "Ni": 58.693, "Cu": 63.546, "Zn": 65.38,
    "Ga": 69.723, "Ge": 72.630, "As": 74.922, "Se": 78.971, "Br": 79.904,
    "Kr": 83.798, "Rb": 85.468, "Sr": 87.62, "Y": 88.906, "Zr": 91.224,
    "Nb": 92.906, "Mo": 95.95, "Ru": 101.07, "Rh": 102.91, "Pd": 106.42,
    "Ag": 107.87, "Cd": 112.41, "In": 114.82, "Sn": 118.71, "Sb": 121.76,
    "Te": 127.60, "I": 126.90, "Xe": 131.29, "Cs": 132.91, "Ba": 137.33,
    "La": 138.91, "Ce": 140.12, "Pr": 140.91, "Nd": 144.24, "Sm": 150.36,
    "Eu": 151.96, "Gd": 157.25, "Tb": 158.93, "Dy": 162.50, "Ho": 164.93,
    "Er": 167.26, "Tm": 168.93, "Yb": 173.05, "Lu": 174.97, "Hf": 178.49,
    "Ta": 180.95, "W": 183.84, "Re": 186.21, "Os": 190.23, "Ir": 192.22,
    "Pt": 195.08, "Au": 196.97, "Hg": 200.59, "Tl": 204.38, "Pb": 207.2,
    "Bi": 208.98, "Th": 232.04, "U": 238.03,
}


def _parse_formula_unit(text: str):
    """递归解析一个化学式单元，支持括号和下标的任意组合。

    例如 H2O、NaCl、C6H12O6、CuSO4、(NH4)2SO4、Ca(OH)2、Al2(SO4)3。
    返回 (质量, 规范化显示, 结束下标)。
    """
    def parse(idx):
        mass = 0.0
        parts = []
        while idx < len(text):
            ch = text[idx]
            if ch == ")":
                return mass, "".join(parts), idx + 1
            if ch == "(":
                inner_mass, inner_disp, idx = parse(idx + 1)
                count = 0
                while idx < len(text) and text[idx].isdigit():
                    count = count * 10 + int(text[idx])
                    idx += 1
                n = count or 1
                mass += inner_mass * n
                parts.append(f"({inner_disp})" + (str(count) if count else ""))
                continue
            if ch.isupper():
                j = idx + 1
                if j < len(text) and text[j].islower():
                    j += 1
                element = text[idx:j]
                if element not in _ATOMIC_MASS:
                    raise ValueError(f"暂不支持元素：{element}")
                idx = j
                count = 0
                while idx < len(text) and text[idx].isdigit():
                    count = count * 10 + int(text[idx])
                    idx += 1
                n = count or 1
                mass += _ATOMIC_MASS[element] * n
                parts.append(f"{element}" + (str(count) if count else ""))
                continue
            raise ValueError(f"无法解析化学式：{text}")
        return mass, "".join(parts), idx

    mass, disp, idx = parse(0)
    if idx != len(text):
        raise ValueError(f"无法解析化学式：{text}")
    return mass, disp


def _parse_formula_custom(formula: str):
    """解析化学式，支持括号、下标和结晶水合物。

    支持：
    - 简单式：H2O、NaCl、C6H12O6、CuSO4
    - 括号：Ca(OH)2、(NH4)2SO4、Al2(SO4)3、KAl(SO4)2
    - 结晶水合物：CuSO4·5H2O、CuSO4.5H2O、Na2CO3·10H2O、FeSO4·7H2O
    - 复盐：KAl(SO4)2·12H2O
    """
    formula = str(formula or "").strip().replace(" ", "")
    if not formula:
        raise ValueError("化学式不能为空")
    formula = (formula.replace("·", ".")
               .replace("⋅", ".")
               .replace("∙", ".")
               .replace("×", ".")
               .replace("＊", ".")
               .replace("*", "."))
    if "." in formula:
        units = [u for u in formula.split(".") if u]
        total = 0.0
        displays = []
        for unit in units:
            coeff = 1
            body = unit
            match = re.match(r"^(\d+)(.*)$", unit)
            if match:
                coeff = int(match.group(1))
                body = match.group(2)
            mass, disp = _parse_formula_unit(body)
            total += coeff * mass
            displays.append((str(coeff) if coeff != 1 else "") + disp)
        return round(total, 3), "·".join(displays)
    mass, disp = _parse_formula_unit(formula)
    return round(mass, 3), disp


# 优先使用开源化学式库 molmass（BSD-3），缺失时回退到内置解析器。
try:
    from molmass import Formula as _MolFormula
except Exception:  # pragma: no cover - 依赖未安装时走内置解析器
    _MolFormula = None


def _parse_formula(formula: str):
    """解析化学式并计算分子量；优先用 molmass，失败回退内置解析器。"""
    if _MolFormula is not None:
        try:
            normalized = (str(formula or "").strip().replace(" ", "")
                          .replace("·", ".")
                          .replace("⋅", ".")
                          .replace("∙", ".")
                          .replace("×", ".")
                          .replace("＊", ".")
                          .replace("*", "."))
            mass = float(_MolFormula(normalized).mass)
            display = normalized
            try:
                _, display = _parse_formula_custom(formula)
            except Exception:
                pass
            return round(mass, 3), display
        except Exception:
            pass
    return _parse_formula_custom(formula)


_REAGENT_ALIASES = {
    "丙酮酸": {"name": "丙酮酸", "formula": "C3H4O3", "molecular_weight": "88.062", "name_en": "pyruvic acid"},
    "pyruvic acid": {"name": "丙酮酸", "formula": "C3H4O3", "molecular_weight": "88.062", "name_en": "pyruvic acid"},
    "丙酮酸钠": {"name": "丙酮酸钠", "formula": "C3H3NaO3", "molecular_weight": "110.04", "name_en": "sodium pyruvate"},
    "sodium pyruvate": {"name": "丙酮酸钠", "formula": "C3H3NaO3", "molecular_weight": "110.04", "name_en": "sodium pyruvate"},
    "乙酸钠": {"name": "乙酸钠", "formula": "C2H3NaO2", "molecular_weight": "82.03", "name_en": "sodium acetate"},
    "sodium acetate": {"name": "乙酸钠", "formula": "C2H3NaO2", "molecular_weight": "82.03", "name_en": "sodium acetate"},
}

@tool(
    "calculate_molecular_weight",
    "计算分子量或摩尔质量。用户问某试剂的分子量、摩尔质量、Mw、相对分子质量，"
    "或者给出化学式（如 H2O、NaCl、C6H12O6）要计算时调用。"
    "会先查试剂安全库，查不到就按化学式解析计算。",
    {
        "type": "object",
        "properties": {
            "reagent": {"type": "string", "description": "试剂中文名/英文名/化学式，如 氢氧化钠、NaCl、C6H12O6"}
        },
        "required": ["reagent"],
        "additionalProperties": False,
    },
    kind="read", title="分子量计算：{reagent}", experiment_command=True,
    present=lambda a, r: [
        (f"{r['name']}：{r['molecular_weight']}" if r.get("name") else f"{r['formula']}：{r['molecular_weight']}")
        + (" g/mol" if r.get("molecular_weight") else "")
    ],
)
def _calculate_molecular_weight(reagent):
    reagent = str(reagent or "").strip()
    if not reagent:
        raise ValueError("请输入试剂名称或化学式")
    from tools.reagent_catalog import find_reagent
    cat = find_reagent(reagent)
    if cat is not None and cat.get("molecular_weight"):
        return {
            "found": True,
            "name": cat.get("name_zh") or cat.get("name_en"),
            "formula": cat.get("formula"),
            "molecular_weight": float(cat["molecular_weight"]),
            "unit": "g/mol",
            "source": "通用试剂目录",
            "state": cat.get("state"),
            "density": cat.get("density"),
            "acidic": cat.get("acidic"),
            "pKa": cat.get("pKa"),
        }
    alias = _REAGENT_ALIASES.get(reagent.strip().lower()) or _REAGENT_ALIASES.get(reagent.strip())
    if alias is not None:
        return {
            "found": True,
            "name": alias["name"],
            "formula": alias["formula"],
            "molecular_weight": float(alias["molecular_weight"]),
            "unit": "g/mol",
            "source": "内置试剂别名表（经 PubChem 分子量复核）",
        }
    store = domain.hazmat()
    found = store.find(reagent) or (store.find_in_text(reagent) or [None])[0]
    if found is not None and found.molecular_weight:
        return {
            "found": True,
            "name": found.name_zh,
            "formula": found.molecular_formula,
            "molecular_weight": float(found.molecular_weight),
            "unit": "g/mol",
            "source": "试剂安全库（PubChem）",
        }
    if found is not None and found.molecular_formula:
        weight, formula = _parse_formula(found.molecular_formula)
        return {
            "found": True,
            "name": found.name_zh,
            "formula": formula,
            "molecular_weight": weight,
            "unit": "g/mol",
            "source": "按化学式从试剂安全库计算",
        }
    weight, formula = _parse_formula(reagent)
    return {
        "found": True,
        "name": None,
        "formula": formula,
        "molecular_weight": weight,
        "unit": "g/mol",
        "source": "按化学式解析计算",
    }


# ---------------- 溶液配制与稀释计算 ----------------

@tool(
    "calculate_solution_prep",
    "计算配制一定摩尔浓度溶液所需的称样量。用户说“配 0.1 mol/L 的 NaOH 500 mL”"
    "“配 1 M Tris 100 mL”这类需求时调用。会先算分子量，再按 质量=浓度×体积×分子量 计算。",
    {
        "type": "object",
        "properties": {
            "reagent": {"type": "string", "description": "试剂中文名/英文名/化学式，如 氢氧化钠、NaCl、Tris"},
            "molarity": {"type": "number", "description": "目标浓度，单位 mol/L，如 0.1"},
            "volume": {"type": "number", "description": "目标体积数值"},
            "volume_unit": {"type": "string", "enum": ["L", "mL"], "description": "体积单位，默认 L"},
            "purity": {"type": "number", "description": "试剂纯度百分比，默认 100，如 98 表示 98%"},
        },
        "required": ["reagent", "molarity", "volume"],
        "additionalProperties": False,
    },
    kind="read", title="溶液配制：{molarity} mol/L {reagent} {volume}{volume_unit}", experiment_command=True,
    present=lambda a, r: [
        f"{r['name'] or r['formula']} 分子量 {r['molecular_weight']} g/mol",
        f"需称取 {r['mass_g']} g（{r['mass_mg']} mg）",
        r["instruction"],
    ],
)
def _calculate_solution_prep(reagent, molarity, volume, volume_unit="L", purity=100.0):
    mw_result = _calculate_molecular_weight(reagent)
    if not mw_result.get("molecular_weight"):
        raise ValueError("无法确定分子量，请提供正确的试剂名或化学式")
    molarity = float(molarity)
    if molarity <= 0:
        raise ValueError("浓度必须大于 0")
    volume = float(volume)
    if volume <= 0:
        raise ValueError("体积必须大于 0")
    raw_unit = str(volume_unit or "L").strip().lower()
    if raw_unit in ("ml", "毫升"):
        volume_l = volume / 1000.0
        unit_display = "mL"
    else:
        volume_l = volume
        unit_display = "L"
    purity = float(purity if purity is not None else 100)
    if purity <= 0 or purity > 100:
        raise ValueError("纯度应在 0-100 之间")
    mw = float(mw_result["molecular_weight"])
    mass_g = mw * molarity * volume_l / (purity / 100.0)
    return {
        "name": mw_result.get("name"),
        "formula": mw_result.get("formula"),
        "molecular_weight": mw,
        "molarity": molarity,
        "volume": volume,
        "volume_unit": unit_display,
        "purity": purity,
        "mass_g": round(mass_g, 4),
        "mass_mg": round(mass_g * 1000, 2),
        "instruction": f"称取约 {round(mass_g, 4)} g（{round(mass_g * 1000, 2)} mg），溶解后定容至 {volume} {unit_display}。",
    }


@tool(
    "calculate_dilution",
    "计算稀释需要的母液体积。用户说“把 1 M 母液稀释成 0.1 M 共 500 mL”时调用，"
    "使用 C1V1=C2V2。",
    {
        "type": "object",
        "properties": {
            "stock_concentration": {"type": "number", "description": "母液浓度，单位 mol/L 或 ×，如 1"},
            "final_concentration": {"type": "number", "description": "目标浓度，单位与母液一致，如 0.1"},
            "final_volume": {"type": "number", "description": "目标体积数值"},
            "volume_unit": {"type": "string", "enum": ["L", "mL"], "description": "体积单位，默认 mL"},
        },
        "required": ["stock_concentration", "final_concentration", "final_volume"],
        "additionalProperties": False,
    },
    kind="read", title="稀释计算：{final_concentration} 从 {stock_concentration} 配 {final_volume}{volume_unit}", experiment_command=True,
    present=lambda a, r: [
        f"取母液 {r['stock_volume']} {r['volume_unit']}",
        f"再加溶剂定容至 {r['final_volume']} {r['volume_unit']}",
    ],
)
def _calculate_dilution(stock_concentration, final_concentration, final_volume, volume_unit="mL"):
    c1 = float(stock_concentration)
    c2 = float(final_concentration)
    v2 = float(final_volume)
    if c1 <= 0 or c2 <= 0 or v2 <= 0:
        raise ValueError("浓度和体积必须大于 0")
    if c2 > c1:
        raise ValueError("目标浓度不能高于母液浓度")
    v1 = c2 * v2 / c1
    raw_unit = str(volume_unit or "mL").strip().lower()
    unit_display = "mL" if raw_unit in ("ml", "毫升") else "L"
    return {
        "stock_volume": round(v1, 4),
        "volume_unit": unit_display,
        "final_volume": v2,
        "formula": "C1V1=C2V2",
        "instruction": f"取母液 {round(v1, 4)} {unit_display}，再加溶剂定容至 {v2} {unit_display}。",
    }


# ---------- 储存库工具 ----------
from database import crud as _storage_crud  # noqa: E402


@tool(
    "list_storage_items",
    "查看/搜索储存库物品。用户问“我存了什么/种子在哪/冰箱里有什么/查储存库”时调用。",
    {
        "type": "object",
        "properties": {
            "q": {"type": "string", "description": "按名称/位置/备注搜索，可留空"},
            "item_type": {"type": "string", "description": "物品类型：溶液/种子/DNA/菌液/试剂/耗材/产物"},
        },
        "required": [],
        "additionalProperties": False,
    },
    kind="search", title="查询储存库",
    present=lambda a, r: [
        f"共 {len(r)} 项",
        *[f"{x.get('name')} · {x.get('location_name') or '未分配'}" for x in r[:5]],
    ],
)
def _list_storage_items(q="", item_type=""):
    return _storage_crud.list_storage_items(q=q, item_type=item_type)


@tool(
    "add_storage_item",
    "向储存库新增一个存储物品（溶液/种子/DNA/试剂等）。用户说“储存一个种子/入库/放到储存库”时调用。",
    {
        "type": "object",
        "properties": {
            "item_type": {"type": "string", "description": "物品类型，默认溶液"},
            "name": {"type": "string", "description": "物品名称，如 ACS 种子、质粒 pUC19"},
            "quantity": {"type": "string", "description": "数量，如 一罐/1 罐/300"},
            "unit": {"type": "string", "description": "单位，如 罐/mL/管"},
            "concentration": {"type": "string", "description": "浓度，如 100 ng/μL"},
            "location_id": {"type": "integer", "description": "存储位置 id，可先 list_storage_locations 查询"},
            "position": {"type": "string", "description": "格子/标签，如 2层 A-03"},
            "storage_condition": {"type": "string", "description": "存放条件，如 4℃ / -20℃ / 室温"},
            "expires_at": {"type": "string", "description": "到期日期，YYYY-MM-DD"},
            "notes": {"type": "string", "description": "备注，如来源实验"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    kind="execute", title="入库：{name}",
    present=lambda a, r: [
        f"已入库 {r.get('name')}",
        f"存放：{r.get('storage_condition') or '未指定'}",
    ],
)
def _add_storage_item(item_type="其他", name="", quantity="", unit="", concentration="",
                      location_id=None, position="", storage_condition="", expires_at="", notes=""):
    return _storage_crud.create_storage_item({
        "item_type": item_type, "name": name, "quantity": quantity, "unit": unit,
        "concentration": concentration, "location_id": location_id, "position": position,
        "storage_condition": storage_condition, "expires_at": expires_at, "notes": notes,
    })


@tool(
    "update_storage_item",
    "修改储存库中某个物品的信息（数量、位置、状态、备注等）。用户说“改一下/移到/取用/丢弃”时调用。",
    {
        "type": "object",
        "properties": {
            "item_id": {"type": "integer", "description": "物品 id，先 list_storage_items 查询"},
            "name": {"type": "string"},
            "quantity": {"type": "string"},
            "unit": {"type": "string"},
            "concentration": {"type": "string"},
            "location_id": {"type": "integer"},
            "position": {"type": "string"},
            "storage_condition": {"type": "string"},
            "status": {"type": "string", "enum": ["in_storage", "taken", "discarded", "expired"]},
            "notes": {"type": "string"},
        },
        "required": ["item_id"],
        "additionalProperties": False,
    },
    kind="execute", title="修改储存物品：{item_id}",
    present=lambda a, r: [f"已更新：{r.get('name')}", f"状态：{r.get('status')}"],
)
def _update_storage_item(item_id, **kwargs):
    return _storage_crud.update_storage_item(item_id, kwargs)


@tool(
    "delete_storage_item",
    "从储存库删除一个物品。用户说“删掉/丢弃这个”时调用。",
    {
        "type": "object",
        "properties": {"item_id": {"type": "integer", "description": "物品 id"}},
        "required": ["item_id"],
        "additionalProperties": False,
    },
    kind="execute", title="删除储存物品：{item_id}",
    present=lambda a, r: ["已删除"],
)
def _delete_storage_item(item_id):
    return _storage_crud.delete_storage_item(item_id)


@tool(
    "list_storage_locations",
    "查看储存库所有存储位置（冰箱、冰柜、试剂柜、样品柜等）。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="search", title="查看存储位置",
    present=lambda a, r: [
        f"共 {len(r)} 个位置",
        *[f"{x.get('name')} · {x.get('type')} · {x.get('temperature')}" for x in r[:8]],
    ],
)
def _list_storage_locations():
    return _storage_crud.list_storage_locations()


@tool(
    "add_storage_location",
    "新增一个存储位置（如冰箱2层、4℃试剂柜）。",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "type": {"type": "string", "description": "冰箱/冰柜/试剂柜/样品柜/其他"},
            "temperature": {"type": "string"},
            "capacity": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    kind="execute", title="新增存储位置：{name}",
    present=lambda a, r: [f"已新增位置：{r.get('name')}"],
)
def _add_storage_location(name, type="其他", temperature="", capacity="", notes=""):
    return _storage_crud.create_storage_location({
        "name": name, "type": type, "temperature": temperature,
        "capacity": capacity, "notes": notes,
    })


@tool(
    "storage_stats",
    "查看储存库统计（总数、7天内到期、已过期）。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="read", title="储存库统计",
    present=lambda a, r: [
        f"总数 {r.get('total')}",
        f"7天内到期 {r.get('expiring')}",
        f"已过期 {r.get('expired')}",
    ],
)
def _storage_stats():
    return _storage_crud.storage_stats()
