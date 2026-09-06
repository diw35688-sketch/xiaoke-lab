# -*- coding: utf-8 -*-
"""论文/Protocol 文件库接口：上传、解析、持久化，之后可回看并生成方案。"""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

import ocr_bridge
import settings_store
from database.paper_store import (
    PAPER_DIR,
    get_paper,
    list_papers,
    save_paper,
)

router = APIRouter(prefix="/papers", tags=["论文库"])


@router.post("/upload")
async def upload_paper(file: UploadFile = File(...)):
    """上传论文/Protocol 文件，OCR 解析后保存为论文库条目。"""
    try:
        raw = await file.read()
        filename = (file.filename or "").lower()
        settings = settings_store.current()
        if filename.endswith(".pdf"):
            text = ocr_bridge.ocr_pdf(settings, raw)
        elif filename.endswith((".png", ".jpg", ".jpeg")):
            text = ocr_bridge.ocr_image(settings, raw)
        else:
            raise HTTPException(
                status_code=400,
                detail="只支持 PDF / PNG / JPG / JPEG 文件。",
            )
        drafts = ocr_bridge.extract_protocol_drafts(settings, text)
        source_name = (file.filename or "论文上传").replace("\\", "/").split("/")[-1]
        for draft in drafts:
            if not draft.get("source"):
                draft["source"] = f"论文上传：{source_name}"

        PAPER_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c for c in source_name if c.isalnum() or c in "._- ").strip() or "paper"
        target = PAPER_DIR / f"{safe_name}"
        # 避免同名覆盖
        index = 1
        while target.exists():
            stem = Path(safe_name).stem
            suffix = Path(safe_name).suffix or ""
            target = PAPER_DIR / f"{stem}_{index}{suffix}"
            index += 1
        with target.open("wb") as out:
            out.write(raw)

        paper = save_paper(
            title=source_name,
            filename=source_name,
            file_path=str(target.relative_to(Path(__file__).resolve().parent.parent)),
            ocr_text=text,
            drafts=drafts,
        )
        return {"paper": paper, "drafts": drafts, "ocr_text": text}
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))


@router.get("")
def papers():
    return {"items": list_papers()}


@router.get("/{paper_id}")
def paper_detail(paper_id: int):
    item = get_paper(paper_id)
    if item is None:
        raise HTTPException(status_code=404, detail="论文不存在。")
    try:
        import json
        item["drafts"] = json.loads(item.get("drafts_json") or "[]")
    except Exception:
        item["drafts"] = []
    return item
