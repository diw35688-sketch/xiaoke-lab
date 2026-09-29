# -*- coding: utf-8 -*-
from __future__ import annotations

"""知识库检索（由 lab_tools.py 拆分生成）。"""

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

# ---------------- 知识库检索（引物表等共享表格） ----------------

@tool(
    "search_knowledge_base",
    "搜索实验室知识库（已上传的共享表格，如引物表、抗体表、细胞系表等）。"
    "用户问'XX的引物是什么''查一下知识库''我们有没有XX的记录'时调用。"
    "传入搜索关键词即可跨所有表格全文检索。",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词，如基因名、引物名、抗体名等"},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    kind="read", title="搜索知识库：{query}", experiment_command=True,
    present=lambda a, r: (
        [f"找到 {r['count']} 条匹配记录"]
        + [
            f"「{item['table_name']}」" + "："
            + "、".join(f"{k}={v}" for k, v in list(item['data'].items())[:4])
            for item in r["results"][:5]
        ]
        if r.get("count")
        else [f"知识库中没有匹配「{a['query']}」的记录"]
    ),
)
def _search_knowledge_base(query):
    from database.db import get_connection

    raw = str(query or "").strip()
    if not raw:
        return {"count": 0, "results": [], "query": query}

    import re as _re
    keywords = [w for w in _re.split(r'[\s,，;；、]+', raw) if w]
    if not keywords:
        keywords = [raw]

    with get_connection() as conn:
        tables_map = {t["id"]: dict(t) for t in conn.execute("SELECT * FROM kb_tables").fetchall()}
        results = []
        seen = set()
        for t_id, t in tables_map.items():
            row_data = conn.execute(
                "SELECT data_json FROM kb_rows WHERE table_id=? ORDER BY row_index LIMIT 5000",
                (t_id,),
            ).fetchall()
            for rd in row_data:
                blob = rd["data_json"]
                if not all(kw.lower() in blob.lower() for kw in keywords):
                    continue
                data = json.loads(blob)
                key = t_id + blob
                if key in seen:
                    continue
                seen.add(key)
                results.append({
                    "table_id": t_id,
                    "table_name": t.get("name", ""),
                    "columns": json.loads(t.get("columns_json") or "[]"),
                    "data": data,
                })
                if len(results) >= 20:
                    break
            if len(results) >= 20:
                break

    return {"query": query, "count": len(results), "results": results}

