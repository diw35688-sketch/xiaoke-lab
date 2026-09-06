# -*- coding: utf-8 -*-
"""调试日志接口：查看 uvicorn 输出/错误日志尾部，便于排查线上问题。"""
import sys
from pathlib import Path

from fastapi import APIRouter, Query

from fastapi.responses import PlainTextResponse

if getattr(sys, "frozen", False):
    REPO_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_LOG = REPO_ROOT / "uvicorn_out.log"
ERR_LOG = REPO_ROOT / "uvicorn_err.log"
EVENT_LOG = REPO_ROOT / "debug_events.log"

router = APIRouter(prefix="/api", tags=["调试日志"])


def _tail(path: Path, limit: int) -> str:
    if not path.exists():
        return ""
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    lines = data.splitlines()
    return "\n".join(lines[-limit:])


@router.get("/logs", response_class=PlainTextResponse)
def logs(limit: int = Query(default=200, ge=10, le=2000)):
    out = _tail(OUT_LOG, limit)
    err = _tail(ERR_LOG, limit)
    events = _tail(EVENT_LOG, limit)
    sections = []
    if out:
        sections.append("===== stdout =====\n" + out)
    if err:
        sections.append("===== stderr =====\n" + err)
    if events:
        sections.append("===== 前端行为 telemetry =====\n" + events)
    if not sections:
        return "(暂无日志文件)"
    return "\n\n".join(sections)
