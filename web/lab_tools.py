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
from datetime import datetime, timedelta
import threading
import uuid

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
    "读取用户通过对话框上传的文件内容（文本类）；PDF/图片会提示走 MinerU/OCR 识别。只读。不要用于修改文件、执行命令或写入项目。",
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
    "在受限沙箱中执行 shell 命令（只读项目资源，超时 10 秒），用于处理文件、查看环境、运行简单脚本。不要用于修改生产数据、删除关键文件或执行破坏性命令。",
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
    "列出项目目录里的文件和子目录，用于了解项目结构。只读，不修改任何文件。不要用于执行命令或修改项目。",
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
    "读取项目内的文本文件（代码、JSON、Markdown等），用于查看实现。只读。不要用于修改文件或执行命令。",
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
    "在项目文本文件里用正则搜索关键词，用于找实现/文档线索。只读。不要用于修改文件或执行命令。",
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
    "列出项目 docs 目录下的文档，用于快速找到交接/架构/开发文档。只读。不要用于修改文件或执行命令。",
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
    "检查项目运行环境：Python版本、Git分支、关键依赖是否安装。只读。不要用于修改环境或安装依赖。",
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
    "根据自然语言描述创建一份新的实验方案。传入你能收集到的最完整描述即可（实验名称+目的+关键参数），"
    "AI 会自动补齐标准实验步骤，不需要用户提供逐步文字。"
    "用户说'和现有方案一样只是某部分不同'时，把原方案步骤+修改点一起写入 description 直接调用。"
    "用户说'确定'/'新建'/'做'后立即调用，不要追问。仅当用户明确要求创建方案时调用。",
    {
        "type": "object",
        "properties": {"description": {"type": "string", "description": "实验方案的自然语言描述。包含实验名称、目的、关键参数（体系体积/温度/循环数等）。如果基于现有方案修改，把原步骤和修改点都写进去。"}},
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
    "列出所有可选的实验方案，包含方案名称、步骤总数和来源。用户问有哪些实验、想做什么实验时调用。不要用于查询当前正在进行的实验/当前步骤。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="search", title="查看可选实验方案", experiment_command=True,
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
    "search_protocols",
    "按关键词搜索实验方案。用户说'我要做XXX'/'做个XXX'时调用本工具搜索，"
    "不要用 list_protocols 翻全部方案。会先查这个关键词的历史偏好（用户上次选了哪个），"
    "如果有偏好直接返回 auto_select=true；只有一个匹配也返回 auto_select=true。"
    "多个匹配时返回所有候选并标记 need_choice=true——此时把候选展示给用户选，不要自己选。",
    {
        "type": "object",
        "properties": {"keyword": {"type": "string", "description": "搜索关键词，从用户消息中提取，如'磷酸缓冲液'、' Bradford'、'质粒提取'"}},
        "required": ["keyword"],
        "additionalProperties": False,
    },
    kind="search", title="搜索方案「{keyword}」", experiment_command=True,
    present=lambda a, r: (
        [f"偏好命中：{r['matches'][0]['title']}（上次选过，已自动选定）"]
        if r.get("auto_select") and r["matches"]
        else [f"找到 {len(r['matches'])} 个匹配方案，请让用户选择："]
        + [f"  {chr(65+i)}：{m['title']}（{m['total_steps']}步，{m['first_step']}）"
           + (" ← 上次选过" if m.get("preferred") else "")
           for i, m in enumerate(r["matches"])]
        if r.get("need_choice")
        else [f"没有找到匹配「{a['keyword']}」的方案"]
    ),
)
def _search_protocols(keyword):
    # 1. 查历史偏好
    pref_id = get_protocol_preference(keyword)
    # 2. 模糊搜索方案库
    kw = keyword.strip().lower()
    all_protos = domain.protocols().list_all()
    matches = []
    for p in all_protos:
        title_lower = p.title.lower()
        pid_lower = p.protocol_id.lower()
        if kw in title_lower or kw in pid_lower or title_lower in kw:
            matches.append(p)
    # 也用标题里的关键词做 token 级匹配
    if not matches:
        kw_tokens = set(kw.replace("缓冲液", "").split())
        for p in all_protos:
            title_tokens = set(p.title.lower().split())
            if kw_tokens & title_tokens:
                matches.append(p)
    # 去重
    seen_ids = set()
    deduped = []
    for p in matches:
        if p.protocol_id not in seen_ids:
            seen_ids.add(p.protocol_id)
            deduped.append(p)
    matches = deduped
    # 3. 构建结果
    result_list = []
    for p in matches:
        step1 = p.steps[0] if p.steps else None
        result_list.append({
            "protocol_id": p.protocol_id,
            "title": p.title,
            "total_steps": len(p.steps),
            "source": p.source,
            "first_step": step1.title if step1 else "",
            "preferred": (pref_id == p.protocol_id) if pref_id else False,
        })
    # 4. 判断动作
    if not matches:
        return {"matches": [], "auto_select": False, "need_choice": False,
                "action": f"没有匹配「{keyword}」的方案"}
    # 偏好命中：方案还在
    if pref_id and any(m["protocol_id"] == pref_id for m in result_list):
        return {"matches": result_list, "auto_select": True, "need_choice": False,
                "preferred_protocol_id": pref_id,
                "action": f"偏好命中，直接调 select_protocol(protocol_id=\"{pref_id}\", search_keyword=\"{keyword}\")"}
    # 只有一个匹配
    if len(matches) == 1:
        return {"matches": result_list, "auto_select": True, "need_choice": False,
                "action": f"唯一匹配，直接调 select_protocol(protocol_id=\"{result_list[0]['protocol_id']}\", search_keyword=\"{keyword}\")"}
    # 多个匹配
    return {"matches": result_list, "auto_select": False, "need_choice": True,
            "action": f"有 {len(matches)} 个匹配，展示给用户选，用户选完后调 select_protocol(protocol_id=..., search_keyword=\"{keyword}\")"}


@tool(
    "select_protocol",
    "选择一份实验方案开始实验；protocol_id 传 null 表示自由记录模式（不按方案）。"
    "用户说要做某个实验时调用。如果之前调过 search_protocols，把搜索关键词传到 search_keyword，"
    "系统会记住这个偏好，下次同样的关键词自动选定。不要用于查看当前实验进度/当前步骤。",
    {
        "type": "object",
        "properties": {"protocol_id": {"type": ["string", "null"],
                                       "description": "方案ID，null表示自由记录"},
                       "search_keyword": {"type": "string",
                                          "description": "用户搜索时用的关键词（如'磷酸缓冲液'），用于记住偏好。如果之前没调过 search_protocols 就不传。"}},
        "required": ["protocol_id"],
        "additionalProperties": False,
    },
    kind="execute", title="选择实验方案 {protocol_id}", experiment_command=True,
    present=lambda a, r: ([f"已进入自由记录模式"] if r.get("mode") == "free" else
                          [f"方案：{r['protocol']['title']}",
                           f"共 {r['protocol']['total_steps']} 步，当前第 {r['step']['number']} 步：{r['step']['title']}"]),
)
def _select_protocol(protocol_id=None, search_keyword=None):
    result = domain.step_view(domain.start_session(protocol_id or None))
    if result.get("mode") == "free":
        result["ui_action"] = {
            "type": "switch_interaction_mode",
            "mode": "free",
            "view": "run",
        }
    else:
        result["ui_action"] = {
            "type": "switch_interaction_mode",
            "mode": "protocol",
            "protocol_id": result["protocol"]["id"],
            "view": "run",
        }
    if search_keyword and protocol_id:
        save_protocol_preference(search_keyword, protocol_id)
        result["preference_saved"] = True

    # 选定方案时开始新实验记录会话，让实验本立刻出现这个实验。
    # 不做这一步，用户选了方案但还没记录口述时，实验本里看不到这条实验。
    if isinstance(result, dict) and result.get("mode") == "protocol":
        try:
            from database.lab_record_store import start_new_session, save_record
            start_new_session()
            proto = result.get("protocol", {})
            step = result.get("step", {})
            save_record({
                "transcript": f"开始实验：{proto.get('title', '')}，共{proto.get('total_steps', 0)}步。",
                "entities": {},
                "evaluation": {},
                "step": {
                    "number": step.get("number", 1),
                    "title": step.get("title", ""),
                    "protocol": proto.get("title", ""),
                    "action": "started",
                },
            })
        except Exception:
            pass

    return result


@tool(
    "create_reagent_prep_from_text",
    "根据用户的自然语言描述创建一条试剂配置。仅当用户明确要求创建配方时调用；不要用于修改已有配置。",
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
    "列出所有可配制的试剂/缓冲液配方。用户在实验前问“要先配什么”“有什么溶液要准备”时调用。不要用于查看当前实验进度。",
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
    "用户问“怎么配 50× TAE”“PBS 怎么配”时调用。不要用于列出所有配方。",
    {
        "type": "object",
        "properties": {"reagent_prep_id": {"type": "string", "description": "试剂配置ID"}},
        "required": ["reagent_prep_id"],
        "additionalProperties": False,
    },
    kind="read", title="查看试剂配方：{reagent_prep_id}", experiment_command=True,
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
    "按ID更新一条试剂配置。仅当用户明确要求“改一下配方/修正某某配法”时调用；不要用于查询。",
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
    "按ID删除一条试剂配置。仅当用户明确要求“删掉这个配方”时调用；不要用于查询或修改其他配置。",
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
    "查看当前所选实验方案在开始前需要准备哪些试剂/缓冲液/仪器/耗材，并输出实验前准备清单。"
    "用户问“做这个实验前要先配什么/准备什么/清单”时调用。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="read", title="实验前准备清单", experiment_command=True,
    artifact_type="checklist",
    present=lambda a, r: _checklist_present_lines(r),
)
def _get_protocol_prep_requirements():
    from checklist_service import generate_protocol_checklist
    state = domain.session()
    protocol_id = state.selection.protocol.protocol_id if state.selection.protocol else None
    if not protocol_id:
        return {"protocol_id": None, "protocol_title": "", "items": [], "message": "当前没有选择实验方案。"}
    checklist = generate_protocol_checklist(protocol_id)
    checklist["message"] = None
    return checklist


def _checklist_present_lines(r: dict) -> list[str]:
    """把准备清单转成聊天里可读的勾选清单。"""
    if r.get("message"):
        return [r["message"]]
    lines = [f"请准备：{r.get('protocol_title') or ''}".strip()]
    reagents = r.get("reagents") or []
    if reagents:
        lines.append("试剂/缓冲液：")
        for item in reagents:
            mark = "☑" if item.get("found_in_storage") else "☐"
            suffix = ""
            if not item.get("found_in_storage") and item.get("available_prep"):
                suffix = " → 可配"
            lines.append(f"{mark} {item.get('name')}{suffix}")
    equipment = r.get("equipment") or []
    if equipment:
        lines.append("仪器：")
        for item in equipment:
            lines.append(f"☐ {item}")
    consumables = r.get("consumables") or []
    if consumables:
        lines.append("耗材：")
        for item in consumables:
            lines.append(f"☐ {item}")
    preps = r.get("prep_requirements") or []
    if preps:
        lines.append("需提前配制：")
        for item in preps:
            lines.append(f"☐ {item.get('name_zh') or item.get('name') or ''}")
    safety = r.get("safety") or []
    if safety:
        lines.append("安全提醒：")
        for item in safety[:4]:
            lines.append(f"⚠ 第{item.get('step')}步：{item.get('note')}")
    if not any([reagents, equipment, consumables, preps, safety]):
        lines.append("当前没有可用的准备材料清单。")
    return lines


@tool(
    "generate_prep_bench",
    "根据当前实验方案自动生成一张准备台：AI 推断这个实验按什么计量（体积/样本数/反应数…）、"
    "推荐默认规模，并把试剂/仪器/耗材分成「现成可用/需现配/缺料」三态，为现配项标注用量、耗时和时效。"
    "用户说'帮我准备''做这个实验要先弄什么''生成准备表'时调用。这是实验开始前的准备阶段。",
    {
        "type": "object",
        "properties": {
            "scale_input": {
                "type": ["string", "null"],
                "description": "用户口头说的规模，如'做50个样本''配200mL'。不传则由AI推断默认值。",
            }
        },
        "additionalProperties": False,
    },
    kind="read", title="生成实验准备台", experiment_command=True,
    artifact_type="prep_bench",
    present=lambda a, r: _prep_bench_present_lines(r),
)
def _generate_prep_bench(scale_input=None):
    from prep_bench_service import generate_prep_bench

    state = domain.session()
    protocol = state.selection.protocol if state.selection else None
    if not protocol:
        return {"prep_run_id": None, "message": "当前没有选择实验方案，无法生成准备台。"}
    bench = generate_prep_bench(
        protocol_id=protocol.protocol_id,
        scale_input=scale_input,
    )
    bench["ui_action"] = {"type": "navigate", "view": "run"}
    return bench


def _prep_bench_present_lines(r: dict) -> list[str]:
    """把准备台转成聊天里可读的摘要。"""
    if r.get("message"):
        return [r["message"]]
    lines = []
    if r.get("scale_unit"):
        basis = r.get("scale_basis", "")
        lines.append(
            f"计量方式：{r.get('scale_unit')}"
            + (f"（{basis}）" if basis else "")
            + f" · 推荐规模：{r.get('default_scale', '未指定')}"
        )
    summary = r.get("summary") or {}
    lines.append(
        f"共 {summary.get('total', 0)} 项："
        f"✅{summary.get('ready', 0)} 现成 · "
        f"🔬{summary.get('prep_now', 0)} 需配 · "
        f"⚠️{summary.get('missing', 0)} 缺料"
    )
    _SENSITIVITY_LABELS = {"prechill": "需预冷", "overnight": "需过夜", "fresh": "现配现用"}
    for item in (r.get("items") or [])[:12]:
        mark = {"ready": "✅", "prep_now": "🔬", "missing": "⚠️"}.get(
            item.get("state", ""), "☐"
        )
        qty = item.get("quantity")
        qty_str = f" {qty}" if qty else ""
        timing = item.get("time_sensitivity", "normal")
        tag = ""
        if timing and timing != "normal":
            tag = " [" + _SENSITIVITY_LABELS.get(timing, timing) + "]"
        minutes = item.get("estimated_minutes")
        mins = f" 约{minutes}分钟" if minutes else ""
        lines.append(f"{mark} {item.get('name', '')}{qty_str}{mins}{tag}")
    return lines


@tool(
    "mark_prep_item",
    "在准备台上把某一项标记为「有」或「没有」。用户说'这个我有了''BSA标准品有了'"
    "'那个缺'时调用。item_name 是试剂/耗材名称，state 是 have（有）或 missing（没有）。"
    "调用后返回更新后的准备台。",
    {
        "type": "object",
        "properties": {
            "item_name": {
                "type": "string",
                "description": "准备台上某一项的名称（如'BSA标准品''Bradford工作液'），尽量跟准备台上的名字对应",
            },
            "state": {
                "type": "string",
                "enum": ["have", "missing"],
                "description": "have=标记为已有（打勾）；missing=标记为缺料",
            },
        },
        "required": ["item_name", "state"],
        "additionalProperties": False,
    },
    kind="execute", title="标记准备项：{item_name}", experiment_command=True,
    present=lambda a, r: _prep_bench_present_lines(r) if r.get("items") else [r.get("message", "操作完成")],
)
def _mark_prep_item(item_name, state):
    from prep_bench_service import get_prep_bench, update_prep_item

    bench = get_prep_bench(None)
    if bench is None:
        return {"message": "当前没有准备台，请先说'帮我准备'生成一张。"}
    target = _find_prep_item_by_name(bench["items"], item_name)
    if target is None:
        return {"message": f"准备台上没有找到「{item_name}」，请确认名称是否匹配。"}
    updated = update_prep_item(target["prep_run_item_id"], state)
    updated["ui_action"] = {"type": "navigate", "view": "run"}
    return updated


def _find_prep_item_by_name(items, query):
    """在准备台条目里模糊匹配名称。"""
    import re
    q = re.sub(r"\s+", "", str(query or "").lower())
    if not q:
        return None
    # 精确匹配优先
    for item in items:
        if re.sub(r"\s+", "", str(item.get("name", "")).lower()) == q:
            return item
    # 子串匹配
    for item in items:
        name = re.sub(r"\s+", "", str(item.get("name", "")).lower())
        if name and (q in name or name in q):
            return item
    return None


@tool(
    "set_prep_bench_status",
    "标记准备台整体状态：ready（准备就绪，开始实验）或 skipped（跳过准备，直接开始）。"
    "用户说'准备好了''开始实验''不用准备了直接开始'时调用。",
    {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["ready", "skipped"],
                "description": "ready=准备就绪；skipped=跳过准备",
            },
        },
        "required": ["status"],
        "additionalProperties": False,
    },
    kind="execute", title="准备台：{status}", experiment_command=True,
    present=lambda a, r: [
        f"准备台已标记为{'就绪' if r.get('status') == 'ready' else '跳过'}",
        f"方案：{r.get('protocol_title', '')}",
    ] if r.get("status") else [r.get("message", "操作完成")],
)
def _set_prep_bench_status(status):
    from prep_bench_service import get_prep_bench, set_prep_run_status

    bench = get_prep_bench(None)
    if bench is None:
        return {"message": "当前没有准备台，请先说'帮我准备'生成一张。"}
    updated = set_prep_run_status(bench["prep_run_id"], status)
    updated["ui_action"] = {"type": "navigate", "view": "run"}
    return updated


@tool(
    "rescale_prep_bench",
    "修改准备台的实验规模（如'做20个样本''配1升'），AI 按新规模重算每项用量。"
    "用户说'我要做20个样本''改成配1升''规模改大一点'时调用。user_scale 是用户描述的新规模。",
    {
        "type": "object",
        "properties": {
            "user_scale": {
                "type": "string",
                "description": "用户要求的新规模，如'20个样本''1 L''48孔'",
            },
        },
        "required": ["user_scale"],
        "additionalProperties": False,
    },
    kind="execute", title="缩放准备台：{user_scale}", experiment_command=True,
    present=lambda a, r: _prep_bench_present_lines(r) if r.get("items") else [r.get("message", "操作完成")],
)
def _rescale_prep_bench(user_scale):
    from prep_bench_service import get_prep_bench, rescale_prep_bench

    bench = get_prep_bench(None)
    if bench is None:
        return {"message": "当前没有准备台，请先说'帮我准备'生成一张。"}
    updated = rescale_prep_bench(bench["prep_run_id"], user_scale)
    updated["ui_action"] = {"type": "navigate", "view": "run"}
    return updated


@tool(
    "get_current_step",
    "查看当前实验进行到第几步、当前步骤标题和操作要点、安全提示。用户问“现在做到哪了”时调用。"
    "注意：没有任何字段是必填的，不要催促用户补录，不要声称“还需要记录某某”。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="read", title="查看当前步骤", experiment_command=True,
    present=lambda a, r: ([f"当前为自由记录模式"] if r.get("mode") == "free" else
                          [f"第 {r['step']['number']}/{r['protocol']['total_steps']} 步：{r['step']['title']}",
                           f"状态：{r['step'].get('status', '')}"]
                          + ([f"已记录：{'、'.join(r['step']['recorded']) or '无'}"
                              ] if r.get("step", {}).get("recorded") else [])
                          + [f"⚠ {s['name']}：{'；'.join(s['statements'][:1])}" for s in r.get("safety", []) if s.get("critical")]),
)
def _get_current_step():
    view = domain.step_view(domain.session())
    view["progress"] = domain.step_progress_view(domain.session())
    return view


@tool(
    "move_step",
    "推进实验步骤。action 取 next（下一步）、prev（上一步）或 jump（跳到指定步）。"
    "用户说做完了/下一步/继续时调 next 推进；用户说回到上一步/搞错了/退回去时调 prev 回退。"
    "jump 时必须传 step_number。推进后告诉用户下一步做什么，并提示可以回退。",
    {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["next", "prev", "jump"]},
            "step_number": {"type": ["integer", "null"], "description": "仅 jump 时需要，next/prev 传 null 或省略"},
        },
        "required": ["action"],
        "additionalProperties": False,
    },
    kind="execute", title="推进步骤 {action}", experiment_command=True,
    present=lambda a, r: ([f"当前为自由记录模式"] if r.get("mode") == "free" else
                          [f"已到第 {r['step']['number']}/{r['protocol']['total_steps']} 步：{r['step']['title']}"]),
)
def _move_step(action, step_number=None):
    # 记录步骤推进前的状态，用于写入实验本
    pre_view = domain.step_view(domain.session())
    pre_step = None
    pre_protocol = None
    if isinstance(pre_view, dict) and pre_view.get("mode") == "protocol":
        pre_step = pre_view.get("step", {})
        pre_protocol = pre_view.get("protocol", {})

    result = domain.step_view(domain.move(action, step_number))
    result["ui_action"] = {"type": "navigate", "view": "run"}

    # 推进步骤时自动写一条实验记录，让实验本能看到进度变化。
    # 不做这一步，用户说"下一步"但本轮没有口述数据时，实验本一直是空的。
    if action == "next" and pre_step and isinstance(result, dict) and result.get("mode") == "protocol":
        try:
            from database.lab_record_store import save_record
            save_record({
                "transcript": f"已完成第{pre_step['number']}步：{pre_step['title']}",
                "entities": {},
                "evaluation": {},
                "step": {
                    "number": pre_step["number"],
                    "title": pre_step["title"],
                    "protocol": pre_protocol.get("title", ""),
                    "action": "completed",
                },
            })
        except Exception:
            pass

    return result


@tool(
    "navigate_view",
    "打开软件中的指定页面。用户说查看方案、查看安全库、打开设置或返回实验进行中时调用。不要用于处理实验数据或记录操作。",
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
    title="打开页面 {view}", experiment_command=True,
    present=lambda a, r: ["已打开目标页面"],
)
def _navigate_view(view):
    return {"ui_action": {"type": "navigate", "view": view}}


@tool(
    "get_protocol_detail",
    "查看一份实验方案的完整步骤、准备材料和安全提示。"
    "可以传 protocol_id 查任意方案（如从 search_protocols 拿到的 ID）；"
    "不传则自动查当前会话已选定的方案。"
    "当你需要读取已有方案的步骤来创建新方案时，用这个工具读出原文。",
    {
        "type": "object",
        "properties": {"protocol_id": {"type": "string", "description": "要查看的方案ID。不传则查当前会话的方案。"}},
        "required": [],
        "additionalProperties": False,
    },
    kind="read", experiment_command=True,
    title="查看方案 {protocol_id}",
    present=lambda a, r: [f"方案：{r['protocol']['title']}", f"共 {len(r['steps'])} 步"],
)
def _get_protocol_detail(protocol_id=None):
    if not protocol_id:
        # 未传 protocol_id 时，自动解析当前会话的方案
        view = domain.step_view(domain.session())
        if isinstance(view, dict) and view.get("mode") == "protocol":
            protocol_id = str(view["protocol"]["id"])
        else:
            raise ValueError("当前没有选定的方案。请传 protocol_id 指定要查看的方案。")
    result = domain.protocol_detail(protocol_id)
    result["ui_action"] = {"type": "navigate", "view": "protocols"}
    return result


@tool(
    "add_protocol_step",
    "在指定实验方案的某一步之后添加新步骤。仅当用户明确要求添加步骤时调用；不要用于修改已有步骤。",
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
    "修改指定实验方案中某一步的标题、说明或安全提示。只传需要修改的字段；仅当用户明确要求修改时调用，不要用于添加/删除步骤。",
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
    "删除指定实验方案中的某一步。仅当用户明确要求删除时调用；不要用于修改其他步骤。",
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
    "用户描述刚做了什么操作或测到什么数据时调用。用户说做完了/完成了/下一步时，"
    "如果本轮有新数据就先调本工具记录，然后调 move_step(action=\"next\") 推进步骤。"
    "不要把闲聊或提问当记录。",
    {
        "type": "object",
        "properties": {"transcript": {"type": "string", "description": "用户口述原文"}},
        "required": ["transcript"],
        "additionalProperties": False,
    },
    kind="execute", title="记录实验口述", experiment_command=True,
    present=lambda a, r: ([f"抽取：{'、'.join(f'{k}={v}' for k, v in r['entities'].items()) or '未抽到结构化字段'}"]
                          + [f"⚠ 偏差：{d['field']} 实际 {d['actual_value']}，方案 {d['protocol_value']}" for d in r["deviations"]]),
)
def _record_observation(transcript):
    result = _build_record_service().record(RecordCommand(transcript=transcript))
    observation = result.observation_result
    saved_evaluation = result.saved_record.get("evaluation")
    evaluation = saved_evaluation if isinstance(saved_evaluation, dict) else {}
    entities = dict(
        observation.entities
        if observation is not None
        else result.saved_record.get("entities") or {}
    )
    deviations = [
        dict(d) if not isinstance(d, dict) else d
        for d in (
            observation.deviations
            if observation is not None
            else evaluation.get("deviations") or ()
        )
    ]
    payload = {
        "transcript": (
            observation.transcript
            if observation is not None
            else result.saved_record["transcript"]
        ),
        "entities": entities,
        "recorded_fields": sorted(entities.keys()),
        "deviations": deviations,
    }
    # 同步抽取的实体到 domain 步骤进度追踪器。
    # 不做这一步，_progress 只记字段名不记值，下一轮上下文看不到实测值，
    # 模型会反复追问"实际称了多少克"。
    if entities:
        try:
            step = domain.session().current_step()
            if step is not None:
                domain.record_step_fields(step.step_number, dict(entities), bool(deviations))
        except Exception:  # noqa: BLE001
            pass
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


def _start_timer_immediate(duration_seconds, label=None):
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
        "recorded": False,
        "pending": False,
    }
    with _timers_lock:
        _timers[timer_id] = timer
    return timer


@tool(
    "start_timer",
    "启动一个计时器。用户说“计时X分钟/秒”“帮我定时”时调用。自动按识别到的名称和时长开始，不需要用户再确认。只负责计时，不要用本工具记录实验数据或修改方案。",
    {
        "type": "object",
        "properties": {
            "duration_seconds": {"type": "integer", "description": "计时时长（秒）"},
            "label": {"type": "string", "description": "计时器名称，如：水浴加热"},
        },
        "required": ["duration_seconds"],
        "additionalProperties": False,
    },
    kind="execute", title="启动计时器 {label}", experiment_command=True,
    present=lambda a, r: [f"计时器已启动：{r['label'] or '未命名'}，{r['duration_seconds']} 秒后结束"],
)
def _start_timer(duration_seconds, label=None):
    """Agent 工具入口：直接开始计时，不需要用户点击确认。"""
    return _start_timer_immediate(duration_seconds, label=label)


def _request_timer(duration_seconds, label=None):
    """由 Agent 工具调用：先创建待确认计时器，等用户在弹窗确认后才真正开始。"""
    if not isinstance(duration_seconds, int) or duration_seconds <= 0:
        raise ValueError("duration_seconds 必须是正整数")
    timer_id = str(uuid.uuid4())[:8]
    now = datetime.now()
    timer = {
        "timer_id": timer_id,
        "label": label or "",
        "duration_seconds": duration_seconds,
        "started_at": now.isoformat(timespec="seconds"),
        "end_at": None,
        "recorded": False,
        "pending": True,
        "created_at": now.isoformat(timespec="seconds"),
    }
    with _timers_lock:
        _timers[timer_id] = timer
    return timer


def accept_pending_timer(
    timer_id: str,
    *,
    label: str | None = None,
    duration_seconds: int | None = None,
) -> dict:
    """确认待确认计时器，真正开始倒计时；可同时修改名称/时长。"""
    with _timers_lock:
        timer = _timers.get(timer_id)
        if timer is None or not timer.get("pending"):
            raise ValueError("没有找到待确认的计时器。")
        if duration_seconds is not None:
            if not isinstance(duration_seconds, int) or duration_seconds <= 0:
                raise ValueError("duration_seconds 必须是正整数")
            timer["duration_seconds"] = duration_seconds
        if label is not None:
            timer["label"] = (label or "").strip()
        timer["pending"] = False
        timer["end_at"] = (
            datetime.now() + timedelta(seconds=timer["duration_seconds"])
        ).isoformat(timespec="seconds")
        return dict(timer)


@tool(
    "check_timer",
    "查询计时器剩余时间。用户问“还有多久”“时间到了吗”时调用。只读，不修改计时器；不要用于记录实验数据。",
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
        if timer.get("pending"):
            return {
                "found": True,
                "timer_id": timer_id,
                "label": timer["label"],
                "duration_seconds": timer["duration_seconds"],
                "started_at": timer.get("started_at"),
                "end_at": None,
                "remaining_seconds": timer["duration_seconds"],
                "finished": False,
                "pending": True,
            }
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
            "pending": False,
        }


def list_active_timers() -> list[dict]:
    """返回全部计时器的活动/待确认/结束快照，供 API 和前端轮询。"""
    now = datetime.now()
    with _timers_lock:
        result = []
        for timer_id, timer in list(_timers.items()):
            if timer.get("pending"):
                result.append({
                    "timer_id": timer_id,
                    "label": timer["label"],
                    "duration_seconds": timer["duration_seconds"],
                    "started_at": timer.get("started_at"),
                    "end_at": None,
                    "remaining_seconds": timer["duration_seconds"],
                    "finished": False,
                    "pending": True,
                    "created_at": timer.get("created_at"),
                })
                continue
            end_at = datetime.fromisoformat(timer["end_at"])
            remaining = max(0, int((end_at - now).total_seconds()))
            finished = remaining <= 0
            # 计时器到点后自动写一条实验记录（只写一次，内存标记防重）。
            if finished and not timer.get("recorded"):
                timer["recorded"] = True
                label = timer.get("label") or "未命名计时器"
                try:
                    save_record({
                        "transcript": f"[计时结束] {label}",
                        "entities": {
                            "timer_id": timer_id,
                            "duration_seconds": timer["duration_seconds"],
                            "label": label,
                        },
                        "evaluation": {},
                        "extraction_source": "timer",
                        "step": None,
                        "at": now.isoformat(timespec="seconds"),
                    })
                except Exception:
                    # 自动记录失败不应影响计时器展示；下轮不再重试。
                    pass
            result.append({
                "timer_id": timer_id,
                "label": timer["label"],
                "duration_seconds": timer["duration_seconds"],
                "started_at": timer["started_at"],
                "end_at": timer["end_at"],
                "remaining_seconds": remaining,
                "finished": finished,
                "pending": False,
            })
        result.sort(key=lambda item: (1 if item.get("pending") else 0, item.get("end_at") or "", item["timer_id"]))
        return result


def create_timer(duration_seconds: int, label: str | None = None) -> dict:
    """API/前端创建计时器；与 Agent 工具共用同一个内存注册表。"""
    return _start_timer_immediate(duration_seconds, label=label)


def cancel_timer(timer_id: str) -> bool:
    with _timers_lock:
        if timer_id not in _timers:
            return False
        _timers.pop(timer_id, None)
        return True


# ---------------- 时间引擎 ----------------

@tool(
    "generate_schedule",
    "根据当前实验方案生成时间规划。分析每一步是「动手操作」还是「机器等待」，"
    "计算总耗时和等待窗口，给出等待期间可以做的并行建议。"
    "用户说'帮我安排时间''怎么做最快''要多久'时调用。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="read", title="时间规划", experiment_command=True,
    present=lambda a, r: format_schedule_brief(r),
)
def _generate_schedule():
    """读取当前方案的步骤，生成时间规划。"""
    from harness_context import get_current_protocol_id
    protocol_id = get_current_protocol_id()
    if not protocol_id:
        return {
            "protocol_id": None,
            "protocol_title": "",
            "total_steps": 0,
            "total_seconds": 0,
            "total_label": "未知",
            "active_seconds": 0,
            "passive_seconds": 0,
            "active_label": "未知",
            "passive_label": "未知",
            "passive_ratio": 0,
            "passive_windows": [],
            "timeline": [],
        }
    return generate_schedule(protocol_id)


@tool(
    "get_remaining_schedule",
    "从当前步骤开始计算剩余时间规划。用户做到一半问'还有多久''剩下要多久'"
    "'后面还要做什么'时调用。会标注接下来的步骤和下一个等待窗口。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="read", title="剩余时间规划", experiment_command=True,
    present=lambda a, r: format_remaining_brief(r),
)
def _get_remaining_schedule():
    """从当前步骤开始计算剩余时间规划。"""
    from harness_context import get_current_protocol_id
    protocol_id = get_current_protocol_id()
    if not protocol_id:
        return {
            "protocol_id": None, "protocol_title": "", "from_step": 0,
            "remaining_seconds": 0, "remaining_label": "未选定方案",
            "remaining_active_seconds": 0, "remaining_passive_seconds": 0,
            "remaining_active_label": "", "remaining_passive_label": "",
            "next_passive_window": None, "timeline": [],
        }
    # 获取当前步骤号
    state = domain.session()
    from_step = 1
    if state.selection.has_protocol:
        try:
            cs = state.current_step()
            if cs:
                from_step = cs.step_number
        except Exception:
            pass
    return get_remaining_schedule(protocol_id, from_step)


@tool(
    "start_step_timer",
    "为当前步骤启动计时器。从方案时间画像自动获取该步骤的预计时长。"
    "到达被动等待步骤（离心、孵育、电泳等）时调用——不需要用户说具体时长，"
    "系统会从方案里查出。如果当前步没有时长数据则返回提示。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="execute", title="启动步骤计时器", experiment_command=True,
    present=lambda a, r: r.get("present_lines", [f"已启动计时器：{r.get('label','')}，{r.get('duration_seconds',0)} 秒"]),
)
def _start_step_timer():
    """为当前被动步骤自动启动计时器。"""
    from harness_context import get_current_protocol_id
    protocol_id = get_current_protocol_id()
    if not protocol_id:
        return {"ok": False, "message": "当前没有选定方案。"}

    state = domain.session()
    if not state.selection.has_protocol:
        return {"ok": False, "message": "当前没有选定方案。"}

    step = state.current_step()
    if not step:
        return {"ok": False, "message": "无法确定当前步骤。"}

    profile = get_step_profile(protocol_id, step.step_number)
    if not profile:
        return {"ok": False, "message": f"第{step.step_number}步没有时间画像数据。"}

    duration = profile.get("duration_seconds", 0)
    if not duration or duration < 10:
        return {
            "ok": False,
            "message": f"第{step.step_number}步「{step.title}」预计耗时太短（{duration}秒），不需要计时器。",
        }

    wait_type = profile.get("wait_type", "active")
    label = step.title
    timer = _start_timer_immediate(duration, label=label)
    result = dict(timer)
    result["ok"] = True
    result["wait_type"] = wait_type
    result["step_number"] = step.step_number
    result["parallel_suggestions"] = profile.get("parallel_suggestions", [])
    # 为 present 提供
    lines = [f"计时器已启动：{label}，{_duration_label(duration)}后结束"]
    sugg = profile.get("parallel_suggestions", [])
    if sugg:
        lines.append(f"等待期间可做：{'、'.join(sugg[:3])}")
    result["present_lines"] = lines
    return result


def _duration_label(seconds: int) -> str:
    """秒 → 可读时长（与 time_engine._fmt_duration 一致）。"""
    if seconds <= 0:
        return "0分钟"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    parts = []
    if hours:
        parts.append(f"{hours}小时")
    if minutes:
        parts.append(f"{minutes}分钟")
    if secs and not hours:
        parts.append(f"{secs}秒")
    return "".join(parts) if parts else "0分钟"


@tool(
    "plan_multi_protocols",
    "分析多个实验方案的时间安排，检测设备冲突，给出交错优化建议。"
    "用户说'今天要做A和B''帮我安排两个实验''怎么做最快'时调用。"
    "传入 protocol_ids 数组。",
    {
        "type": "object",
        "properties": {
            "protocol_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要规划的方案 ID 列表",
            },
        },
        "required": ["protocol_ids"],
        "additionalProperties": False,
    },
    kind="read", title="跨实验规划", experiment_command=True,
    present=lambda a, r: format_multi_protocol_brief(r),
)
def _plan_multi_protocols(protocol_ids):
    return plan_multi_protocols(protocol_ids)


@tool(
    "plan_clock_schedule",
    "按用户作息时间做时钟规划：把每个步骤投射到真实钟点，标出午饭/下班/过夜节点。"
    "用户说'我9点开始''几点能做完''来得及午饭前做吗'时调用。"
    "work_start 是开始时间（HH:MM），lunch_start/lunch_end 是午休，work_end 是下班。"
    "如果用户没说全部时间，用默认值（09:00/12:00-13:00/18:00）。",
    {
        "type": "object",
        "properties": {
            "work_start": {"type": "string", "description": "开始时间 HH:MM，如 09:00", "default": "09:00"},
            "lunch_start": {"type": "string", "description": "午休开始 HH:MM", "default": "12:00"},
            "lunch_end": {"type": "string", "description": "午休结束 HH:MM", "default": "13:00"},
            "work_end": {"type": "string", "description": "下班时间 HH:MM", "default": "18:00"},
        },
        "additionalProperties": False,
    },
    kind="read", title="时钟规划", experiment_command=True,
    present=lambda a, r: r.get("summary_lines", ["无法生成时钟规划。"]),
)
def _plan_clock_schedule(work_start="09:00", lunch_start="12:00", lunch_end="13:00", work_end="18:00"):
    from harness_context import get_current_protocol_id
    protocol_id = get_current_protocol_id()
    if not protocol_id:
        return {"summary_lines": ["当前没有选定方案。请先选定一个实验方案。"]}
    return plan_clock_schedule(
        protocol_id,
        work_start=work_start or "09:00",
        lunch_start=lunch_start or "12:00",
        lunch_end=lunch_end or "13:00",
        work_end=work_end or "18:00",
    )


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


# ---------------- 知识库检索（引物表等共享表格） ----------------

@tool(
    "search_knowledge_base",
    "搜索实验室知识库（已上传的共享表格，如引物表、抗体表、细胞系表等）。"
    "用户问'XX的引物是什么''查一下知识库''我们有没有XX的记录'时调用。"
    "传入搜索关键词即可跨所有表格全文检索。",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词，如基因名、引物名、抗体名等"},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    kind="read", title="搜索知识库：{query}", experiment_command=True,
    present=lambda a, r: (
        [f"找到 {r['count']} 条匹配记录"]
        + [
            f"「{item['table_name']}」" + "："
            + "、".join(f"{k}={v}" for k, v in list(item['data'].items())[:4])
            for item in r["results"][:5]
        ]
        if r.get("count")
        else [f"知识库中没有匹配「{a['query']}」的记录"]
    ),
)
def _search_knowledge_base(query):
    from database.db import get_connection

    raw = str(query or "").strip()
    if not raw:
        return {"count": 0, "results": [], "query": query}

    import re as _re
    keywords = [w for w in _re.split(r'[\s,，;；、]+', raw) if w]
    if not keywords:
        keywords = [raw]

    with get_connection() as conn:
        tables_map = {t["id"]: dict(t) for t in conn.execute("SELECT * FROM kb_tables").fetchall()}
        results = []
        seen = set()
        for t_id, t in tables_map.items():
            row_data = conn.execute(
                "SELECT data_json FROM kb_rows WHERE table_id=? ORDER BY row_index LIMIT 5000",
                (t_id,),
            ).fetchall()
            for rd in row_data:
                blob = rd["data_json"]
                if not all(kw.lower() in blob.lower() for kw in keywords):
                    continue
                data = json.loads(blob)
                key = t_id + blob
                if key in seen:
                    continue
                seen.add(key)
                results.append({
                    "table_id": t_id,
                    "table_name": t.get("name", ""),
                    "columns": json.loads(t.get("columns_json") or "[]"),
                    "data": data,
                })
                if len(results) >= 20:
                    break
            if len(results) >= 20:
                break

    return {"query": query, "count": len(results), "results": results}


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


# ---------------- 比例换算计算 ----------------

@tool(
    "calculate_proportion",
    "按参考配方比例换算本次用量。用户给出参考用量、参考体积和本次目标体积时调用；"
    "只计算比例，不把参考值当成本次实际值。",
    {
        "type": "object",
        "properties": {
            "reference_quantity": {"type": "number", "description": "参考用量数值"},
            "reference_unit": {"type": "string", "description": "参考用量单位，如 g、mL"},
            "reference_volume": {"type": "number", "description": "参考配方体积"},
            "target_volume": {"type": "number", "description": "本次目标体积"},
            "volume_unit": {"type": "string", "enum": ["L", "mL"], "description": "参考体积和目标体积的单位"},
        },
        "required": ["reference_quantity", "reference_unit", "reference_volume", "target_volume"],
        "additionalProperties": False,
    },
    kind="read", title="比例换算：{reference_quantity}{reference_unit} → {target_volume}{volume_unit}", experiment_command=True,
    present=lambda a, r: [
        f"参考：{r['reference_quantity']} {r['reference_unit']} / {r['reference_volume']} {r['volume_unit']}",
        f"本次：{r['quantity']} {r['reference_unit']} / {r['target_volume']} {r['volume_unit']}",
        r["formula"],
    ],
)
def _calculate_proportion(reference_quantity, reference_unit, reference_volume, target_volume, volume_unit="mL"):
    quantity = float(reference_quantity)
    base_volume = float(reference_volume)
    requested_volume = float(target_volume)
    if quantity < 0 or base_volume <= 0 or requested_volume <= 0:
        raise ValueError("用量必须不小于 0，体积必须大于 0")
    unit = "L" if str(volume_unit or "mL").strip().lower() == "l" else "mL"
    scaled = quantity * requested_volume / base_volume
    return {
        "reference_quantity": quantity,
        "reference_unit": str(reference_unit or "").strip(),
        "reference_volume": base_volume,
        "target_volume": requested_volume,
        "volume_unit": unit,
        "quantity": round(scaled, 6),
        "formula": f"{quantity} × {requested_volume} ÷ {base_volume} = {round(scaled, 6)} {str(reference_unit or '').strip()}",
        "instruction": f"按比例计算，本次应取约 {round(scaled, 6)} {str(reference_unit or '').strip()}；这是计算值，实际以现场称量/测量为准。",
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
    "查看/搜索储存库物品。用户问“我存了什么/种子在哪/冰箱里有什么/查储存库”时调用。只读；不要用于修改/删除物品。",
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
    "向储存库新增一个存储物品（溶液/种子/DNA/试剂等）。用户说“储存一个种子/入库/放到储存库”时调用。仅创建；不要用于修改/删除已有物品。",
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
    "修改储存库中某个物品的信息（数量、位置、状态、备注等）。用户说“改一下/移到/取用/丢弃”时调用。仅修改；不要用于新增/删除物品。",
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
    "从储存库删除一个物品。用户说“删掉/丢弃这个”时调用。仅当用户明确要求删除时调用；不要用于查询/修改。",
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
    "查看储存库所有存储位置（冰箱、冰柜、试剂柜、样品柜等）。只读；不要用于修改/新增位置。",
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
    "新增一个存储位置（如冰箱2层、4℃试剂柜）。仅当用户明确要求新增位置时调用；不要用于修改/删除位置。",
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
    "查看储存库统计（总数、7天内到期、已过期）。只读；不要用于修改/删除物品。",
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


# ---------- 社区工具 ----------

def _community_summary(item):
    """把社区条目转成模型可读的简洁摘要。"""
    try:
        content = json.loads(item.get("content_json") or "{}")
    except Exception:
        content = {}
    if item.get("kind") == "protocol":
        steps = content.get("steps") or []
        first_step = steps[0] if steps else {}
        return {
            "community_entry_id": item.get("id"),
            "kind": "protocol",
            "title": item.get("title"),
            "protocol_id": content.get("protocol_id"),
            "source": content.get("source"),
            "total_steps": len(steps),
            "tags": item.get("tags") or "",
            "author": item.get("author") or "",
            "downloads": item.get("downloads") or 0,
            "first_step": first_step.get("title") or "",
            "first_instruction": (first_step.get("instruction") or "")[:300],
        }
    if item.get("kind") == "reagent_prep":
        name = content.get("name_zh") or item.get("title")
        return {
            "community_entry_id": item.get("id"),
            "kind": "reagent_prep",
            "title": item.get("title"),
            "name_zh": name,
            "purpose": (content.get("purpose") or "")[:300],
            "tags": item.get("tags") or "",
            "author": item.get("author") or "",
            "downloads": item.get("downloads") or 0,
        }
    return {
        "community_entry_id": item.get("id"),
        "kind": item.get("kind"),
        "title": item.get("title"),
        "tags": item.get("tags") or "",
        "author": item.get("author") or "",
        "downloads": item.get("downloads") or 0,
    }


@tool(
    "search_community",
    "在社区模板库中搜索实验方案或试剂配方。用户希望找现成的实验方案、社区方案、模板、试剂配方时调用；"
    "可按关键词 search 标题/标签/作者。只读，不会导入。",
    {
        "type": "object",
        "properties": {
            "q": {"type": "string", "description": "搜索关键词，如 RNA、ELISA、PBS、细胞培养"},
            "kind": {"type": "string", "enum": ["protocol", "reagent_prep"], "description": "只搜方案或只搜试剂配方，默认全部"},
            "limit": {"type": "integer", "description": "最多返回条数，默认 20"},
        },
        "required": [],
        "additionalProperties": False,
    },
    kind="search", title="搜索社区模板：{q}",
    present=lambda a, r: [
        f"找到 {len(r)} 条",
        *[f"{x.get('title')} · {x.get('kind')} · {x.get('total_steps') or ''}步" for x in r[:5]],
    ],
)
def _search_community(q="", kind="", limit=20):
    items = _storage_crud.list_community_entries(
        q=q or "", kind=kind or "", limit=max(1, min(int(limit or 20), 50))
    )
    return [_community_summary(item) for item in items]


@tool(
    "import_community_entry",
    "把社区中的一条方案或试剂配方导入本地方案库/试剂配置库。用户看到搜索结果后明确说“用这个/导入这个/保存这个”时调用。"
    "必须先先用 search_community 搜索并拿到 community_entry_id，不要猜测编号。",
    {
        "type": "object",
        "properties": {
            "community_entry_id": {"type": "integer", "description": "社区条目 id，来自 search_community 返回的 community_entry_id"},
        },
        "required": ["community_entry_id"],
        "additionalProperties": False,
    },
    kind="execute", title="导入社区模板：{community_entry_id}",
    present=lambda a, r: [
        f"已导入：{r.get('title')}",
        f"类型：{r.get('kind')}",
    ],
)
def _import_community_entry(community_entry_id):
    row = _storage_crud.get_community_entry(int(community_entry_id))
    if not row:
        raise ValueError("找不到该社区条目，请先用 search_community 搜索。")
    content = json.loads(row.get("content_json") or "{}")
    kind = row.get("kind")
    if kind == "protocol":
        # 复制一份并给新 id，避免覆盖本地已有方案
        content["protocol_id"] = _community_new_id(content.get("protocol_id", ""), "protocol")
        saved = domain.add_protocol(content)
    elif kind == "reagent_prep":
        content["reagent_prep_id"] = _community_new_id(content.get("reagent_prep_id", ""), "reagent_prep")
        saved = domain.add_reagent_prep(content)
    else:
        raise ValueError("未知社区类型：" + str(kind))
    _storage_crud.increment_community_downloads(row["id"])
    return {
        "ok": True,
        "kind": kind,
        "title": row.get("title"),
        "saved": saved,
        "community_entry_id": row["id"],
    }


@tool(
    "web_search",
    "在公开互联网上搜索实验方案/试剂配方信息。仅当本地方案库、本地试剂配置库、社区模板库、知识库都找不到，"
    "用户又确实需要某个配方/方法时调用。优先用 search_knowledge_base 查本地知识库（引物表等），"
    "只有本地查不到才用本工具联网搜。只读，不会自动保存。返回搜索结果（标题/网址/摘要）。"
    "\n\n搜索技巧：缩写词（如 SOB、LB、TB）要加上完整英文名或中文用途说明，"
    "例如 'SOB medium Super Optimal Broth recipe' 或 'LB 培养基配方 tryptone'，"
    "避免被搜索引擎当成普通英文单词。",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词。缩写要加全称，如 'SOB medium Super Optimal Broth composition per liter'、'LB 培养基配方 tryptone yeast extract'"},
            "limit": {"type": "integer", "description": "最多返回几条，默认5"}
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    kind="search", title="联网搜索：{query}",
    present=lambda a, r: [f"联网找到 {len(r)} 条结果："] + [
        f"{i}. {x.get('title','')}（{x.get('url','')}）" for i, x in enumerate(r[:5], start=1)
    ],
)
def _web_search(query, limit=5):
    from web_search_service import web_search
    try:
        return web_search(query, limit=max(1, min(int(limit or 5), 10)))
    except RuntimeError as error:
        raise ValueError(str(error))


@tool(
    "web_search_and_save_recipe",
    "当本地和社区都没有某个试剂/缓冲液配方，用户又需要时，联网搜索网页并保存为一条「网络检索（临时）」配方。"
    "会真实抓取网页、把内容整理成配方落库，并保留来源网址。用户说'网上查一下这个配方''联网找找XX怎么配''本地没有，上网搜一个保存'时调用。"
    "成功后可直接用于配制流程。"
    "\n\n搜索技巧：缩写词（如 SOB、LB、TB）要加上完整英文名或用途说明，"
    "否则搜索引擎可能返回无关结果（如 SOB 被当成英文单词'啜泣'）。",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "要查的配方关键词。缩写要加全称，如 'SOB medium Super Optimal Broth recipe'、'10x TBE buffer composition'"},
            "url": {"type": "string", "description": "可选：如果用户已给出具体网址，直接抓这个网址；不填就自动搜索"},
            "description": {"type": "string", "description": "可选：用户补充的要求，如 '要500mL、不含EDTA'，会帮助挑选网页"},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    kind="execute", title="联网查配方：{query}",
    present=lambda a, r: [
        f"已保存：{r.get('name_zh') or '未知'}",
        f"来源：{r.get('source') or '未知'}",
        f"网页：{r.get('source_url') or '无'}",
        f"共 {len(r.get('steps') or [])} 个配制步骤",
    ],
)
def _web_search_and_save_recipe(query, url="", description=""):
    from web_search_service import save_web_reagent_prep
    try:
        return save_web_reagent_prep(
            query=query,
            url=url or "",
            description=description or "",
        )
    except RuntimeError as error:
        raise ValueError(str(error))
    except Exception as error:
        raise ValueError(f"联网保存配方失败：{error}")


def _community_new_id(base_id: str, kind: str) -> str:
    """生成不会与本地现有方案/配方冲突的新 id。"""
    import re as _re
    try:
        existing = (
            {p.protocol_id for p in domain.protocols().list_all()}
            if kind == "protocol"
            else {p.reagent_prep_id for p in domain.reagent_preps().list_all()}
        )
    except Exception:
        existing = set()
    slug = _re.sub(r"[^A-Za-z0-9_.-]+", "-", str(base_id or "")).strip("-") or ("community-protocol" if kind == "protocol" else "community-prep")
    if slug not in existing:
        return slug
    index = 2
    while f"{slug}-community-{index}" in existing:
        index += 1
    return f"{slug}-community-{index}"


# ---------- 试剂配置流程工具（小型分支 protocol） ----------

def _flow_conversation_id() -> str:
    """试剂配制流程的稳定会话键。

    以前从磁盘文件读取 current-conversation-id.txt，结果经常和真实会话不同步，
    导致"配置写错会话"。现在改用稳定常量：单用户助手只有一个活动会话，
    配制流程挂在会话上，不再随聊天会话漂移。
    """
    return "lab-session"


def _flow_present_lines(flow: dict) -> list[str]:
    if not flow:
        return ["当前没有进行中的试剂配置流程。"]
    steps = flow.get("steps") or []
    current = int(flow.get("current_index") or 0)
    sub_index = int(flow.get("current_sub_index") or 0)
    sub_steps = flow.get("sub_steps") or []
    sub_count = int(flow.get("current_sub_count") or len(sub_steps) or 1)
    step_text = flow.get("current_step_text") or (steps[current] if steps and current < len(steps) else "")
    name = flow.get("name_zh") or flow.get("prep_id") or "试剂配置"
    status = flow.get("status") or "running"
    if status == "completed" or (steps and current >= len(steps)):
        return [f"✅ {name} 配置完成，全部 {len(steps)} 步已做完。"]
    # 子步骤是否已被状态机记录（sub_count>1 说明当前大步骤已被拆分）
    decomposed = sub_count > 1
    header = f"📋 {name}（第 {current + 1}/{len(steps)} 步"
    if decomposed:
        header += f"，小步骤 {sub_index + 1}/{sub_count}"
    header += "）"
    lines = [header]
    lines.append("")
    if decomposed:
        # 已拆分：当前小步骤是模型唯一要说的内容
        current_sub = flow.get("step") or (sub_steps[sub_index] if sub_index < len(sub_steps) else step_text)
        lines.append(f"▶ 当前小步骤（{sub_index + 1}/{sub_count}）：{current_sub}")
        if sub_index + 1 < sub_count:
            lines.append("")
            lines.append(f"本大步骤还有 {sub_count - sub_index - 1} 个小步骤没做。用户说做好了后调用 advance_reagent_prep_flow 进入下一个小步骤（仍在同一大步骤内）。")
        else:
            lines.append("")
            lines.append("这是本大步骤的最后一个小步骤。用户说做好了后调用 advance_reagent_prep_flow 进入下一个大步骤。")
    else:
        # 未拆分：展示大步骤原文，并提示 AI 若含多个动作就先拆分落库
        lines.append(f"▶ 当前步骤原文：{step_text}")
        lines.append("")
        lines.append("⚠️ 如果这一步里包含多个独立动作（例如一次称取好几种试剂、或称取+溶解连在一起），")
        lines.append("请先调用 set_reagent_prep_substeps 把它拆成一个个小步骤——每条小步骤只含一个动作。")
        lines.append("拆分会写进记录，之后 advance 会按记录逐个小步骤推进，不会跳步、也不会漂移。")
        lines.append("如果这一步只有一个动作，无需拆分，直接引导用户做完后调 advance_reagent_prep_flow。")
    # 计算提示
    focus = flow.get("step") or step_text
    has_quantity = bool(re.search(r"\d+(?:\.\d+)?\s*(g|mg|mL|ml|mol|克|毫升|升)", focus))
    has_calc_word = any(w in focus for w in ("称取", "量取", "稀释", "浓度", "定容"))
    if has_quantity or has_calc_word:
        lines.append("")
        lines.append("💡 涉及称量/浓度且用户需求与配方参考值不同时，先调 calculate_solution_prep 或 calculate_proportion 算出本次实际用量再说。")
    # 剩余大步骤仅列标题
    remaining = steps[current + 1:] if current + 1 < len(steps) else []
    if remaining:
        lines.append("")
        lines.append(f"后续还有 {len(remaining)} 个大步骤（等当前大步骤全部做完后再说）：")
        for i, s in enumerate(remaining):
            brief = s[:30] + "…" if len(s) > 30 else s
            lines.append(f"  {current + 2 + i}. {brief}")
    return lines


@tool(
    "start_reagent_prep_flow",
    "启动某个试剂配方/缓冲液的逐步配制流程（相当于一个小型分支 protocol）。"
    "用户说“开始配 PBS/开始配置这个试剂/按这个配方开始”时调用。"
    "调用后返回第一步原文——你只需语音描述这第一步。"
    "重要：如果第一步里包含多个独立动作（如“称取 A、B、C”三种试剂），"
    "先调用 set_reagent_prep_substeps 把它拆成一条一个小动作的小步骤列表写进记录，"
    "然后逐个小步骤引导用户——每说完一个等用户确认，再调 advance 进入下一个小步骤。"
    "只有单一步骤（一个动作）时不用拆。涉及称量/浓度时先调 calculate_solution_prep 算用量。",
    {
        "type": "object",
        "properties": {
            "reagent_prep_id": {"type": "string", "description": "试剂配置ID，先用 list_reagent_preps/get_reagent_prep 获取"},
        },
        "required": ["reagent_prep_id"],
        "additionalProperties": False,
    },
    kind="execute", title="开始配置：{reagent_prep_id}",
    present=lambda a, r: _flow_present_lines(r),
)
def _start_reagent_prep_flow(reagent_prep_id):
    from api.reagent_prep import FlowStartPayload, start_flow
    cid = _flow_conversation_id()
    flow = start_flow(FlowStartPayload(conversation_id=cid, reagent_prep_id=reagent_prep_id))
    flow["name_zh"] = flow.get("prep_id") or reagent_prep_id
    try:
        prep = domain.reagent_preps().get_by_id(reagent_prep_id)
        if prep:
            flow["name_zh"] = prep.name_zh
    except Exception:
        pass
    flow["ui_action"] = {"type": "navigate", "view": "reagent_prep"}
    flow["guidance"] = (
        "只描述当前步骤。如果当前步骤原文里含多个独立动作（多个称量/量取连在一起），"
        "先调 set_reagent_prep_substeps 拆成小步骤写进记录，再逐个引导。"
        "每个小步骤做完只是口头确认；全部小步骤做完才调 advance_reagent_prep_flow 进入下一个大步骤。"
        "涉及称量/浓度且与参考值不同时先调 calculate_solution_prep。"
    )
    return flow


@tool(
    "set_reagent_prep_substeps",
    "把当前试剂配制步骤拆分成一条一个小动作的小步骤列表，写进状态机记录。"
    "当某个步骤包含多个独立动作（如“称取胰化蛋白胨、酵母提取物、NaCl”三种试剂，或“称取+溶解”连在一起）时调用。"
    "拆分后 advance 会按记录逐个小步骤推进，避免跳步或多轮漂移。"
    "每条小步骤只描述一个动作；不要把整个配方所有步骤都塞进来，只拆当前这一大步。",
    {
        "type": "object",
        "properties": {
            "step_substeps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "当前大步骤拆成的小步骤，每条一个动作，例如 [\"称取胰化蛋白胨 2 g 放入烧杯\",\"称取酵母提取物 0.5 g 放入同一烧杯\",\"称取 NaCl 0.05 g 放入同一烧杯\"]",
            }
        },
        "required": ["step_substeps"],
        "additionalProperties": False,
    },
    kind="execute", title="拆分当前步骤",
    present=lambda a, r: _flow_present_lines(r),
)
def _set_reagent_prep_substeps(step_substeps):
    from api.reagent_prep import FlowSubstepsPayload, set_substeps
    cid = _flow_conversation_id()
    flow = set_substeps(FlowSubstepsPayload(conversation_id=cid, step_substeps=step_substeps))
    try:
        prep = domain.reagent_preps().get_by_id(flow.get("prep_id"))
        if prep:
            flow["name_zh"] = prep.name_zh
    except Exception:
        pass
    flow["guidance"] = (
        "已记录当前大步骤的小步骤。现在只引导用户做第 1 个小步骤；"
        "用户说做好了就调 advance_reagent_prep_flow 进入下一个小步骤（仍在同一大步骤内）。"
    )
    return flow


@tool(
    "show_reagent_prep_flow",
    "查看当前正在进行的试剂配制流程（当前进度、剩余步骤）。当用户问“配到哪一步/这个试剂配制流程”时调用。只读。",
    {"type": "object", "properties": {}, "additionalProperties": False},
    kind="search", title="查看试剂配制进度",
    present=lambda a, r: _flow_present_lines(r),
)
def _show_reagent_prep_flow():
    from api.reagent_prep import FlowStartPayload, current_flow
    cid = _flow_conversation_id()
    try:
        flow = current_flow(cid)
    except Exception:
        return {"active": False, "message": "当前没有进行中的试剂配置流程。"}
    try:
        prep = domain.reagent_preps().get_by_id(flow.get("prep_id"))
        if prep:
            flow["name_zh"] = prep.name_zh
    except Exception:
        pass
    return flow


@tool(
    "advance_reagent_prep_flow",
    "推进当前试剂配制流程。"
    "状态机记录了当前大步骤的小步骤（如果有）：调用 next 会先在当前大步骤内走到下一个小步骤，"
    "走完最后一个小步骤才进入下一个大步骤。所以“做好了/下一步”一律调 next，状态机会自动判断是进下一个小步骤还是下一个大步骤。"
    "用户确认整个配置结束时调 complete。",
    {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["next", "complete"], "description": "next=完成当前小步骤，进入下一个（小步骤或大步骤由状态机决定）；complete=结束整个配制"}
        },
        "required": ["action"],
        "additionalProperties": False,
    },
    kind="execute", title="推进试剂配置：{action}",
    present=lambda a, r: _flow_present_lines(r) if r.get("status") != "completed" else [f"配置完成：{r.get('name_zh') or r.get('prep_id')}"],
)
def _advance_reagent_prep_flow(action="next"):
    from api.reagent_prep import FlowMovePayload, move_flow
    cid = _flow_conversation_id()
    flow = move_flow(FlowMovePayload(conversation_id=cid, action=action))
    try:
        prep = domain.reagent_preps().get_by_id(flow.get("prep_id"))
        if prep:
            flow["name_zh"] = prep.name_zh
    except Exception:
        pass
    if flow.get("status") != "completed":
        flow["guidance"] = (
            "只描述当前这一步的操作（返回的 step 字段）。如果进入了新的大步骤且它含多个动作，"
            "先调 set_reagent_prep_substeps 拆分；否则直接引导。不要提前说出后续步骤。"
        )
    return flow
