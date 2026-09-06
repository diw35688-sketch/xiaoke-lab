# -*- coding: utf-8 -*-
"""知识库：实验室共享表格上传 + FTS5 全文检索。

典型场景：实验室共享一张引物 Excel 表，几百到几千条，
用户忘了就去查"这个基因的某个功能用哪对引物"。

数据结构：
  - kb_tables：上传的表格元信息（名称、描述、列名、行数）
  - kb_rows：表格内的每一行（JSON 存列→值映射）
  - kb_rows_fts：FTS5 全文索引（跨所有列做关键词搜索）
"""
import json
import sys
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from database.db import get_connection

router = APIRouter(prefix="/kb", tags=["知识库"])

if getattr(sys, "frozen", False):
    BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)) / "web"
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
KB_UPLOAD_DIR = BASE_DIR.parent / "uploads" / "kb"
KB_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _ensure_tables():
    """建表（幂等）。"""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS kb_tables (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                columns_json TEXT NOT NULL DEFAULT '[]',
                row_count INTEGER DEFAULT 0,
                uploaded_by TEXT DEFAULT '',
                file_name TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS kb_rows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_id TEXT NOT NULL,
                row_index INTEGER DEFAULT 0,
                data_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (table_id) REFERENCES kb_tables(id)
            );
        """)
        # FTS5 虚拟表——只在不存在时创建
        try:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS kb_rows_fts USING fts5(
                    table_id UNINDEXED,
                    content,
                    tokenize='unicode61'
                )
            """)
        except Exception:
            pass  # FTS5 可能某些构建不支持，忽略


_ensure_tables()


def _parse_excel(file_path: Path):
    """解析 Excel/CSV，返回 (columns, rows)。

    columns: ['引物名称', '靶基因', ...]
    rows:    [{'引物名称': 'lacZ-F', '靶基因': 'lacZ', ...}, ...]
    """
    import openpyxl

    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    # 第一行是表头
    header_row = next(rows_iter, None)
    if not header_row:
        wb.close()
        return [], []
    columns = [str(c or "").strip() for c in header_row]
    # 过滤空列名
    columns = [c for c in columns if c]

    data = []
    for row_idx, row in enumerate(rows_iter):
        if not row or all(c is None for c in row):
            continue
        record = {}
        for i, col in enumerate(columns):
            val = row[i] if i < len(row) else None
            if val is None:
                continue
            # 数字/公式值转字符串
            if isinstance(val, float) and val.is_integer():
                record[col] = str(int(val))
            else:
                record[col] = str(val).strip()
        if record:
            data.append(record)
    wb.close()
    return columns, data


def _parse_csv(file_path: Path):
    """简单 CSV 解析（不依赖 pandas）。"""
    import csv

    with file_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header_row = next(reader, None)
        if not header_row:
            return [], []
        columns = [c.strip() for c in header_row if c.strip()]
        data = []
        for row in reader:
            if not row or all(not c.strip() for c in row):
                continue
            record = {}
            for i, col in enumerate(columns):
                if i < len(row) and row[i].strip():
                    record[col] = row[i].strip()
            if record:
                data.append(record)
    return columns, data


def _ingest_rows(conn, table_id: str, columns: list, rows: list):
    """把行数据写入 kb_rows + FTS 索引。"""
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    for idx, row in enumerate(rows):
        data_json = json.dumps(row, ensure_ascii=False)
        conn.execute(
            "INSERT INTO kb_rows (table_id, row_index, data_json, created_at) VALUES (?,?,?,?)",
            (table_id, idx, data_json, now),
        )
        # FTS：把所有字段值拼成一个字符串做全文索引
        content = " \n ".join(v for v in row.values() if v)
        conn.execute(
            "INSERT INTO kb_rows_fts (table_id, content) VALUES (?,?)",
            (table_id, content),
        )


# ---- API ----

@router.get("/tables")
def list_tables():
    """列出所有已上传的表格（卡片信息）。"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM kb_tables ORDER BY created_at DESC"
        ).fetchall()
    tables = []
    for r in rows:
        tables.append({
            "id": r["id"],
            "name": r["name"],
            "description": r["description"],
            "columns": json.loads(r["columns_json"] or "[]"),
            "row_count": r["row_count"],
            "uploaded_by": r["uploaded_by"],
            "file_name": r["file_name"],
            "created_at": r["created_at"],
        })
    return {"tables": tables, "count": len(tables)}


@router.delete("/tables/{table_id}")
def delete_table(table_id: str):
    """删除一张表格及其所有行数据。"""
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM kb_tables WHERE id=?", (table_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="找不到该表格。")
        # 先删子表，再删主表（避免 FK 约束）
        conn.execute("DELETE FROM kb_rows WHERE table_id=?", (table_id,))
        conn.execute("DELETE FROM kb_rows_fts WHERE table_id=?", (table_id,))
        conn.execute("DELETE FROM kb_tables WHERE id=?", (table_id,))
        conn.commit()
        conn.execute("DELETE FROM kb_rows WHERE table_id=?", (table_id,))
        conn.execute("DELETE FROM kb_rows_fts WHERE table_id=?", (table_id,))
        conn.commit()
    return {"ok": True, "deleted": table_id}


@router.post("/upload")
async def upload_table(
    name: str = "",
    description: str = "",
    file: UploadFile = File(...),
):
    """上传 Excel/CSV → 解析 → 入库 + 建 FTS 索引。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="请选择文件。")

    file_id = uuid.uuid4().hex[:16]
    suffix = Path(file.filename).suffix.lower()
    stored = KB_UPLOAD_DIR / f"{file_id}_{file.filename}"

    # 保存文件
    size = 0
    with stored.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            size += len(chunk)
            if size > 50 * 1024 * 1024:
                stored.unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail="文件超过 50MB 限制")

    # 解析
    try:
        if suffix in (".xlsx", ".xls"):
            columns, rows = _parse_excel(stored)
        elif suffix == ".csv":
            columns, rows = _parse_csv(stored)
        else:
            stored.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="请上传 .xlsx 或 .csv 文件。")
    except HTTPException:
        raise
    except Exception as e:
        stored.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"解析失败：{e}")

    if not columns or not rows:
        stored.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="文件内容为空或格式不正确。")

    table_name = name.strip() or Path(file.filename).stem
    table_id = file_id
    now = time.strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO kb_tables (id, name, description, columns_json, row_count, uploaded_by, file_name, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (table_id, table_name, description.strip(), json.dumps(columns, ensure_ascii=False), len(rows), "", file.filename, now),
        )
        _ingest_rows(conn, table_id, columns, rows)
        conn.commit()

    return {
        "ok": True,
        "table_id": table_id,
        "name": table_name,
        "columns": columns,
        "row_count": len(rows),
    }


@router.get("/search")
def search(
    q: str = Query(..., min_length=1, max_length=200),
    table_id: str = Query("", description="限定在某张表内搜索"),
    limit: int = Query(50, ge=1, le=500),
):
    """全文检索：跨所有表格的所有列搜索关键词。

    支持多关键词 AND 匹配：输入「ABC 过表达」时，拆成「ABC」「过表达」两个词，
    每个词都要在该行某列中出现才算命中。单字段内只找一个词也可。
    """
    import re
    raw = q.strip()
    # 拆分关键词：空格分隔，去掉空白词
    keywords = [w for w in re.split(r'[\s,，;；、]+', raw) if w]
    if not keywords:
        keywords = [raw]
    # 清洗每个关键词（去掉 LIKE 通配符，保留中文和希腊字母）
    def sanitize(w):
        s = re.sub(r'[\\%_\[\]{}()]', '', w).strip()
        return s or w
    keywords = [sanitize(w) for w in keywords]
    # 构造每个关键词的 LIKE pattern
    like_patterns = [f"%{w}%" for w in keywords]

    with get_connection() as conn:
        tables_map = {t["id"]: dict(t) for t in conn.execute("SELECT * FROM kb_tables").fetchall()}
        if table_id:
            tables_map = {k: v for k, v in tables_map.items() if k == table_id}

        results = []
        seen = set()
        for t_id, t in tables_map.items():
            # 取出该表所有行，在 Python 里做多关键词 AND 匹配
            row_data = conn.execute(
                "SELECT data_json FROM kb_rows WHERE table_id=? ORDER BY row_index LIMIT 5000",
                (t_id,),
            ).fetchall()
            for rd in row_data:
                blob = rd["data_json"]
                # 快速预过滤：blob 必须同时包含所有关键词（子串检查）
                if not all(kw in blob for kw in keywords):
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
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break

    return {"query": q, "count": len(results), "results": results}


@router.get("/tables/{table_id}/rows")
def table_rows(table_id: str, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    """查看某张表的原始数据（分页）。"""
    with get_connection() as conn:
        t = conn.execute("SELECT * FROM kb_tables WHERE id=?", (table_id,)).fetchone()
        if not t:
            raise HTTPException(status_code=404, detail="找不到该表格。")
        rows = conn.execute(
            "SELECT data_json FROM kb_rows WHERE table_id=? ORDER BY row_index LIMIT ? OFFSET ?",
            (table_id, limit, offset),
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) as c FROM kb_rows WHERE table_id=?", (table_id,)).fetchone()
    return {
        "table": {
            "id": t["id"],
            "name": t["name"],
            "description": t["description"],
            "columns": json.loads(t["columns_json"] or "[]"),
            "row_count": t["row_count"],
        },
        "rows": [json.loads(r["data_json"]) for r in rows],
        "total": total["c"] if total else 0,
        "limit": limit,
        "offset": offset,
    }
