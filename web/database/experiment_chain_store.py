# -*- coding: utf-8 -*-
"""实验产物链：记录每个实验产出了什么、消耗了什么，建立实验间的材料流转关系。

核心模型：
- experiment_products：一次实验（session）产出的样品/试剂/培养物等，
  可选地自动入库为 storage_item（带 source_experiment_id 溯源）。
- experiment_consumes：一次实验消耗的储存物品，标记从库存扣除。

这样实验之间就能建立接续链：
  实验A产出「感受态细胞」→ 入库 → 几天后实验B从这里取用 → 产出「转化子」→ 入库 → …
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from database.db import get_connection, initialize_database

# ── 建表 ──

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS experiment_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL DEFAULT '',
    experiment_id INTEGER DEFAULT NULL,
    product_name TEXT NOT NULL,
    product_type TEXT NOT NULL DEFAULT 'sample',
    quantity TEXT DEFAULT '',
    unit TEXT DEFAULT '',
    storage_item_id INTEGER DEFAULT NULL,
    notes TEXT DEFAULT '',
    produced_at TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS experiment_consumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL DEFAULT '',
    experiment_id INTEGER DEFAULT NULL,
    storage_item_id INTEGER NOT NULL,
    quantity_used TEXT DEFAULT '',
    consumed_at TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_products_session ON experiment_products(session_id);
CREATE INDEX IF NOT EXISTS idx_products_exp ON experiment_products(experiment_id);
CREATE INDEX IF NOT EXISTS idx_consumes_session ON experiment_consumes(session_id);
CREATE INDEX IF NOT EXISTS idx_consumes_item ON experiment_consumes(storage_item_id);
"""


def _ensure_tables(conn: sqlite3.Connection):
    conn.executescript(_SCHEMA_SQL)


def ensure_tables():
    initialize_database()
    with get_connection() as conn:
        _ensure_tables(conn)


# ── 产物 ──


def add_product(
    session_id: str = "",
    experiment_id: int | None = None,
    product_name: str = "",
    product_type: str = "sample",
    quantity: str = "",
    unit: str = "",
    storage_item_id: int | None = None,
    notes: str = "",
    produced_at: str = "",
) -> dict:
    """记录一个实验产物。"""
    ensure_tables()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not produced_at:
        produced_at = now
    with get_connection() as conn:
        _ensure_tables(conn)
        cursor = conn.execute(
            """INSERT INTO experiment_products
            (session_id, experiment_id, product_name, product_type, quantity, unit,
             storage_item_id, notes, produced_at, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                session_id, experiment_id, product_name, product_type, quantity, unit,
                storage_item_id, notes, produced_at, now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM experiment_products WHERE id=?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


def list_products(session_id: str = "", experiment_id: int | None = None) -> list[dict]:
    """列出某个实验 session 或 experiment 的所有产物。"""
    ensure_tables()
    where = []
    params: list = []
    if session_id:
        where.append("session_id=?")
        params.append(session_id)
    if experiment_id is not None:
        where.append("experiment_id=?")
        params.append(experiment_id)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    with get_connection() as conn:
        _ensure_tables(conn)
        rows = conn.execute(
            f"SELECT * FROM experiment_products {where_sql} ORDER BY id", params
        ).fetchall()
    result = [dict(r) for r in rows]
    # 尝试关联 storage_item 名称
    for item in result:
        if item.get("storage_item_id"):
            with get_connection() as conn:
                sr = conn.execute(
                    "SELECT name, status, location_id FROM storage_items WHERE id=?",
                    (item["storage_item_id"],),
                ).fetchone()
            if sr:
                item["storage_name"] = sr["name"]
                item["storage_status"] = sr["status"]
    return result


def remove_product(product_id: int) -> bool:
    """删除产物记录（不删除关联的 storage_item）。"""
    ensure_tables()
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM experiment_products WHERE id=?", (product_id,))
    return bool(cursor.rowcount)


def update_product_storage_link(product_id: int, storage_item_id: int):
    """把产物关联到新建的 storage_item。"""
    ensure_tables()
    with get_connection() as conn:
        conn.execute(
            "UPDATE experiment_products SET storage_item_id=? WHERE id=?",
            (storage_item_id, product_id),
        )


# ── 消耗 ──


def add_consume(
    session_id: str = "",
    experiment_id: int | None = None,
    storage_item_id: int = 0,
    quantity_used: str = "",
    consumed_at: str = "",
) -> dict:
    """记录一次实验消耗了某个库存物品。"""
    ensure_tables()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not consumed_at:
        consumed_at = now
    with get_connection() as conn:
        _ensure_tables(conn)
        cursor = conn.execute(
            """INSERT INTO experiment_consumes
            (session_id, experiment_id, storage_item_id, quantity_used, consumed_at, created_at)
            VALUES (?,?,?,?,?,?)""",
            (session_id, experiment_id, storage_item_id, quantity_used, consumed_at, now),
        )
        row = conn.execute(
            "SELECT * FROM experiment_consumes WHERE id=?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


def list_consumes(session_id: str = "", experiment_id: int | None = None) -> list[dict]:
    """列出某实验消耗的库存物品。"""
    ensure_tables()
    where = []
    params: list = []
    if session_id:
        where.append("c.session_id=?")
        params.append(session_id)
    if experiment_id is not None:
        where.append("c.experiment_id=?")
        params.append(experiment_id)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    with get_connection() as conn:
        _ensure_tables(conn)
        rows = conn.execute(
            f"""SELECT c.*, s.name AS storage_name, s.unit AS storage_unit,
                       s.status AS storage_status
                FROM experiment_consumes c
                LEFT JOIN storage_items s ON s.id=c.storage_item_id
                {where_sql} ORDER BY c.id""",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


# ── 实验链：完整溯源 ──


def session_chain(session_id: str) -> dict:
    """返回一个 session 的完整产物/消耗信息。"""
    return {
        "session_id": session_id,
        "products": list_products(session_id=session_id),
        "consumes": list_consumes(session_id=session_id),
    }


def storage_provenance(storage_item_id: int) -> dict | None:
    """溯源：一个储存物来自哪个实验 session。"""
    ensure_tables()
    with get_connection() as conn:
        _ensure_tables(conn)
        # 直接通过 storage_items.source_experiment_id 查
        row = conn.execute(
            "SELECT source_experiment_id FROM storage_items WHERE id=?",
            (storage_item_id,),
        ).fetchone()
        if not row:
            return None
        session_id = row["source_experiment_id"] or ""
        result = {"storage_item_id": storage_item_id}
        if session_id:
            result["source_session_id"] = session_id
            # 尝试从 experiment_products 查补充信息
            prow = conn.execute(
                """SELECT * FROM experiment_products
                   WHERE storage_item_id=? ORDER BY id DESC LIMIT 1""",
                (storage_item_id,),
            ).fetchone()
            if prow:
                result["product_name"] = prow["product_name"]
                result["product_type"] = prow["product_type"]
                result["produced_at"] = prow["produced_at"]
                result["notes"] = prow["notes"]
        return result
