# -*- coding: utf-8 -*-
"""调试日志接口：查看 uvicorn 输出/错误日志尾部，便于排查线上问题。"""
from pathlib import Path

from fastapi import APIRouter, Query

from fastapi.responses import PlainTextResponse

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_LOG = REPO_ROOT / "uvicorn_out.log"
ERR_LOG = REPO_ROOT / "uvicorn_err.log"

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
    if not out and not err:
        return "(暂无日志文件)"
    return f"===== stdout =====\n{out}\n\n===== stderr =====\n{err}"
