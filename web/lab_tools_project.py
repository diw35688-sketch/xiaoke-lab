# -*- coding: utf-8 -*-
from __future__ import annotations

"""通用项目/研发调研工具（由 lab_tools.py 拆分生成）。"""

import json
import re
import uuid
import threading
from datetime import datetime, timedelta
from pathlib import Path

from lab_tools_registry import (
    _REGISTRY, tool, PresentedToolResult, _attach_artifact,
    present_call, present_result,
    REPO_ROOT, RESULTS_DIR, STEP_IMPROVEMENTS_FILE,
    _timers, _timers_lock, _record_lock,
    domain, llm_bridge, settings_store,
    RecordCommand, SharedRecordService,
    generate_schedule, format_schedule_brief,
    get_remaining_schedule, format_remaining_brief,
    get_step_profile, get_next_passive_window,
    plan_multi_protocols, format_multi_protocol_brief,
    plan_clock_schedule,
    PresentationDeliveryPlan, build_delivery_plan,
    extract_entities,
    current_session_id, list_records, next_segment_id, save_record,
    save_protocol_preference, get_protocol_preference,
)

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


