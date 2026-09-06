# -*- coding: utf-8 -*-
"""网页层到领域层的桥：复用 src/ 里已验证的方案与安全逻辑。

web/ 以自身为工作目录启动，src/ 在仓库根目录，因此这里显式把根目录
加入模块搜索路径。除此之外不做任何业务判断，只负责装配与转译。
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

if getattr(sys, "frozen", False):
    # PyInstaller 冻结运行时：__file__ 是虚拟路径，用 _MEIPASS 定位真实资源根。
    REPO_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.protocol_segment_evaluation import evaluate_segment  # noqa: E402
from src.core.protocol_deviations import detect_protocol_deviations  # noqa: E402
from src.core.protocol_selection import select_protocol  # noqa: E402
from src.core.protocol_session import ProtocolSessionState  # noqa: E402
from src.core.reagent_prep import ReagentPrep, ReagentPrepError  # noqa: E402
from src.llm.schemas import ExperimentEntities  # noqa: E402
from src.storage.hazmat_store import HazmatStore  # noqa: E402
from src.storage.protocol_store import ProtocolStore  # noqa: E402
from src.storage.reagent_prep_store import (  # noqa: E402
    REAGENT_PREP_FILE,
    ReagentPrepStore,
)

from step_progress import StepProgress, card_type_for  # noqa: E402
from database.session_store import (  # noqa: E402
    clear_progress_rows,
    load_session_snapshot,
    load_step_confirmations,
    load_step_progress,
    save_session_snapshot,
    save_step_confirmation,
    save_step_progress,
)

PROTOCOL_FILE = REPO_ROOT / "data" / "protocols" / "undergraduate_basic_protocols.json"
PREP_REQUIREMENTS_FILE = (
    REPO_ROOT / "data" / "protocols" / "prep_requirements.json"
)

_lock = threading.RLock()
_protocol_store = None
_hazmat_store = None
_reagent_prep_store = None
_session: ProtocolSessionState | None = None
_progress = StepProgress()


def protocols() -> ProtocolStore:
    global _protocol_store
    with _lock:
        if _protocol_store is None:
            _protocol_store = ProtocolStore(PROTOCOL_FILE)
        return _protocol_store


def hazmat() -> HazmatStore:
    global _hazmat_store
    with _lock:
        if _hazmat_store is None:
            _hazmat_store = HazmatStore()
        return _hazmat_store


def reagent_preps() -> ReagentPrepStore:
    global _reagent_prep_store
    with _lock:
        if _reagent_prep_store is None:
            _reagent_prep_store = ReagentPrepStore(REAGENT_PREP_FILE)
        return _reagent_prep_store


def session() -> ProtocolSessionState:
    """当前会话状态；首次访问时尝试从持久层恢复（刷新/重启不丢进度）。"""
    global _session
    with _lock:
        if _session is None:
            _session = _restore_session()
        return _session


def _restore_session() -> ProtocolSessionState:
    """从 SQLite 恢复：方案选择 + 当前步 + 各步记录进度。"""
    snapshot = load_session_snapshot()
    protocol_id = snapshot.get("protocol_id") if snapshot else None
    state = ProtocolSessionState.start(select_protocol(protocols(), protocol_id))
    _progress.reset()
    saved_step = snapshot.get("step_number") if snapshot else None
    if saved_step and state.selection.has_protocol:
        try:
            state = state.jump_to(int(saved_step))
        except Exception:
            pass  # 持久数据与方案不匹配时回退到第 1 步，不崩溃
    for step_number, info in load_step_progress().items():
        _progress.restore(step_number, info["recorded"], info["deviation"])
    for step_number in load_step_confirmations():
        _progress.confirm(step_number)
    return state


def _persist_snapshot() -> None:
    """把当前方案与步骤号写进 SQLite 快照。"""
    protocol_id = None
    step_number = None
    if _session is not None and _session.selection.has_protocol:
        protocol_id = _session.selection.protocol.protocol_id
        step_number = _session.step_number
    save_session_snapshot(protocol_id, step_number)


def start_session(selection) -> ProtocolSessionState:
    """selection 为 None 表示自由记录模式。换方案时进度清零并持久化。"""
    global _session
    with _lock:
        _session = ProtocolSessionState.start(select_protocol(protocols(), selection))
        _progress.reset()
        _persist_snapshot()
        clear_progress_rows()
        return _session


def record_step_fields(step_number: int, fields: dict, has_deviation: bool) -> None:
    """把一段口述的实体字段与偏差登记进当前步骤并落盘。"""
    with _lock:
        _progress.record(step_number, fields, has_deviation)
        if step_number is not None:
            save_step_progress(
                step_number,
                {k for k, v in (fields or {}).items() if v},
                bool(has_deviation),
            )


def step_status(step) -> str:
    """当前步骤的确定性状态：completed / error / waiting_user。"""
    with _lock:
        return _progress.status_for(step)


def _step_recorded_missing(step):
    """某一步的已记录字段与还缺字段（同一把锁内读取，保证一致性）。"""
    with _lock:
        return (
            _progress.recorded_fields(step.step_number),
            _progress.missing_fields(step),
        )


def recorded_step_values() -> dict[int, dict[str, str]]:
    """所有步骤的已记录值（{step_number: {field_name: value}}），用于序列化到 store。"""
    with _lock:
        return _progress.all_values()


def step_progress_view(state) -> dict:
    """当前步骤的进度事实：状态 + 已记录字段 + 还缺的必测字段。

    供大模型在用户说"完成了"时核对真相用——模型只读事实，不自己猜。
    """
    step = state.current_step()
    if step is None:
        return {"status": "waiting_user", "recorded": [], "missing": []}
    with _lock:
        return {
            "status": _progress.status_for(step),
            "recorded": _progress.recorded_fields(step.step_number),
            "missing": _progress.missing_fields(step),
        }


def complete_step(step_number: int, manual: bool) -> dict:
    """完成当前步。

    - manual=True：用户手动确认（点"完成本步"按钮）→ 直接打勾并落盘，
      视为人类责任确认，不要求补齐口述数据；
    - manual=False：严格校验（必测字段记齐且无偏差才通过，否则拒绝）。
    两种路径都只能完成"当前步"，且状态变更都发生在后端状态机。
    """
    with _lock:
        state = session()
        if not state.selection.has_protocol:
            raise ValueError("尚未选择实验方案")
        if state.step_number != step_number:
            raise ValueError(f"只能完成当前步（第 {state.step_number} 步）")
        if manual:
            _progress.confirm(step_number)
            save_step_confirmation(step_number)
            return step_progress_view(state)
        progress = step_progress_view(state)
        if progress["status"] == "error":
            raise ValueError("本步存在偏差，需要先处理")
        if progress["status"] != "completed":
            raise ValueError("本步还没记齐，还缺：" + "、".join(progress["missing"]))
        return progress


def move(action: str, step_number: int | None = None) -> ProtocolSessionState:
    global _session
    with _lock:
        state = session()
        if action == "next":
            _session = state.next()
        elif action == "prev":
            _session = state.prev()
        elif action == "jump":
            _session = state.jump_to(int(step_number))
        else:
            raise ValueError("不支持的步骤操作：" + str(action))
        _persist_snapshot()
        return _session


def safety_for(step) -> list:
    """返回本步骤涉及试剂的安全信息；只突出高危项，避免警告过载。"""
    if step is None:
        return []
    store = hazmat()
    found = store.find_in_text(step.instruction, *step.terms)
    result = []
    for reagent in found:
        result.append({
            "name": reagent.name_zh,
            "cas": reagent.cas,
            "critical": reagent.is_critical,
            "codes": list(reagent.critical_codes),
            "statements": [s.text for s in reagent.critical_statements()],
            "source_url": reagent.source_url,
        })
    return result


def step_view(state: ProtocolSessionState) -> dict:
    """把会话状态转成前端可直接渲染的结构。"""
    step = state.current_step()
    protocol = state.selection.protocol
    if step is None or protocol is None:
        return {
            "mode": "free",
            "protocol": None,
            "step": None,
            "safety": [],
            "safety_note": hazmat().authority_note,
        }
    recorded, _missing = _step_recorded_missing(step)
    # 产品要求：全局没有任何“必测字段”。界面只展示用户已说的内容，
    # 不再显示“还缺什么/现场必测什么”，也不要因为缺字段把步骤卡标成等待。
    return {
        "mode": "protocol",
        "protocol": {
            "id": protocol.protocol_id,
            "title": protocol.title,
            "source": protocol.source,
            "version": protocol.version,
            "total_steps": len(protocol.steps),
        },
        "step": {
            "number": step.step_number,
            "title": step.title,
            "instruction": step.instruction,
            "protocol_values": dict(step.protocol_values),
            "value_aliases": {
                name: list(values) for name, values in step.value_aliases.items()
            },
            "must_record": [],
            "hazard_note": step.hazard_note,
            "terms": list(step.terms),
            "status": step_status(step),
            "card_type": "confirm",
            "recorded": recorded,
            "missing": [],
            "substeps": [
                {"order": x.order, "text": x.text, "note": x.note}
                for x in step.substeps
            ],
        },
        "safety": safety_for(step),
        "safety_note": hazmat().authority_note,
    }


def evaluate(entities_dict: dict) -> dict:
    """按当前步骤做确定性判断：缺什么、有没有偏差。"""
    return evaluate_for_state(session(), entities_dict)


def evaluate_for_state(state: ProtocolSessionState, entities_dict: dict) -> dict:
    """按调用方捕获的同一方案状态快照评价，避免步骤在处理中漂移。"""
    known = {f: entities_dict.get(f) for f in ExperimentEntities.__dataclass_fields__}
    entities = ExperimentEntities(**known)
    result = evaluate_segment(state, entities)
    return {
        "missing_fields": list(result.missing_fields),
        "follow_up_question": result.follow_up_question,
        "follow_up_required": result.follow_up_required,
        "deviations": [
            {
                "field": d.field_name,
                "protocol_value": d.protocol_value,
                "actual_value": d.actual_value,
            }
            for d in result.deviations
        ],
        "sourced_values": {
            name: {"value": v.value, "source": v.source.value}
            for name, v in result.sourced_values.items()
        },
    }


def project_record_evaluation(record: dict) -> dict:
    """Re-evaluate ledger display with the exact current protocol id/version/step."""

    step_snapshot = record.get("step") or {}
    protocol_snapshot = step_snapshot.get("protocol") or {}
    recorded_step = step_snapshot.get("step") or {}
    protocol_id = protocol_snapshot.get("id")
    protocol_version = protocol_snapshot.get("version")
    step_number = recorded_step.get("number")
    if not protocol_id or not protocol_version or not step_number:
        return record
    protocol = protocols().get(str(protocol_id))
    if protocol is None or protocol.version != str(protocol_version):
        return record
    step_index = int(step_number) - 1
    if step_index < 0 or step_index >= len(protocol.steps):
        return record
    entities_dict = record.get("entities") or {}
    known = {
        name: entities_dict.get(name)
        for name in ExperimentEntities.__dataclass_fields__
    }
    deviations = detect_protocol_deviations(
        protocol.steps[step_index], ExperimentEntities(**known)
    )
    projected = dict(record)
    stored_evaluation = dict(record.get("evaluation") or {})
    evaluation = dict(stored_evaluation)
    evaluation["stored_deviations"] = stored_evaluation.get("deviations") or []
    evaluation["deviations"] = [{
        "field": item.field_name,
        "protocol_value": item.protocol_value,
        "actual_value": item.actual_value,
    } for item in deviations]
    evaluation["deviation_rule_version"] = 2
    projected["evaluation"] = evaluation
    return projected

def all_steps_view(state) -> dict:
    """当前方案的全部步骤概要，供状态机卡片栏渲染。"""
    view = step_view(state)
    protocol = state.selection.protocol
    if protocol is None:
        view["all_steps"] = []
        view["all_completed"] = False
        return view
    view["all_steps"] = [
        {
            "number": s.step_number,
            "title": s.title,
            "instruction": s.instruction,
            "protocol_values": dict(s.protocol_values),
            "must_record": [],
            "has_hazard": bool(s.hazard_note) or bool(safety_for(s)),
            "substep_count": len(s.substeps),
            "status": step_status(s),
            "card_type": "confirm",
            "recorded": _step_recorded_missing(s)[0],
            "missing": [],
        }
        for s in protocol.steps
    ]
    # "全部完成"由后端判定（前端只渲染）：所有步骤均为 completed。
    view["all_completed"] = bool(view["all_steps"]) and all(
        s["status"] == "completed" for s in view["all_steps"]
    )
    return view

def entity_field_names() -> list:
    """实体字段白名单，供编辑界面做下拉选择。"""
    from dataclasses import fields as dc_fields
    return [f.name for f in dc_fields(ExperimentEntities)]


def _bump_version(version: str) -> str:
    try:
        major, minor = str(version).split(".")
        return f"{major}.{int(minor) + 1}"
    except Exception:
        return str(version) + ".1"


_USER_PROTOCOL_SOURCE_MARKERS = (
    "AI生成草稿",
    "AI生成",
    "OCR识别草稿",
    "论文上传",
    "用户上传",
    "用户创建",
    "用户自制",
    "本地创建",
    "自定义",
)


def is_deletable_protocol_source(source: str | None) -> bool:
    """是否属于用户自己创建/上传、可以整份删除的方案。"""
    if not source:
        return False
    return any(marker in str(source) for marker in _USER_PROTOCOL_SOURCE_MARKERS)


def _unique_protocol_title(title: str, raw_library: dict) -> str:
    """同名方案自动加（1）/（2）…，避免多份同名方案在列表里无法区分。"""
    titles = {
        item.get("title", "")
        for item in raw_library.get("protocols", [])
    }
    if title not in titles:
        return title
    index = 1
    while f"{title}（{index}）" in titles:
        index += 1
    return f"{title}（{index}）"


def protocol_detail(protocol_id: str) -> dict:
    """一份方案的完整详情：步骤、准备材料、危险提示。"""

    protocol = protocols().get_by_id(protocol_id)
    if protocol is None:
        raise ValueError(f"找不到方案 {protocol_id}")
    return {
        "protocol": {
            "id": protocol.protocol_id,
            "title": protocol.title,
            "source": protocol.source,
            "version": protocol.version,
            "total_steps": len(protocol.steps),
            "deletable": is_deletable_protocol_source(protocol.source),
        },
        "steps": [
            {
                "number": s.step_number,
                "title": s.title,
                "instruction": s.instruction,
                "protocol_values": dict(s.protocol_values),
                "must_record": list(s.must_record),
                "terms": list(s.terms),
                "hazard_note": s.hazard_note,
                "field_prompts": dict(s.field_prompts),
                "substeps": [
                    {"order": x.order, "text": x.text, "note": x.note}
                    for x in s.substeps
                ],
                "safety": safety_for(s),
            }
            for s in protocol.steps
        ],
        "prep_requirements": protocol_prep_requirements(protocol_id)["items"],
    }


def add_protocol(raw_protocol: dict) -> dict:
    """把一份新的实验方案写入方案库；先严格校验，再整份重写。"""
    import json

    from src.storage.protocol_store import ProtocolStore, ProtocolStoreError

    raw_library = json.loads(PROTOCOL_FILE.read_text(encoding="utf-8"))
    raw_protocol = dict(raw_protocol)
    raw_protocol["title"] = _unique_protocol_title(
        raw_protocol.get("title", ""), raw_library
    )
    existing_ids = {item.get("protocol_id") for item in raw_library.get("protocols", [])}
    new_id = raw_protocol.get("protocol_id", "")
    if not new_id or new_id in existing_ids:
        raise ValueError("protocol_id 为空或已存在：" + str(new_id))

    # 用契约解析器先验证这份草稿；不通过绝不写入。
    try:
        ProtocolStore._parse_protocol(raw_protocol, index=len(raw_library["protocols"]) + 1)
    except ProtocolStoreError as error:
        raise ValueError(f"方案草稿不符合契约：{error}") from error

    raw_library["protocols"].append(raw_protocol)
    PROTOCOL_FILE.write_text(
        json.dumps(raw_library, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    global _protocol_store, _session
    with _lock:
        _protocol_store = None
        if _session is not None and _session.selection.protocol is None:
            pass

    _sync_prep_requirements_for_protocol(raw_protocol)
    return raw_protocol


def upsert_protocol(raw_protocol: dict) -> dict:
    """社区导入用：protocol_id 已存在则整份覆盖，不存在则新增。"""
    import json

    from src.storage.protocol_store import ProtocolStore, ProtocolStoreError

    protocol_id = raw_protocol.get("protocol_id", "")
    if not protocol_id:
        raise ValueError("protocol_id 不能为空")

    raw_protocol = dict(raw_protocol)
    raw_library = json.loads(PROTOCOL_FILE.read_text(encoding="utf-8"))
    try:
        ProtocolStore._parse_protocol(
            raw_protocol, index=len(raw_library["protocols"]) + 1
        )
    except ProtocolStoreError as error:
        raise ValueError(f"方案草稿不符合契约：{error}") from error

    replaced = False
    for index, item in enumerate(raw_library.get("protocols", [])):
        if item.get("protocol_id") == protocol_id:
            raw_library["protocols"][index] = raw_protocol
            replaced = True
            break
    if not replaced:
        raw_protocol["title"] = _unique_protocol_title(
            raw_protocol.get("title", ""), raw_library
        )
        raw_library["protocols"].append(raw_protocol)

    PROTOCOL_FILE.write_text(
        json.dumps(raw_library, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    global _protocol_store, _session
    with _lock:
        _protocol_store = None
        if _session is not None and _session.selection.protocol is not None:
            if _session.selection.protocol.protocol_id == protocol_id:
                current = _session.step_number
                _session = ProtocolSessionState.start(
                    select_protocol(protocols(), protocol_id)
                )
                _progress.reset()
                clear_progress_rows()
                if current:
                    _session = _session.jump_to(current)

    _sync_prep_requirements_for_protocol(raw_protocol)
    return raw_protocol



def update_step(payload: dict) -> dict:
    """编辑一个大步骤并写回方案库。

    先在内存里构造新的 ProtocolStep，让契约校验拦下非法输入；
    通过后才整份重写 JSON，避免写出半成品文件。
    """
    import json
    from src.core.protocol import ProtocolStep, ProtocolSubStep

    protocol_id = payload["protocol_id"]
    step_number = int(payload["step_number"])

    raw = json.loads(PROTOCOL_FILE.read_text(encoding="utf-8"))
    target_protocol = None
    target_step = None
    for item in raw["protocols"]:
        if item["protocol_id"] == protocol_id:
            target_protocol = item
            for step in item["steps"]:
                if step["step_number"] == step_number:
                    target_step = step
            break
    if target_protocol is None or target_step is None:
        raise ValueError(f"找不到方案 {protocol_id} 的第 {step_number} 步")

    updated = dict(target_step)
    for key in ("title", "instruction", "hazard_note"):
        if payload.get(key) is not None:
            updated[key] = payload[key]
    if payload.get("protocol_values") is not None:
        updated["protocol_values"] = payload["protocol_values"]
    if payload.get("must_record") is not None:
        updated["must_record"] = list(payload["must_record"])
    if payload.get("field_prompts") is not None:
        updated["field_prompts"] = payload["field_prompts"]
    if payload.get("value_aliases") is not None:
        updated["value_aliases"] = payload["value_aliases"]
    if payload.get("substeps") is not None:
        updated["substeps"] = [
            {"order": i, "text": x.get("text", ""), "note": x.get("note") or None}
            for i, x in enumerate(payload["substeps"], start=1)
            if str(x.get("text", "")).strip()
        ]

    # 先让契约校验；不通过直接抛，不落盘
    ProtocolStep(
        step_number=updated["step_number"],
        title=updated["title"],
        instruction=updated["instruction"],
        protocol_values=updated.get("protocol_values") or {},
        must_record=tuple(updated.get("must_record") or ()),
        terms=tuple(updated.get("terms") or ()),
        hazard_note=updated.get("hazard_note") or None,
        field_prompts=updated.get("field_prompts") or {},
        value_aliases={
            key: tuple(values)
            for key, values in (updated.get("value_aliases") or {}).items()
        },
        substeps=tuple(
            ProtocolSubStep(order=x["order"], text=x["text"], note=x.get("note"))
            for x in (updated.get("substeps") or [])
        ),
    )

    for index, step in enumerate(target_protocol["steps"]):
        if step["step_number"] == step_number:
            target_protocol["steps"][index] = updated
            break
    target_protocol["version"] = _bump_version(target_protocol.get("version", "1.0"))
    PROTOCOL_FILE.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    global _protocol_store, _session
    with _lock:
        _protocol_store = None       # 下次访问重新加载
        if _session is not None and _session.selection.protocol is not None:
            if _session.selection.protocol.protocol_id == protocol_id:
                current = _session.step_number
                _session = ProtocolSessionState.start(
                    select_protocol(protocols(), protocol_id)
                )
                _progress.reset()     # 方案步骤被编辑，进度按新方案重新计
                clear_progress_rows() # 落盘进度同步清零
                if current:
                    _session = _session.jump_to(current)
    return step_view(session())


def reagent_prep_view(prep: ReagentPrep) -> dict:
    """把一条试剂配置方案转成前端可渲染结构，并附带危险提示。"""

    from tools.reagent_catalog import find_reagent

    store = hazmat()
    safety = []
    for name in prep.hazard_reagents:
        found = store.find(name)
        if found is not None:
            safety.append({
                "name": found.name_zh,
                "cas": found.cas,
                "critical": found.is_critical,
                "codes": list(found.critical_codes),
                "statements": [s.text for s in found.critical_statements()],
                "source_url": found.source_url,
            })
            continue
        cat = find_reagent(name)
        if cat is not None:
            state = "液体" if cat.get("state") == "liquid" else ("固体" if cat.get("state") == "solid" else "未知")
            extra = f"通用试剂目录：{state}"
            if cat.get("density"):
                extra += f"，密度约 {cat['density']} g/mL"
            if cat.get("acidic"):
                extra += "，酸性试剂，配液后需注意调pH"
            safety.append({
                "name": cat.get("name_zh") or name,
                "cas": cat.get("cas"),
                "critical": False,
                "codes": [],
                "statements": [extra],
                "source_url": None,
            })
    return {
        "reagent_prep_id": prep.reagent_prep_id,
        "name_zh": prep.name_zh,
        "purpose": prep.purpose,
        "target_concentration": prep.target_concentration,
        "target_volume": prep.target_volume,
        "solvent": prep.solvent,
        "steps": list(prep.steps),
        "storage_condition": prep.storage_condition,
        "expiry": prep.expiry,
        "hazard_reagents": list(prep.hazard_reagents),
        "source": prep.source,
        "source_url": prep.source_url,
        "review_status": prep.review_status,
        "safety": safety,
        "safety_note": hazmat().authority_note,
    }


def add_reagent_prep(raw_prep: dict) -> dict:
    """校验并新增一条试剂配置；不通过绝不落盘。新增时自动识别步骤里的试剂名称。"""

    raw_prep["hazard_reagents"] = _auto_hazard_reagents(raw_prep)
    prep = ReagentPrep.from_dict(raw_prep)
    store = reagent_preps()
    store.add(prep)
    return reagent_prep_view(prep)


def _detect_reagent_names(texts: list[str]) -> list[str]:
    """从文本中识别试剂名称（试剂目录 + 危化品库），避免短名误命中。"""
    from tools.reagent_catalog import load_catalog

    blob = " ".join(texts)
    catalog_map = {}
    for item in load_catalog().values():
        catalog_map.setdefault(item.get("name_zh") or item.get("name_en"), item)
    # 试剂目录别名优先（最长名优先）
    names = []
    for alias, item in load_catalog().items():
        name = item.get("name_zh") or item.get("name_en")
        if name and alias and alias in blob:
            names.append(name)
    names = sorted(set(names), key=lambda x: -len(x))
    # 危化品库文本匹配
    store = hazmat()
    hazmat_found = list(store.find_in_text(*texts))
    for r in hazmat_found:
        if not any(r.name_zh in existing for existing in names):
            names.append(r.name_zh)
    # 去重并保持顺序
    seen = set()
    result = []
    for name in names:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _auto_hazard_reagents(raw_prep: dict) -> list[str]:
    """从步骤文本中自动识别危险试剂名称，用于保存后安全提示。"""
    texts = []
    for value in [raw_prep.get("name_zh"), raw_prep.get("purpose")]:
        if isinstance(value, str) and value:
            texts.append(value)
    steps = raw_prep.get("steps")
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, str) and step:
                texts.append(step)
    return _detect_reagent_names(texts)


def update_reagent_prep(reagent_prep_id: str, raw_prep: dict) -> dict:
    """校验并更新一条试剂配置；不通过绝不落盘。更新时自动识别步骤里的试剂名称。"""
    existing = reagent_preps().get_by_id(reagent_prep_id)
    if existing is not None:
        for field in ("source", "source_url", "review_status"):
            raw_prep.setdefault(field, getattr(existing, field))
    raw_prep["hazard_reagents"] = _auto_hazard_reagents(raw_prep)
    prep = reagent_preps().update(reagent_prep_id, raw_prep)
    return reagent_prep_view(prep)


def delete_reagent_prep(reagent_prep_id: str) -> dict:
    """删除一条试剂配置。"""
    ok = reagent_preps().delete(reagent_prep_id)
    if not ok:
        raise ValueError(f"找不到试剂配置：{reagent_prep_id}")
    return {"ok": True, "reagent_prep_id": reagent_prep_id}


def add_reagent_preps(raw_preps: list) -> dict:
    """批量校验并新增；全部通过才写库。"""

    preps = [ReagentPrep.from_dict(item) for item in raw_preps]
    store = reagent_preps()
    store.add_many(preps)
    return {
        "added": len(preps),
        "ids": [p.reagent_prep_id for p in preps],
    }


def analyze_reagents(texts: list) -> dict:
    """识别文字中出现的危化品与试剂配置库条目。

    试剂名采用最长名优先，避免“硫酸铜”命中后“五水硫酸铜”重复。
    """

    store = hazmat()
    found = store.find_in_text(*texts)
    prep_store = reagent_preps()
    preps = [
        prep
        for prep in prep_store.list_all()
        if any(prep.name_zh in text for text in texts if isinstance(text, str))
    ]
    return {
        "hazmat": [
            {
                "name": r.name_zh,
                "cas": r.cas,
                "critical": r.is_critical,
                "codes": list(r.critical_codes),
                "statements": [s.text for s in r.critical_statements()],
            }
            for r in found
        ],
        "reagent_preps": [
            {
                "reagent_prep_id": p.reagent_prep_id,
                "name_zh": p.name_zh,
                "purpose": p.purpose,
            }
            for p in preps
        ],
    }


def protocol_prep_requirements(protocol_id: str | None) -> dict:
    """读取方案需要的试剂配置列表；找不到方案返回空。"""

    if protocol_id is None:
        return {"protocol_id": None, "items": []}
    raw = json.loads(PREP_REQUIREMENTS_FILE.read_text(encoding="utf-8"))
    ids = raw.get("requirements", {}).get(protocol_id, [])
    store = reagent_preps()
    items = []
    for prep_id in ids:
        prep = store.get_by_id(prep_id)
        if prep is not None:
            items.append(reagent_prep_view(prep))
    return {"protocol_id": protocol_id, "items": items}


def _protocol_texts(raw_protocol: dict) -> list:
    """提取一份方案中可用于试剂识别的文本。"""

    texts = [raw_protocol.get("title", "")]
    for step in raw_protocol.get("steps", []):
        texts.append(step.get("instruction", ""))
        texts.append(step.get("title", ""))
        texts.extend(step.get("terms", []) or [])
    return [str(t) for t in texts if str(t).strip()]


def _sync_prep_requirements_for_protocol(raw_protocol: dict) -> None:
    """把方案中命中的试剂配置自动写入 prep_requirements 映射。"""

    protocol_id = raw_protocol.get("protocol_id", "")
    if not protocol_id:
        return
    texts = _protocol_texts(raw_protocol)
    analysis = analyze_reagents(texts)
    prep_ids = [item["reagent_prep_id"] for item in analysis["reagent_preps"]]

    raw = json.loads(PREP_REQUIREMENTS_FILE.read_text(encoding="utf-8"))
    requirements = raw.setdefault("requirements", {})
    requirements[protocol_id] = prep_ids
    PREP_REQUIREMENTS_FILE.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def add_protocol_step(payload: dict) -> dict:
    """在方案中追加/插入一个大步骤，严格校验后落盘。"""

    from src.core.protocol import ProtocolStep, ProtocolSubStep

    protocol_id = payload["protocol_id"]
    after = payload.get("after_step_number")
    raw = json.loads(PROTOCOL_FILE.read_text(encoding="utf-8"))
    target_protocol = None
    for item in raw["protocols"]:
        if item["protocol_id"] == protocol_id:
            target_protocol = item
            break
    if target_protocol is None:
        raise ValueError(f"找不到方案 {protocol_id}")

    step_data = {
        "step_number": 0,
        "title": payload.get("title", ""),
        "instruction": payload.get("instruction", ""),
        "protocol_values": payload.get("protocol_values") or {},
        "must_record": list(payload.get("must_record") or ()),
        "terms": list(payload.get("terms") or ()),
        "hazard_note": payload.get("hazard_note") or None,
        "field_prompts": payload.get("field_prompts") or {},
        "substeps": [
            {"order": i, "text": x.get("text", ""), "note": x.get("note") or None}
            for i, x in enumerate(payload.get("substeps") or [], start=1)
            if str(x.get("text", "")).strip()
        ],
    }

    ProtocolStep(
        step_number=1,
        title=step_data["title"],
        instruction=step_data["instruction"],
        protocol_values=step_data["protocol_values"],
        must_record=tuple(step_data["must_record"]),
        terms=tuple(step_data["terms"]),
        hazard_note=step_data["hazard_note"],
        field_prompts=step_data["field_prompts"],
        substeps=tuple(
            ProtocolSubStep(order=x["order"], text=x["text"], note=x.get("note"))
            for x in step_data["substeps"]
        ),
    )

    steps = target_protocol["steps"]
    if after is None:
        insert_at = len(steps)
    else:
        after = int(after)
        insert_at = after
        if insert_at < 0 or insert_at > len(steps):
            raise ValueError("after_step_number 超出范围。")
    steps.insert(insert_at, step_data)
    for index, step in enumerate(steps, start=1):
        step["step_number"] = index
    target_protocol["version"] = _bump_version(target_protocol.get("version", "1.0"))
    PROTOCOL_FILE.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    global _protocol_store, _session
    with _lock:
        _protocol_store = None
        if _session is not None and _session.selection.protocol is not None:
            if _session.selection.protocol.protocol_id == protocol_id:
                current = _session.step_number
                _session = ProtocolSessionState.start(
                    select_protocol(protocols(), protocol_id)
                )
                if current:
                    _session = _session.jump_to(current)
    return step_view(session())


def update_protocol_from_draft(raw_protocol: dict) -> dict:
    """用 AI 修订后的完整方案替换同 ID 的现有方案，自动升版本。"""

    from src.storage.protocol_store import ProtocolStore, ProtocolStoreError

    protocol_id = raw_protocol.get("protocol_id", "")
    # 先校验，不通过绝不落盘
    try:
        ProtocolStore._parse_protocol(raw_protocol, index=1)
    except ProtocolStoreError as error:
        raise ValueError(f"修订后的方案不符合契约：{error}")

    raw = json.loads(PROTOCOL_FILE.read_text(encoding="utf-8"))
    target = None
    for item in raw["protocols"]:
        if item["protocol_id"] == protocol_id:
            target = item
            break
    if target is None:
        raise ValueError(f"找不到方案 {protocol_id}")
    raw_protocol["version"] = _bump_version(raw_protocol.get("version", "1.0"))
    for index, item in enumerate(raw["protocols"]):
        if item["protocol_id"] == protocol_id:
            raw["protocols"][index] = raw_protocol
            break
    PROTOCOL_FILE.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    global _protocol_store, _session
    with _lock:
        _protocol_store = None
        if _session is not None and _session.selection.protocol is not None:
            if _session.selection.protocol.protocol_id == protocol_id:
                current = _session.step_number
                _session = ProtocolSessionState.start(
                    select_protocol(protocols(), protocol_id)
                )
                if current:
                    _session = _session.jump_to(current)
    _sync_prep_requirements_for_protocol(raw_protocol)
    return protocol_detail(protocol_id)


def delete_protocol_step(protocol_id: str, step_number: int) -> dict:
    """删除方案中的一个大步骤并重新编号，严格校验后落盘。"""

    raw = json.loads(PROTOCOL_FILE.read_text(encoding="utf-8"))
    target_protocol = None
    for item in raw["protocols"]:
        if item["protocol_id"] == protocol_id:
            target_protocol = item
            break
    if target_protocol is None:
        raise ValueError(f"找不到方案 {protocol_id}")
    if len(target_protocol["steps"]) <= 1:
        raise ValueError("方案至少保留一个步骤。")
    step_number = int(step_number)
    if step_number < 1 or step_number > len(target_protocol["steps"]):
        raise ValueError("步骤号超出范围。")
    del target_protocol["steps"][step_number - 1]
    for index, step in enumerate(target_protocol["steps"], start=1):
        step["step_number"] = index
    target_protocol["version"] = _bump_version(target_protocol.get("version", "1.0"))
    PROTOCOL_FILE.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    global _protocol_store, _session
    with _lock:
        _protocol_store = None
        if _session is not None and _session.selection.protocol is not None:
            if _session.selection.protocol.protocol_id == protocol_id:
                current = _session.step_number
                _session = ProtocolSessionState.start(
                    select_protocol(protocols(), protocol_id)
                )
                if current:
                    _session = _session.jump_to(current)
    return step_view(session())


def delete_protocol(protocol_id: str) -> dict:
    """删除用户自己创建/上传的整份方案；内置/社区方案不允许删除。"""
    import json

    raw = json.loads(PROTOCOL_FILE.read_text(encoding="utf-8"))
    target_index = None
    target = None
    for index, item in enumerate(raw.get("protocols", [])):
        if item.get("protocol_id") == protocol_id:
            target_index = index
            target = item
            break
    if target_index is None:
        raise ValueError("找不到方案：" + protocol_id)
    source = target.get("source", "")
    if not is_deletable_protocol_source(source):
        raise ValueError("该来源的方案不能删除，仅可删除用户自己创建或上传的方案。")

    del raw["protocols"][target_index]
    PROTOCOL_FILE.write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    global _protocol_store, _session
    with _lock:
        _protocol_store = None
        if _session is not None and _session.selection.has_protocol:
            if _session.selection.protocol.protocol_id == protocol_id:
                _session = ProtocolSessionState.start(select_protocol(protocols(), None))
                _progress.reset()
                clear_progress_rows()
                _persist_snapshot()
    return {"ok": True, "deleted": protocol_id}
