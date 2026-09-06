# -*- coding: utf-8 -*-
"""实验方案接口：选方案、走步骤、按方案做确定性判断与安全提示。"""

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

import domain
import llm_bridge
import ocr_bridge
import settings_store
from database.turn_store import ExperimentStateConflictError, TurnStore
from src.core.protocol_execution_state import (
    ProtocolExecutionState,
    ProtocolStepProgressStatus,
)
from src.core.protocol_navigation import decide_protocol_move
from src.core.reply_coordinator import ReplyCoordinator

router = APIRouter(prefix="/protocols", tags=["实验方案"])
turn_store = TurnStore()


class SelectPayload(BaseModel):
    protocol_id: str | None = None
    conversation_id: str | None = Field(default=None, max_length=128)
    lab_session_id: str | None = Field(default=None, max_length=128)


class MovePayload(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=128)
    lab_session_id: str = Field(min_length=1, max_length=128)
    action: str
    step_number: int | None = None


class EvaluatePayload(BaseModel):
    entities: dict = {}
    transcript: str | None = None


class AiDraftPayload(BaseModel):
    text: str = Field(min_length=5, max_length=2000)


class SaveDraftPayload(BaseModel):
    protocol: dict


class AiEditPayload(BaseModel):
    protocol_id: str
    instruction: str


class SaveAiEditPayload(BaseModel):
    protocol: dict


class UploadPayload(BaseModel):
    protocols: list


class ImportPayload(BaseModel):
    protocol: dict


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
            "deletable": domain.is_deletable_protocol_source(protocol.source),
        })
    return {"protocols": items}

@router.post("/ai-edit")
def ai_edit(payload: AiEditPayload):
    """结合当前方案上下文和用户文字，生成修订后的完整方案草稿。"""
    try:
        detail = domain.protocol_detail(payload.protocol_id)
        raw_protocol = {
            "protocol_id": detail["protocol"]["id"],
            "title": detail["protocol"]["title"],
            "source": detail["protocol"]["source"],
            "version": detail["protocol"]["version"],
            "schema_version": 1,
            "steps": [
                {
                    "step_number": s["number"],
                    "title": s["title"],
                    "instruction": s["instruction"],
                    "protocol_values": s["protocol_values"],
                    "must_record": s["must_record"],
                    "terms": s["terms"],
                    "hazard_note": s["hazard_note"],
                    "field_prompts": s["field_prompts"],
                    "substeps": s["substeps"],
                }
                for s in detail["steps"]
            ],
        }
        draft = llm_bridge.generate_protocol_edit_draft(
            raw_protocol, payload.instruction
        )
        return {"draft": draft}
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))


@router.post("/save-ai-edit")
def save_ai_edit(payload: SaveAiEditPayload):
    """保存 AI 修订后的完整方案，自动升版本。"""
    try:
        return domain.update_protocol_from_draft(payload.protocol)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


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
        # 论文/Protocol 文件上传：把来源文件名写入草稿 source，用户确认保存后可知出处。
        source_name = (file.filename or "论文上传").replace("\\", "/").split("/")[-1]
        for draft in drafts:
            if not draft.get("source"):
                draft["source"] = f"论文上传：{source_name}"
        return {"ocr_text": text, "drafts": drafts}
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error))


@router.post("/import")
def import_protocol(payload: ImportPayload):
    """社区导入专用：已有相同 protocol_id 时整份覆盖，否则新增。"""
    try:
        saved = domain.upsert_protocol(payload.protocol)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {"ok": True, "saved": saved}


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
def read_session(
    conversation_id: str | None = Query(default=None),
    lab_session_id: str | None = Query(default=None),
):
    """当前会话：已选方案、当前步骤、安全提示。"""
    return _session_view(conversation_id, lab_session_id, include_steps=False)


@router.get("/session/steps")
def session_steps(
    conversation_id: str | None = Query(default=None),
    lab_session_id: str | None = Query(default=None),
):
    """当前会话 + 全部步骤概要，供状态机卡片栏使用。"""
    return _session_view(conversation_id, lab_session_id, include_steps=True)


@router.get("/active-tracks")
def active_tracks():
    """列出所有正在进行中的实验轨道——支持多实验并行展示。

    从 experiment_session_state 表读取所有有步骤进度的 session，
    关联方案标题和记录数，返回每个轨道的进度摘要。
    每个步骤包含简化标题和预估时间（分钟），供时间轴展示。
    """
    import json as _json
    import sqlite3
    from database.db import get_connection

    def simplify_title(title: str, step_vals: dict | None) -> str:
        """把冗长的步骤标题简化为短动词。"""
        if not title:
            return ""
        # 直接映射表：常见实验操作 → 短名
        mapping = {
            "融化感受态细胞": "融化", "加入质粒或连接产物": "加质粒",
            "热激并冰浴": "热激", "复苏转化菌液": "复苏",
            "离心并涂布平板": "涂板",
            "收集细菌培养物": "收集", "重悬细菌沉淀": "重悬",
            "碱性裂解细胞": "裂解", "中和并沉淀杂质": "中和",
            "转移上清液": "转上清", "氯仿抽提": "氯仿",
            "异丙醇沉淀质粒 DNA": "异丙醇", "异丙醇沉淀质粒DNA": "异丙醇",
            "乙醇沉淀质粒 DNA": "乙醇沉", "乙醇沉淀质粒DNA": "乙醇沉",
            "去除沉淀表面液滴": "晾干", "乙醇洗涤并溶解 DNA": "洗涤",
            "乙醇洗涤并溶解DNA": "洗涤", "RNase 处理": "RNase",
            "RNase处理": "RNase", "电泳鉴定质粒 DNA": "电泳",
            "电泳鉴定质粒DNA": "电泳",
            "称量磷酸盐": "称量", "溶解试剂": "溶解",
            "调节酸碱度": "调pH", "转移定容": "定容",
            "混匀标记": "标记",
        }
        if title in mapping:
            return mapping[title]
        action = ""
        if step_vals and step_vals.get("action"):
            action = str(step_vals.get("action", ""))
        if action and len(action) <= 4:
            return action
        # 去括号、去冗余后缀
        t = title.split("（")[0].split("(")[0]
        if len(t) <= 4:
            return t
        for sep in ["并", "后", "以", "使", "，", "、"]:
            if sep in t:
                short = t.split(sep)[0]
                if len(short) <= 4:
                    return short
        return t[:4]

    tracks = []
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT DISTINCT lab_session_id, protocol_step_facts_json, updated_at
               FROM experiment_session_state
               WHERE lab_session_id IS NOT NULL AND lab_session_id != ''
               ORDER BY updated_at DESC""",
        ).fetchall()

    for row in rows:
        lab_session_id = row["lab_session_id"]
        facts_raw = row["protocol_step_facts_json"] or "{}"
        try:
            facts = _json.loads(facts_raw)
        except Exception:
            facts = {}
        protocol_id = facts.get("protocol_id", "")
        current_step = facts.get("current_step_number", 0)
        steps_facts = facts.get("steps", {})
        statuses = facts.get("statuses", {})

        # 方案信息
        title = protocol_id
        short_title = protocol_id
        total_steps = 0
        step_list = []
        if protocol_id:
            try:
                proto = domain.protocols().get_by_id(protocol_id)
                if proto:
                    title = proto.title
                    total_steps = len(proto.steps)
                    short_title = _short_protocol_title(title)
                    for s in proto.steps:
                        step_vals = {}
                        step_facts = steps_facts.get(str(s.step_number), {})
                        vals = step_facts.get("values", {}) if step_facts else {}
                        step_list.append({
                            "n": s.step_number,
                            "title": simplify_title(s.title, None),
                            "status": statuses.get(str(s.step_number), ""),
                            "has_data": bool(vals),
                        })
            except Exception:
                pass

        # 统计已完成步骤
        completed_steps = 0
        for sn, status in statuses.items():
            if status in ("completed", "left_with_pending"):
                completed_steps += 1
        if not completed_steps and steps_facts:
            completed_steps = sum(
                1 for s in steps_facts.values() if s.get("values")
            )

        # 记录数
        record_count = 0
        try:
            with get_connection() as conn2:
                r = conn2.execute(
                    "SELECT COUNT(*) as cnt FROM lab_records WHERE session_id=?",
                    (lab_session_id,),
                ).fetchone()
                record_count = r["cnt"] if r else 0
        except Exception:
            pass

        tracks.append({
            "lab_session_id": lab_session_id,
            "protocol_id": protocol_id,
            "title": title,
            "short_title": short_title,
            "current_step": current_step,
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "record_count": record_count,
            "updated_at": row["updated_at"],
            "steps": step_list,
            "is_completed": total_steps > 0 and current_step >= total_steps and completed_steps >= total_steps,
        })

    # 同一个 lab_session_id 可能在多个 conversation 里出现（如 conv 切换），去重保留最新
    seen = {}
    for t in tracks:
        key = t["lab_session_id"]
        if key not in seen or t["updated_at"] > seen[key]["updated_at"]:
            seen[key] = t
    tracks = list(seen.values())
    tracks.sort(key=lambda t: t["updated_at"], reverse=True)

    # 只返回未完成的轨道（进行中的）
    active = [t for t in tracks if not t["is_completed"]]

    # ---- 追加 AI 排程/计划里还没开始的实验（experiments 表）----
    # 这些实验只写了计划，还没建立 lab_session；前端渲染成"计划"轨道，
    # 点击后走 /protocols/session 启动成为真正的轨道。
    planned = _planned_experiment_tracks()

    # 已开始的轨道里已有相同 protocol 的，就不重复显示"计划"轨
    started_protocols = {t.get("protocol_id") for t in active if t.get("protocol_id")}
    planned = [p for p in planned if p["protocol_id"] not in started_protocols]

    all_tracks = active + planned
    return {"tracks": all_tracks, "count": len(all_tracks)}


def _short_protocol_title(title: str) -> str:
    """把完整方案标题简化为短名。"""
    if not title:
        return ""
    # 直接映射
    mapping = {
        "大肠杆菌质粒 DNA 的提取（碱裂解法）": "质粒提取",
        "感受态细胞转化": "转化",
        "0.1 mol/L pH 7.4 磷酸缓冲液配制": "PBS配制",
        "蛋白质免疫印迹法（Western Blot）": "免疫印迹",
        "蛋白质免疫印迹法": "免疫印迹",
        "RNA 的提取（Trizol 法）": "RNA提取",
        "重组蛋白的表达与纯化": "蛋白纯化",
        "硫酸铜溶液吸光度的测定": "吸光度测定",
        "氢氧化钠标准溶液的标定": "NaOH标定",
        "凝胶层析分离血红蛋白": "凝胶层析",
    }
    if title in mapping:
        return mapping[title]
    # 通用简化：去括号、去常见冗余词
    t = title.split("（")[0].split("(")[0]
    for old in ["的提取", "的配制", "的测定", "大肠杆菌", "碱裂解法", "标准溶液"]:
        t = t.replace(old, "")
    t = t.strip()
    return t[:6] if len(t) > 6 else t


def _planned_experiment_tracks() -> list[dict]:
    """读取 experiments 表里的计划实验（还没开始、有 protocol_id），转成时间轴轨道格式。

    供 run_canvas 的剪映式时间轴展示"计划中"的实验轨道；
    这些轨道没有 lab_session_id，点击后由前端走 /protocols/session 启动。
    """
    import re
    from database import crud

    try:
        experiments = crud.list_experiments(include_completed=True)
    except Exception:
        return []

    planned = []
    for exp in experiments:
        # 已完成的不显示；pending/in_progress 但还没有 lab_session 的都作为"计划/待启动"轨道
        status = str(exp.get("status") or "")
        if status == "completed":
            continue
        notes = str(exp.get("notes") or "")
        m = re.search(r"protocol_id=([^\s;]+)", notes)
        if not m:
            continue
        protocol_id = m.group(1)
        try:
            proto = domain.protocols().get_by_id(protocol_id)
        except Exception:
            continue
        if proto is None:
            continue

        title = getattr(proto, "title", protocol_id)
        total_steps = len(getattr(proto, "steps", ()) or ())
        step_list = []
        for s in (getattr(proto, "steps", ()) or ()):
            step_list.append({
                "n": getattr(s, "step_number", 0),
                "title": _short_step_title(getattr(s, "title", "")),
                "status": "pending",
                "has_data": False,
            })

        planned.append({
            "lab_session_id": "",  # 还没启动，没有 lab_session
            "protocol_id": protocol_id,
            "title": title,
            "short_title": _short_protocol_title(title),
            "current_step": 0,
            "total_steps": total_steps,
            "completed_steps": 0,
            "record_count": 0,
            "updated_at": str(exp.get("start_at") or exp.get("created_at") or ""),
            "steps": step_list,
            "is_completed": False,
            "is_planned": True,
            "experiment_id": exp.get("id"),
            "start_at": str(exp.get("start_at") or ""),
        })
    return planned


def _short_step_title(title: str) -> str:
    """时间轴里步骤块显示用短标题。"""
    if not title:
        return ""
    mapping = {
        "融化感受态细胞": "融化", "加入质粒或连接产物": "加质粒",
        "热激并冰浴": "热激", "复苏转化菌液": "复苏",
        "离心并涂布平板": "涂板",
        "称量磷酸盐": "称量", "溶解试剂": "溶解",
        "调节酸碱度": "调pH", "转移定容": "定容",
        "混匀标记": "标记",
    }
    if title in mapping:
        return mapping[title]
    t = title.split("（")[0].split("(")[0]
    if len(t) <= 4:
        return t
    for sep in ["并", "后", "以", "使", "，", "、"]:
        if sep in t:
            short = t.split(sep)[0]
            if len(short) <= 4:
                return short
    return t[:4]


class ArchiveTrackPayload(BaseModel):
    lab_session_id: str = Field(min_length=1, max_length=200)
    protocol_id: str | None = Field(default=None, max_length=200)


@router.post("/archive-track")
def archive_track(payload: ArchiveTrackPayload):
    """归档一个实验轨道——标记为已完成，从时间轴移除。

    把 experiment_session_state 里对应 session 的步骤标记为 completed。
    """
    import sqlite3
    from database.db import get_connection

    with get_connection() as conn:
        # 找到对应记录
        rows = conn.execute(
            "SELECT lab_session_id, protocol_step_facts_json FROM experiment_session_state WHERE lab_session_id=?",
            (payload.lab_session_id,),
        ).fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail="找不到该实验轨道。")
        for row in rows:
            facts = {}
            try:
                import json as _json
                facts = _json.loads(row["protocol_step_facts_json"] or "{}")
            except Exception:
                pass
            statuses = facts.get("statuses", {})
            # 从方案定义获取总步骤数
            protocol_id = facts.get("protocol_id", "") or payload.protocol_id or ""
            total = facts.get("total_steps", 0)
            if not total and protocol_id:
                try:
                    proto = domain.protocols().get_by_id(protocol_id)
                    if proto:
                        total = len(proto.steps)
                except Exception:
                    pass
            if not total:
                total = facts.get("current_step_number", 1)
            # 所有步骤标记为 completed
            for i in range(1, total + 1):
                statuses[str(i)] = "completed"
            facts["statuses"] = statuses
            facts["current_step_number"] = total
            import json as _json
            conn.execute(
                "UPDATE experiment_session_state SET protocol_step_facts_json=? WHERE lab_session_id=?",
                (_json.dumps(facts, ensure_ascii=False), payload.lab_session_id),
            )
        conn.commit()
    return {"ok": True, "archived": payload.lab_session_id}


@router.get("/session/progress")
def session_progress():
    """当前步骤的进度事实：状态 / 已记录 / 还缺哪些必测字段。

    供移动端卡片「完成本步」按钮核对用——用户点按钮只是"查账"，
    是否完成仍由确定性状态机判定，不提供手点改状态的入口。
    """
    return domain.step_progress_view(domain.session())


class CompletePayload(BaseModel):
    """完成请求：manual=True 表示用户手动确认（直接打勾，人类责任确认）。"""

    manual: bool = False
    conversation_id: str | None = Field(default=None, min_length=1, max_length=128)
    lab_session_id: str | None = Field(default=None, min_length=1, max_length=128)


@router.post("/session/steps/{step_number}/complete")
def complete_step(step_number: int, payload: CompletePayload | None = None):
    """完成当前步（后端状态机判定/落盘，前端无改状态入口）。

    - manual=True：用户手动确认 → 直接打勾（不需要再口述数据）；
    - manual=False：严格校验——必测字段记齐且无偏差才通过，否则拒绝并说明缺什么；
    - 只能完成"当前步"（不能跨步、不能完成未来步）；
    - 本接口不推进步骤（方案 B），翻页仍靠用户明确指示。
    """
    manual = bool(payload and payload.manual)
    conversation_id = payload.conversation_id if payload else None
    lab_session_id = payload.lab_session_id if payload else None
    try:
        if bool(conversation_id) != bool(lab_session_id):
            raise ValueError("conversation_id 和 lab_session_id 必须同时提供。")
        if conversation_id and lab_session_id:
            if not manual:
                raise ValueError("会话级完成接口目前只接受用户手动确认。")
            stored = turn_store.load_experiment_state(
                conversation_id, lab_session_id
            )
            facts = stored.get("protocol_step_facts") or {}
            protocol_id = str(facts.get("protocol_id") or "")
            selected = None
            if protocol_id:
                from src.core.protocol_selection import select_protocol
                from src.core.protocol_session import ProtocolSessionState
                protocol_obj = domain.protocols().get_by_id(protocol_id)
                if protocol_obj is not None:
                    selected = ProtocolSessionState.start(
                        select_protocol(domain.protocols(), protocol_id)
                    )
                    try:
                        selected = selected.jump_to(
                            int(facts.get("current_step_number") or 1)
                        )
                    except Exception:
                        pass
            if selected is None:
                selected = domain.session()
            selected_view = domain.step_view(selected)
            if selected_view.get("mode") != "protocol":
                raise ValueError("当前没有选择实验方案。")
            protocol = selected_view["protocol"]
            execution = ProtocolExecutionState.from_snapshot(
                stored.get("protocol_step_facts"),
                protocol_id=str(protocol["id"]),
                protocol_version=str(protocol["version"]),
                default_step_number=int(selected_view["step"]["number"]),
            )
            if execution.current_step_number != step_number:
                raise ValueError(
                    f"只能完成当前步（第 {execution.current_step_number} 步）"
                )
            completed = execution.with_step(
                execution.step_state(step_number),
                status=ProtocolStepProgressStatus.COMPLETED,
            )
            revision = turn_store.save_protocol_navigation(
                conversation_id=conversation_id,
                lab_session_id=lab_session_id,
                expected_revision=int(stored["revision"]),
                protocol_step_facts=completed.to_snapshot(),
            )
            return {
                "ok": True,
                "step_number": step_number,
                "status": ProtocolStepProgressStatus.COMPLETED.value,
                "progress": {
                    "status": ProtocolStepProgressStatus.COMPLETED.value,
                    "recorded": [],
                    "missing": [],
                },
                "manual": True,
                "revision": revision,
            }
        progress = domain.complete_step(step_number, manual)
    except ValueError as error:
        raise HTTPException(400, str(error))
    return {
        "ok": True,
        "step_number": step_number,
        "status": progress["status"],
        "progress": progress,
        "manual": manual,
    }


@router.post("/session")
def start(payload: SelectPayload):
    """选择方案开始会话；protocol_id 为空表示自由记录模式。

    如果同时传了 conversation_id + lab_session_id，会把这个方案选择
    写入该实验会话的 TurnStore 快照，Harness 才能真正按会话感知。
    """
    try:
        state = domain.start_session(payload.protocol_id or None)
        selected_view = domain.step_view(state)
        if payload.conversation_id and payload.lab_session_id and selected_view.get("mode") == "protocol":
            protocol = selected_view["protocol"]
            execution = ProtocolExecutionState.start(
                protocol_id=str(protocol["id"]),
                protocol_version=str(protocol["version"]),
                step_number=1,
            )
            stored = turn_store.load_experiment_state(
                payload.conversation_id, payload.lab_session_id
            )
            turn_store.save_protocol_navigation(
                conversation_id=payload.conversation_id,
                lab_session_id=payload.lab_session_id,
                expected_revision=int(stored["revision"]),
                protocol_step_facts=execution.to_snapshot(),
            )
            selected_view["revision"] = int(stored["revision"]) + 1
        return selected_view
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.post("/session/move")
def move(payload: MovePayload):
    """按会话事实和问题状态确定性切步，不调用模型。"""
    try:
        stored = turn_store.load_experiment_state(
            payload.conversation_id, payload.lab_session_id
        )
        facts = stored.get("protocol_step_facts") or {}
        protocol_id = str(facts.get("protocol_id") or "")
        selected = None
        if protocol_id:
            from src.core.protocol_selection import select_protocol
            from src.core.protocol_session import ProtocolSessionState
            protocol = domain.protocols().get_by_id(protocol_id)
            if protocol is not None:
                selected = ProtocolSessionState.start(
                    select_protocol(domain.protocols(), protocol_id)
                )
                try:
                    selected = selected.jump_to(
                        int(facts.get("current_step_number") or 1)
                    )
                except Exception:
                    pass
        if selected is None:
            selected = domain.session()
        selected_view = domain.step_view(selected)
        if selected_view.get("mode") != "protocol":
            raise ValueError("当前没有选择实验方案。")
        protocol = selected_view["protocol"]
        execution = ProtocolExecutionState.from_snapshot(
            stored.get("protocol_step_facts"),
            protocol_id=str(protocol["id"]),
            protocol_version=str(protocol["version"]),
            default_step_number=int(selected_view["step"]["number"]),
        )
        current_domain = selected.jump_to(execution.current_step_number)
        current_facts = execution.step_state(execution.current_step_number)
        evaluation = domain.evaluate_for_state(
            current_domain, current_facts.entity_values()
        )
        coordinator = ReplyCoordinator.from_snapshot(
            dict(stored.get("reply_coordinator") or {})
        )
        decision = decide_protocol_move(
            state=execution,
            action=payload.action,
            target_step_number=payload.step_number,
            total_steps=int(protocol["total_steps"]),
            evaluation=evaluation,
            unresolved=coordinator.active_clarifications(),
        )
        if not decision.allowed:
            raise HTTPException(status_code=409, detail={
                "reason": decision.reason,
                "missing_fields": list(decision.missing_fields),
                "blocking_question_numbers": list(
                    decision.blocking_question_numbers
                ),
                "deferred_question_numbers": list(
                    decision.deferred_question_numbers
                ),
                "current_step_number": decision.from_step_number,
                "target_step_number": decision.target_step_number,
            })
        revision = turn_store.save_protocol_navigation(
            conversation_id=payload.conversation_id,
            lab_session_id=payload.lab_session_id,
            expected_revision=int(stored["revision"]),
            protocol_step_facts=decision.state.to_snapshot(),
        )
        state = selected.jump_to(decision.state.current_step_number)
    except Exception as error:
        if isinstance(error, HTTPException):
            raise
        if isinstance(error, ExperimentStateConflictError):
            raise HTTPException(status_code=409, detail=str(error))
        raise HTTPException(status_code=400, detail=str(error))
    result = domain.step_view(state)
    result["revision"] = revision
    result["move"] = {
        "allowed": True,
        "reason": decision.reason,
        "from_step_number": decision.from_step_number,
        "target_step_number": decision.target_step_number,
        "deferred_question_numbers": list(decision.deferred_question_numbers),
    }
    return result


def _session_view(
    conversation_id: str | None,
    lab_session_id: str | None,
    *,
    include_steps: bool,
):
    stored = None
    selected = None
    if conversation_id and lab_session_id:
        stored = turn_store.load_experiment_state(conversation_id, lab_session_id)
        facts = stored.get("protocol_step_facts") or {}
        protocol_id = str(facts.get("protocol_id") or "")
        if protocol_id:
            from src.core.protocol_selection import select_protocol
            from src.core.protocol_session import ProtocolSessionState
            protocol = domain.protocols().get_by_id(protocol_id)
            if protocol is not None:
                selected = ProtocolSessionState.start(
                    select_protocol(domain.protocols(), protocol_id)
                )
                try:
                    selected = selected.jump_to(
                        int(facts.get("current_step_number") or 1)
                    )
                except Exception:
                    pass
    if selected is None:
        selected = domain.session()
    base = (
        domain.all_steps_view(selected)
        if include_steps else domain.step_view(selected)
    )
    if (
        not conversation_id or not lab_session_id
        or base.get("mode") != "protocol"
    ):
        return base
    if stored is None:
        stored = turn_store.load_experiment_state(conversation_id, lab_session_id)
    protocol = base["protocol"]
    execution = ProtocolExecutionState.from_snapshot(
        stored.get("protocol_step_facts"),
        protocol_id=str(protocol["id"]),
        protocol_version=str(protocol["version"]),
        default_step_number=int(base["step"]["number"]),
    )
    scoped = selected.jump_to(execution.current_step_number)
    result = (
        domain.all_steps_view(scoped)
        if include_steps else domain.step_view(scoped)
    )
    # domain.*_view 仍包含旧的进程级 StepProgress 状态；会话化接口必须以
    # TurnStore 中的执行快照为准，否则“完成”写入成功后卡片又会显示 waiting_user。
    def card_status(number: int, fallback: str) -> str:
        status = execution.statuses.get(number)
        if status == ProtocolStepProgressStatus.COMPLETED:
            return "completed"
        if status in {
            ProtocolStepProgressStatus.IN_PROGRESS,
            ProtocolStepProgressStatus.LEFT_WITH_PENDING,
            ProtocolStepProgressStatus.NOT_STARTED,
        }:
            return "waiting_user"
        return fallback

    current = result.get("step")
    if current:
        current["status"] = card_status(
            int(current["number"]), str(current.get("status") or "waiting_user")
        )
        if current["status"] == "completed":
            current["card_type"] = "result"
            current["missing"] = []
    if include_steps:
        for item in result.get("all_steps", []):
            item["status"] = card_status(
                int(item["number"]), str(item.get("status") or "waiting_user")
            )
            if item["status"] == "completed":
                item["card_type"] = "result"
                item["missing"] = []
        result["all_completed"] = bool(result.get("all_steps")) and all(
            item["status"] == "completed" for item in result["all_steps"]
        )
    result["revision"] = int(stored["revision"])
    result["step_statuses"] = {
        str(number): status.value
        for number, status in execution.statuses.items()
    }
    return result


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
            "name_en": reagent.name_en,
            "cas": reagent.cas,
            "formula": reagent.molecular_formula,
            "weight": reagent.molecular_weight,
            "signal_word": reagent.signal_word,
            "critical": reagent.is_critical,
            "codes": list(reagent.critical_codes),
            "statements": [s.text for s in reagent.hazard_statements],
            "critical_statements": [s.text for s in reagent.critical_statements()],
            "source_url": reagent.source_url,
            "review_status": reagent.review_status,
        })
    return {"note": store.authority_note, "count": len(items), "reagents": items}

class AnalyzeReagentsPayload(BaseModel):
    texts: list


class AddStepPayload(BaseModel):
    protocol_id: str
    after_step_number: int | None = None
    title: str
    instruction: str = ""
    hazard_note: str | None = None
    protocol_values: dict | None = None
    must_record: list | None = None
    terms: list | None = None
    field_prompts: dict | None = None
    substeps: list | None = None


class DeleteStepPayload(BaseModel):
    protocol_id: str
    step_number: int


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


@router.delete("/step")
def delete_step(payload: DeleteStepPayload):
    """删除方案中的一个步骤并重新编号。"""
    try:
        return domain.delete_protocol_step(
            payload.protocol_id, payload.step_number
        )
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


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

@router.get("/{protocol_id}")
def read_protocol(protocol_id: str):
    """方案详情：完整步骤、准备材料、安全提示。"""
    try:
        return domain.protocol_detail(protocol_id)
    except Exception as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.delete("/{protocol_id}")
def delete_protocol(protocol_id: str):
    """删除用户自己创建/上传的整份方案；内置/社区方案禁止删除。"""
    try:
        return domain.delete_protocol(protocol_id)
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
