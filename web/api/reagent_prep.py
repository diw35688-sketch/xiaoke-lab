# -*- coding: utf-8 -*-
"""试剂配置库接口：查询、上传与逐步配置流程。"""

from contextlib import closing
import json
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import domain
import lab_tools
import llm_bridge
from database.db import get_connection

router = APIRouter(prefix="/reagent-prep", tags=["试剂配置库"])


class UploadPayload(BaseModel):
    reagent_preps: list


class ImportPayload(BaseModel):
    reagent_prep: dict


class AiDraftPayload(BaseModel):
    text: str


class SaveDraftPayload(BaseModel):
    reagent_prep: dict


class UpdatePrepPayload(BaseModel):
    reagent_prep: dict


class ScalePrepPayload(BaseModel):
    reagent_prep_id: str
    target_volume: float
    volume_unit: str = "mL"


class FlowStartPayload(BaseModel):
    conversation_id: str
    reagent_prep_id: str


class FlowMovePayload(BaseModel):
    conversation_id: str
    action: str  # next / prev / complete / jump


class FlowSubstepsPayload(BaseModel):
    """AI 把当前步骤拆成的小步骤列表，落进状态机持久记录。"""
    conversation_id: str
    step_substeps: list[str]


def _load_sub_steps(raw: str | None) -> dict:
    """把 sub_steps_json 列安全解析成 {step_index_str: [sub, ...]}。"""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _flow_view(conversation_id: str, prep_id: str) -> dict:
    prep = domain.reagent_preps().get_by_id(prep_id)
    if prep is None:
        raise HTTPException(status_code=404, detail="没有这种试剂配置。")
    steps = list(prep.steps or [])
    prep_view = domain.reagent_prep_view(prep)
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT current_index, current_sub_index, sub_steps_json, status FROM reagent_prep_flows WHERE conversation_id=?",
            (conversation_id,),
        ).fetchone()
    current_index = int(row["current_index"] or 0) if row else 0
    current_sub_index = int(row["current_sub_index"] or 0) if row else 0
    status = (row["status"] if row else "running")
    sub_steps_map = _load_sub_steps(row["sub_steps_json"] if row else None)

    # 当前大步骤的小步骤：若状态机里有记录就用记录，否则整步作为一个小步骤
    current_sub_list = sub_steps_map.get(str(current_index))
    if current_sub_list is None:
        raw = steps[current_index] if steps and current_index < len(steps) else ""
        current_sub_list = [raw] if raw else []
    if current_sub_list and current_sub_index >= len(current_sub_list):
        current_sub_index = 0
    current_step_text = steps[current_index] if steps and current_index < len(steps) else ""
    current_sub = current_sub_list[current_sub_index] if current_sub_list and current_sub_index < len(current_sub_list) else current_step_text

    return {
        "conversation_id": conversation_id,
        "prep_id": prep_id,
        "current_index": current_index,
        "current_sub_index": current_sub_index,
        "status": status,
        "total_steps": len(steps),
        "step": current_sub,
        "current_step_text": current_step_text,
        "current_sub_count": len(current_sub_list),
        "sub_steps": current_sub_list,
        "steps": steps,
        "safety": prep_view.get("safety", []),
    }


@router.post("/calculate")
def calculate_prep(payload: ScalePrepPayload):
    """按配方参考规模计算本次目标体积用量；不修改配方，也不把参考值当实际值。"""
    prep = domain.reagent_preps().get_by_id(payload.reagent_prep_id)
    if prep is None:
        raise HTTPException(status_code=404, detail="没有这种试剂配置。")
    target_unit = "L" if payload.volume_unit.strip().lower() == "l" else "mL"
    target_volume = float(payload.target_volume)
    if target_volume <= 0:
        raise HTTPException(status_code=400, detail="目标体积必须大于 0。")

    reference_volume = _parse_volume(prep.target_volume)
    if reference_volume is None:
        raise HTTPException(status_code=400, detail="该配方没有可识别的参考体积，无法按比例换算。")
    reference_value, reference_unit = reference_volume
    if reference_unit != target_unit:
        if reference_unit == "L":
            reference_value *= 1000
            reference_unit = "mL"
        else:
            reference_value /= 1000
            reference_unit = "L"
    # 将配方中的可识别“数值 + 单位”交给统一工具逐项换算。
    quantities = []
    for step in prep.steps:
        for match in re.finditer(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(g|mg|mL|ml|毫升|克)", step):
            q = float(match.group(1))
            unit = "mL" if match.group(2).lower() in {"ml", "毫升"} else ("mg" if match.group(2) == "mg" else "g")
            outcome = lab_tools.call("calculate_proportion", {
                "reference_quantity": q, "reference_unit": unit,
                "reference_volume": reference_value, "target_volume": target_volume,
                "volume_unit": target_unit,
            })
            if outcome.get("ok"):
                quantities.append({"source": step, **outcome["result"]})
    return {
        "reagent_prep_id": prep.reagent_prep_id,
        "name_zh": prep.name_zh,
        "reference_volume": reference_value,
        "reference_volume_unit": reference_unit,
        "target_volume": target_volume,
        "target_volume_unit": target_unit,
        "quantities": quantities,
        "note": "以上是按参考配方比例计算的本次目标用量；实际称量、量取和定容以现场记录为准。",
    }


def _parse_volume(value: str | None):
    if not value:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(mL|ml|L|升|毫升)", str(value))
    if not match:
        return None
    unit = "L" if match.group(2) in {"L", "升"} else "mL"
    return float(match.group(1)), unit


@router.post("/flow/start")
def start_flow(payload: FlowStartPayload):
    prep = domain.reagent_preps().get_by_id(payload.reagent_prep_id)
    if prep is None:
        raise HTTPException(status_code=404, detail="没有这种试剂配置。")
    with closing(get_connection()) as connection, connection:
        connection.execute(
            """INSERT INTO reagent_prep_flows(conversation_id, prep_id, current_index, current_sub_index, sub_steps_json, status, updated_at)
               VALUES(?, ?, 0, 0, '{}', 'running', CURRENT_TIMESTAMP)
               ON CONFLICT(conversation_id) DO UPDATE SET
                 prep_id=excluded.prep_id,
                 current_index=0,
                 current_sub_index=0,
                 sub_steps_json='{}',
                 status='running',
                 updated_at=CURRENT_TIMESTAMP""",
            (payload.conversation_id, payload.reagent_prep_id),
        )
    return _flow_view(payload.conversation_id, payload.reagent_prep_id)


@router.get("/flow/current")
def current_flow(conversation_id: str):
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT prep_id FROM reagent_prep_flows WHERE conversation_id=?",
            (conversation_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="当前没有进行中的配置流程。")
    return _flow_view(conversation_id, row["prep_id"])


@router.post("/flow/move")
def move_flow(payload: FlowMovePayload):
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT prep_id, current_index, current_sub_index, sub_steps_json, status FROM reagent_prep_flows WHERE conversation_id=?",
            (payload.conversation_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="当前没有进行中的配置流程。")
    prep = domain.reagent_preps().get_by_id(row["prep_id"])
    if prep is None:
        raise HTTPException(status_code=404, detail="没有这种试剂配置。")
    steps = list(prep.steps or [])
    index = int(row["current_index"] or 0)
    sub_index = int(row["current_sub_index"] or 0)
    status = row["status"]
    sub_steps_map = _load_sub_steps(row["sub_steps_json"])
    action = payload.action
    if action == "next":
        # 先在当前大步骤的小步骤里推进；走完最后一个才进入下一个大步骤
        current_subs = sub_steps_map.get(str(index))
        if current_subs is not None and sub_index + 1 < len(current_subs):
            sub_index += 1
        else:
            index = min(index + 1, len(steps) - 1) if steps else 0
            sub_index = 0
    elif action == "prev":
        if sub_index > 0:
            sub_index -= 1
        else:
            index = max(index - 1, 0)
            prev_subs = sub_steps_map.get(str(index))
            sub_index = max(len(prev_subs) - 1, 0) if prev_subs else 0
    elif action == "complete":
        status = "completed"
    elif action == "jump":
        pass  # 不支持任意跳转，保持当前
    else:
        raise HTTPException(status_code=400, detail="不支持的配置流程动作。")
    with closing(get_connection()) as connection, connection:
        connection.execute(
            "UPDATE reagent_prep_flows SET current_index=?, current_sub_index=?, status=?, updated_at=CURRENT_TIMESTAMP WHERE conversation_id=?",
            (index, sub_index, status, payload.conversation_id),
        )
    return _flow_view(payload.conversation_id, row["prep_id"])


@router.post("/flow/substeps")
def set_substeps(payload: FlowSubstepsPayload):
    """AI 把当前步骤拆成的小步骤写进状态机，之后 advance 据此确定性推进。"""
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT prep_id, current_index, sub_steps_json FROM reagent_prep_flows WHERE conversation_id=?",
            (payload.conversation_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="当前没有进行中的配置流程。")
    substeps = [str(s).strip() for s in (payload.step_substeps or []) if str(s).strip()]
    if not substeps:
        raise HTTPException(status_code=400, detail="小步骤列表不能为空。")
    sub_steps_map = _load_sub_steps(row["sub_steps_json"])
    sub_steps_map[str(int(row["current_index"] or 0))] = substeps
    with closing(get_connection()) as connection, connection:
        connection.execute(
            "UPDATE reagent_prep_flows SET sub_steps_json=?, current_sub_index=0, updated_at=CURRENT_TIMESTAMP WHERE conversation_id=?",
            (json.dumps(sub_steps_map, ensure_ascii=False), payload.conversation_id),
        )
    return _flow_view(payload.conversation_id, row["prep_id"])


@router.get("")
def list_reagent_preps():
    """全部试剂配置方案。"""
    return {
        "items": [
            domain.reagent_prep_view(prep)
            for prep in domain.reagent_preps().list_all()
        ]
    }


@router.get("/{reagent_prep_id}")
def read_reagent_prep(reagent_prep_id: str):
    """单条试剂配置方案。"""
    prep = domain.reagent_preps().get_by_id(reagent_prep_id)
    if prep is None:
        raise HTTPException(status_code=404, detail="没有这种试剂配置。")
    return domain.reagent_prep_view(prep)


@router.post("/ai-draft")
def ai_draft(payload: AiDraftPayload):
    """用户粘贴/上传文字，AI 生成试剂配置草稿，不落盘。"""
    try:
        return llm_bridge.generate_reagent_prep_draft(payload.text)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/save-draft")
def save_draft(payload: SaveDraftPayload):
    """确认保存 AI 生成的试剂配置草稿。"""
    try:
        return domain.add_reagent_prep(payload.reagent_prep)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.patch("/{reagent_prep_id}")
def update_reagent_prep(reagent_prep_id: str, payload: UpdatePrepPayload):
    """按ID更新一条试剂配置，严格校验。"""
    try:
        return domain.update_reagent_prep(reagent_prep_id, payload.reagent_prep)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.delete("/{reagent_prep_id}")
def delete_reagent_prep(reagent_prep_id: str):
    """删除一条试剂配置。"""
    try:
        return domain.delete_reagent_prep(reagent_prep_id)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/import")
def import_reagent_prep(payload: ImportPayload):
    """社区导入专用：已有相同 reagent_prep_id 时覆盖，否则新增。"""
    try:
        prep_id = (payload.reagent_prep or {}).get("reagent_prep_id", "")
        if prep_id and domain.reagent_preps().get_by_id(prep_id) is not None:
            saved = domain.update_reagent_prep(prep_id, payload.reagent_prep)
        else:
            saved = domain.add_reagent_prep(payload.reagent_prep)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {"ok": True, "saved": saved}


@router.post("/upload")
def upload_reagent_preps(payload: UploadPayload):
    """用户上传试剂配置 JSON 数组，严格校验后写库。"""
    try:
        return domain.add_reagent_preps(payload.reagent_preps)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
