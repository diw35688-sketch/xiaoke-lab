# -*- coding: utf-8 -*-
"""文件上传与读取接口：给对话里的 Agent 提供上传文件访问能力。"""
import os
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR.parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/api", tags=["文件"])

ALLOWED_SUFFIXES = {
    ".txt", ".md", ".json", ".csv", ".py", ".js", ".html", ".xml", ".yaml", ".yml",
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".doc", ".docx", ".ppt", ".pptx",
    ".xls", ".xlsx", ".csv", ".log",
}


def safe_upload_path(filename: str) -> tuple[Path, str]:
    path = Path(filename or "upload")
    name = path.name
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型：{suffix or '无扩展名'}")
    file_id = uuid.uuid4().hex[:16]
    stored = UPLOAD_DIR / f"{file_id}_{name}"
    return stored, file_id


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    stored, file_id = safe_upload_path(file.filename or "")
    size = 0
    with stored.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            size += len(chunk)
            if size > 50 * 1024 * 1024:
                out.close()
                stored.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="文件超过 50MB 限制")
    return {
        "ok": True,
        "file_id": file_id,
        "name": Path(file.filename or "upload").name,
        "size": size,
        "path": str(stored).replace("\\", "/"),
    }
