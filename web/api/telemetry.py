# -*- coding: utf-8 -*-
"""前端行为遥测接口：把用户使用的关键功能上报到调试日志。"""
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger("web.api.telemetry")

if getattr(sys, "frozen", False):
    REPO_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    REPO_ROOT = Path(__file__).resolve().parents[2]
EVENT_LOG = REPO_ROOT / "debug_events.log"

router = APIRouter(prefix="/api", tags=["调试遥测"])


class TelemetryPayload(BaseModel):
    event: str
    data: dict[str, Any] | None = None


@router.post("/telemetry")
def telemetry(payload: TelemetryPayload):
    line = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "event": payload.event,
        "data": payload.data or {},
    }
    try:
        with EVENT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        # 日志失败不影响业务
        pass
    logger.debug("[TELEMETRY] %s", line)
    return {"ok": True}
