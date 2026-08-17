# -*- coding: utf-8 -*-
"""实验方案接口：选方案、走步骤、按方案做确定性判断与安全提示。"""

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

import domain
import llm_bridge
import ocr_bridge
import settings_store

router = APIRouter(prefix="/protocols", tags=["实验方案"])


class SelectPayload(BaseModel):
    protocol_id: str | None = None


class MovePayload(BaseModel):
    action: str
    step_number: int | None = None


class EvaluatePayload(BaseModel):
    entities: dict = {}
    transcript: str | None = None


class AiDraftPayload(BaseModel):
    text: str = Field(min_length=5, max_length=2000)


class SaveDraftPayload(BaseModel):
    protocol: dict


class UploadPayload(BaseModel):
    protocols: list


@router.get("")
def list_protocols():
    """可选实验方案列表；含自由记录模式。"""
    items = []
    for protocol in domain.protocols().list_all():
        items.append({
            "id": protocol.protocol_id,
            "title": protocol.title,
            "source": protocol.source,
            "version": protocol.version,
            "total_steps": len(protocol.steps),
        })
    return {"protocols": items}

@router.post("/ai-draft")
def ai_draft(payload: AiDraftPayload):
    """用 AI 生成实验方案草稿（不落盘）。"""
    try:
        return llm_bridge.generate_protocol_draft(payload.text)
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"AI 生成方案失败：{error}")



@router.post("/save-draft")
def save_draft(payload: SaveDraftPayload):
    """把 AI 生成的方案草稿确认保存进方案库（严格校验后落盘）。"""
    try:
        saved = domain.add_protocol(payload.protocol)
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"保存方案失败：{error}")
    return {"ok": True, "protocol": saved}


@router.post("/upload-file")
async def upload_file(file: UploadFile = File(...)):
    """上传 PDF/图片版 Protocol，OCR 后拆成多份结构化方案草稿。"""
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
        return {"ocr_text": text, "drafts": drafts}
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))


@router.post("/upload")
def upload_protocols(payload: UploadPayload):
    """用户上传协议 JSON 数组，严格校验后逐份写库。"""
    added = []
    try:
        for item in payload.protocols:
            added.append(domain.add_protocol(item))
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {"added": len(added), "protocols": added}


@router.get("/session")
def read_session():
    """当前会话：已选方案、当前步骤、安全提示。"""
    return domain.step_view(domain.session())


@router.get("/session/steps")
def session_steps():
    """当前会话 + 全部步骤概要，供状态机卡片栏使用。"""
    return domain.all_steps_view(domain.session())


@router.post("/session")
def start(payload: SelectPayload):
    """选择方案开始会话；protocol_id 为空表示自由记录模式。"""
    try:
        state = domain.start_session(payload.protocol_id or None)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
    return domain.step_view(state)


@router.post("/session/move")
def move(payload: MovePayload):
    """显式推进步骤：next / prev / jump。不做模型猜测。"""
    try:
        state = domain.move(payload.action, payload.step_number)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
    return domain.step_view(state)


@router.post("/evaluate")
def evaluate(payload: EvaluatePayload):
    """按当前步骤判断缺什么、有没有偏离方案。不调用大模型。"""
    try:
        return domain.evaluate(payload.entities or {})
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/reagents")
def reagents():
    """试剂安全知识库概览。"""
    store = domain.hazmat()
    items = []
    for reagent in store.all_reagents():
        items.append({
            "name": reagent.name_zh,
            "cas": reagent.cas,
            "critical": reagent.is_critical,
            "codes": list(reagent.critical_codes),
        })
    return {"note": store.authority_note, "count": len(items), "reagents": items}

class AnalyzeReagentsPayload(BaseModel):
    texts: list


class AddStepPayload(BaseModel):
    protocol_id: str
    title: str
    instruction: str = ""
    hazard_note: str | None = None
    protocol_values: dict | None = None
    must_record: list | None = None
    terms: list | None = None
    field_prompts: dict | None = None
    substeps: list | None = None


class StepEditPayload(BaseModel):
    """一个大步骤的可编辑内容。"""

    protocol_id: str
    step_number: int
    title: str | None = None
    instruction: str | None = None
    hazard_note: str | None = None
    protocol_values: dict | None = None
    must_record: list | None = None
    field_prompts: dict | None = None
    substeps: list | None = None


@router.post("/analyze-reagents")
def analyze_reagents(payload: AnalyzeReagentsPayload):
    """识别文字中出现的危化品和试剂配置库条目。"""
    return domain.analyze_reagents(payload.texts)


@router.post("/step")
def add_step(payload: AddStepPayload):
    """在方案末尾添加一个新的大步骤，严格校验后落盘。"""
    try:
        return domain.add_protocol_step(payload.model_dump(exclude_none=True))
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"{type(error).__name__}: {error}")


@router.put("/step")
def edit_step(payload: StepEditPayload):
    """编辑一个大步骤并落盘。

    改动先按契约校验（字段白名单、field_prompts 必须属于 must_record、
    小步序号连续），校验不过则整笔拒绝，不写入半成品。
    """
    try:
        return domain.update_step(payload.model_dump(exclude_none=False))
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"{type(error).__name__}: {error}")


@router.get("/entity-fields")
def entity_fields():
    """可用于 protocol_values / must_record 的实体字段白名单。"""
    return {"fields": domain.entity_field_names()}
