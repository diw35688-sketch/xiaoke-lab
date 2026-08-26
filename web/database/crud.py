import uuid
from datetime import datetime
from database.db import get_connection, initialize_database


def _sync_time_statuses(connection):
    now = datetime.now()
    rows = connection.execute("SELECT id,start_at FROM experiments WHERE status='pending' AND start_at IS NOT NULL").fetchall()
    for row in rows:
        try:
            if datetime.fromisoformat(row["start_at"]) <= now:
                connection.execute("UPDATE experiments SET status='in_progress' WHERE id=?", (row["id"],))
        except (TypeError, ValueError):
            continue


def run_daily_experiment_check():
    initialize_database()
    with get_connection() as connection:
        _sync_time_statuses(connection)
        connection.execute("INSERT OR REPLACE INTO app_settings (key,value) VALUES ('last_daily_experiment_check', ?)", (datetime.now().isoformat(timespec='seconds'),))


def create_experiment(name, goal="", start_at=None, end_at=None, equipment="", notes="", plan_id=None, step_order=None, depends_on=""):
    initialize_database()
    with get_connection() as connection:
        cursor = connection.execute("""INSERT INTO experiments
            (name,goal,status,start_at,end_at,equipment,notes,plan_id,step_order,depends_on)
            VALUES (?,?,'pending',?,?,?,?,?,?,?)""", (name, goal, start_at, end_at, equipment, notes, plan_id, step_order, depends_on))
        row = connection.execute("SELECT * FROM experiments WHERE id=?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def create_experiment_plan(template_id, name, start_at, steps):
    initialize_database()
    with get_connection() as connection:
        cursor = connection.execute("INSERT INTO experiment_plans (template_id,name,start_at) VALUES (?,?,?)", (template_id, name, start_at))
        plan_id = cursor.lastrowid
        created = []
        for step in steps:
            step_cursor = connection.execute("""INSERT INTO experiments
                (name,goal,status,start_at,end_at,equipment,notes,plan_id,step_order,depends_on)
                VALUES (?,?,'pending',?,?,?,?,?,?,?)""", (
                step["name"], step["goal"], step["start_at"], step["end_at"], step["equipment"], step["notes"],
                plan_id, step["order"], ",".join(str(item) for item in step["depends_on"]),
            ))
            created.append(dict(connection.execute("SELECT * FROM experiments WHERE id=?", (step_cursor.lastrowid,)).fetchone()))
    return {"id": plan_id, "name": name, "template_id": template_id, "start_at": start_at, "steps": created}


def list_experiments(include_completed=False):
    initialize_database()
    with get_connection() as connection:
        _sync_time_statuses(connection)
        where = "" if include_completed else "WHERE status != 'completed'"
        rows = connection.execute(f"SELECT * FROM experiments {where} ORDER BY start_at IS NULL,start_at,id").fetchall()
    return [dict(row) for row in rows]


def list_history():
    initialize_database()
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM experiments WHERE status='completed' ORDER BY id DESC").fetchall()
    return [dict(row) for row in rows]


def set_experiment_status(experiment_id, status):
    if status not in {"pending", "completed"}:
        raise ValueError("状态只允许 pending 或 completed。")
    initialize_database()
    with get_connection() as connection:
        cursor = connection.execute("UPDATE experiments SET status=? WHERE id=?", (status, experiment_id))
        if not cursor.rowcount:
            return None
        row = connection.execute("SELECT * FROM experiments WHERE id=?", (experiment_id,)).fetchone()
    return dict(row)


def delete_history_item(experiment_id):
    initialize_database()
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM experiments WHERE id=? AND status='completed'", (experiment_id,))
    return bool(cursor.rowcount)


def clear_history():
    initialize_database()
    with get_connection() as connection:
        return connection.execute("DELETE FROM experiments WHERE status='completed'").rowcount


def list_memories(limit=50):
    initialize_database()
    with get_connection() as connection:
        rows = connection.execute("SELECT id,category,content,created_at FROM memories ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in reversed(rows)]


def save_memory(content, category="general"):
    initialize_database(); content = content.strip()
    if not content:
        raise ValueError("记忆内容不能为空。")
    with get_connection() as connection:
        connection.execute("INSERT OR IGNORE INTO memories (category,content) VALUES (?,?)", (category, content))
        row = connection.execute("SELECT id,category,content,created_at FROM memories WHERE content=?", (content,)).fetchone()
    return dict(row)


def create_conversation(title="新会话", conversation_id=None):
    initialize_database()
    conversation_id = conversation_id or str(uuid.uuid4())
    title = str(title or "新会话").strip() or "新会话"
    with get_connection() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO conversations (id,title) VALUES (?,?)",
            (conversation_id, title),
        )
    return conversation_id


def ensure_conversation(conversation_id=None):
    if conversation_id is None:
        return create_conversation()
    initialize_database()
    with get_connection() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO conversations (id,title) VALUES (?,?)",
            (conversation_id, "新会话"),
        )
    return conversation_id


def list_conversations(limit=50):
    initialize_database()
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT c.id,c.title,c.created_at,c.updated_at,
                      COUNT(m.id) AS message_count,
                      (SELECT content FROM messages lm
                       WHERE lm.conversation_id=c.id
                       ORDER BY lm.id DESC LIMIT 1) AS last_message
               FROM conversations c
               LEFT JOIN messages m ON m.conversation_id=c.id
               GROUP BY c.id
               ORDER BY c.updated_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def rename_conversation(conversation_id, title):
    title = str(title or "").strip()
    if not title:
        raise ValueError("会话标题不能为空。")
    initialize_database()
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE conversations SET title=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (title, conversation_id),
        )
    return bool(cursor.rowcount)


def delete_conversation(conversation_id):
    initialize_database()
    with get_connection() as connection:
        connection.execute("DELETE FROM agent_tasks WHERE conversation_id=?", (conversation_id,))
        connection.execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
        cursor = connection.execute("DELETE FROM conversations WHERE id=?", (conversation_id,))
    return bool(cursor.rowcount)


def add_message(conversation_id, role, content):
    with get_connection() as connection:
        connection.execute("INSERT INTO messages (conversation_id,role,content) VALUES (?,?,?)", (conversation_id, role, content))
        if role == "user":
            row = connection.execute(
                "SELECT title FROM conversations WHERE id=?", (conversation_id,)
            ).fetchone()
            if row is not None and row["title"] == "新会话":
                title = str(content).strip().replace("\n", " ")[:32] or "新会话"
                connection.execute(
                    "UPDATE conversations SET title=? WHERE id=?",
                    (title, conversation_id),
                )
        connection.execute("UPDATE conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (conversation_id,))


def get_recent_messages(conversation_id, limit=20):
    with get_connection() as connection:
        rows = connection.execute("SELECT role,content FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?", (conversation_id, limit)).fetchall()
    return [dict(row) for row in reversed(rows)]


def get_messages(conversation_id, limit=100):
    """按会话读取历史消息，旧消息在前。用于页面刷新后恢复显示。"""
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id,role,content,created_at FROM messages WHERE conversation_id=? ORDER BY id ASC LIMIT ?",
            (conversation_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def latest_conversation():
    """最近一次对话的 id；没有对话时返回 None。"""
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id FROM conversations ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    return row["id"] if row is not None else None


# ---------- 储存库：存储位置与存储物品 ----------

def list_storage_locations():
    initialize_database()
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM storage_locations ORDER BY enabled DESC, id"
        ).fetchall()
    return [dict(row) for row in rows]


def create_storage_location(location):
    initialize_database()
    with get_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO storage_locations (name,type,temperature,capacity,notes,enabled,grid_rows,grid_cols,map_x,map_y)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                str(location.get("name", "")).strip(),
                str(location.get("type", "其他")).strip() or "其他",
                str(location.get("temperature", "")).strip(),
                str(location.get("capacity", "")).strip(),
                str(location.get("notes", "")).strip(),
                1 if location.get("enabled", True) else 0,
                int(location.get("grid_rows", 2) or 2),
                int(location.get("grid_cols", 4) or 4),
                int(location.get("map_x", 0) or 0),
                int(location.get("map_y", 0) or 0),
            ),
        )
        row = connection.execute(
            "SELECT * FROM storage_locations WHERE id=?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


def update_storage_location(location_id, location):
    initialize_database()
    fields = []
    values = []
    for key in ("name", "type", "temperature", "capacity", "notes"):
        if key in location:
            fields.append(f"{key}=?")
            values.append(str(location[key]).strip())
    if "enabled" in location:
        fields.append("enabled=?")
        values.append(1 if location["enabled"] else 0)
    for int_key in ("grid_rows", "grid_cols", "map_x", "map_y"):
        if int_key in location:
            fields.append(f"{int_key}=?")
            values.append(int(location[int_key] or 0))
    if not fields:
        raise ValueError("没有可更新的字段。")
    values.append(location_id)
    with get_connection() as connection:
        cursor = connection.execute(
            f"UPDATE storage_locations SET {', '.join(fields)} WHERE id=?", values
        )
        if not cursor.rowcount:
            return None
        row = connection.execute(
            "SELECT * FROM storage_locations WHERE id=?", (location_id,)
        ).fetchone()
    return dict(row)


def delete_storage_location(location_id):
    initialize_database()
    with get_connection() as connection:
        connection.execute(
            "UPDATE storage_items SET location_id=NULL WHERE location_id=?", (location_id,)
        )
        cursor = connection.execute(
            "DELETE FROM storage_locations WHERE id=?", (location_id,)
        )
    return bool(cursor.rowcount)


def list_storage_items(q="", item_type="", location_id=None, status="", limit=500):
    initialize_database()
    where = []
    params = []
    if q:
        where.append("(s.name LIKE ? OR s.notes LIKE ? OR s.position LIKE ? OR s.concentration LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like, like])
    if item_type:
        where.append("item_type=?")
        params.append(item_type)
    if location_id:
        where.append("location_id=?")
        params.append(location_id)
    if status:
        where.append("status=?")
        params.append(status)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    params.append(limit)
    with get_connection() as connection:
        rows = connection.execute(
            f"""SELECT s.*, l.name AS location_name, l.temperature AS location_temperature,
                       CASE WHEN s.expires_at != '' AND s.expires_at < date('now','localtime') THEN 'expired'
                            WHEN s.expires_at != '' AND s.expires_at <= date('now','localtime','+7 day') THEN 'expiring'
                            ELSE 'ok' END AS expiry_state
                FROM storage_items s
                LEFT JOIN storage_locations l ON l.id=s.location_id
                {where_sql}
                ORDER BY s.updated_at DESC, s.id DESC
                LIMIT ?""",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def create_storage_item(item):
    initialize_database()
    with get_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO storage_items
            (item_type,name,quantity,unit,concentration,location_id,position,
             storage_condition,owner,source_experiment_id,stored_at,expires_at,status,notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                str(item.get("item_type", "其他")).strip() or "其他",
                str(item.get("name", "")).strip(),
                str(item.get("quantity", "")).strip(),
                str(item.get("unit", "")).strip(),
                str(item.get("concentration", "")).strip(),
                item.get("location_id"),
                str(item.get("position", "")).strip(),
                str(item.get("storage_condition", "")).strip(),
                str(item.get("owner", "")).strip(),
                str(item.get("source_experiment_id", "")).strip(),
                str(item.get("stored_at", "")).strip(),
                str(item.get("expires_at", "")).strip(),
                str(item.get("status", "in_storage")).strip() or "in_storage",
                str(item.get("notes", "")).strip(),
            ),
        )
        row = connection.execute(
            "SELECT * FROM storage_items WHERE id=?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


def update_storage_item(item_id, item):
    initialize_database()
    whitelist = (
        "item_type", "name", "quantity", "unit", "concentration", "location_id",
        "position", "storage_condition", "owner", "source_experiment_id",
        "stored_at", "expires_at", "status", "notes",
    )
    fields = []
    values = []
    for key in whitelist:
        if key in item:
            fields.append(f"{key}=?")
            values.append(item[key])
    if not fields:
        raise ValueError("没有可更新的字段。")
    fields.append("updated_at=CURRENT_TIMESTAMP")
    values.append(item_id)
    with get_connection() as connection:
        cursor = connection.execute(
            f"UPDATE storage_items SET {', '.join(fields)} WHERE id=?", values
        )
        if not cursor.rowcount:
            return None
        row = connection.execute(
            f"""SELECT s.*, l.name AS location_name
                FROM storage_items s LEFT JOIN storage_locations l ON l.id=s.location_id
                WHERE s.id=?""",
            (item_id,),
        ).fetchone()
    return dict(row)


def delete_storage_item(item_id):
    initialize_database()
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM storage_items WHERE id=?", (item_id,))
    return bool(cursor.rowcount)


def storage_stats():
    initialize_database()
    with get_connection() as connection:
        total = connection.execute("SELECT COUNT(*) AS c FROM storage_items").fetchone()["c"]
        by_type = {
            row["item_type"]: row["c"]
            for row in connection.execute(
                "SELECT item_type, COUNT(*) AS c FROM storage_items GROUP BY item_type"
            ).fetchall()
        }
        expiring = connection.execute(
            """SELECT COUNT(*) AS c FROM storage_items
               WHERE expires_at != '' AND expires_at > date('now','localtime')
                 AND expires_at <= date('now','localtime','+7 day')"""
        ).fetchone()["c"]
        expired = connection.execute(
            """SELECT COUNT(*) AS c FROM storage_items
               WHERE expires_at != '' AND expires_at < date('now','localtime')"""
        ).fetchone()["c"]
    return {"total": total, "by_type": by_type, "expiring": expiring, "expired": expired}


# ---------- 通知 / 每日工作弹窗 ----------

PERIODS = ("morning", "afternoon", "evening")


def period_for_now():
    """按当前时间返回 period；凌晨不弹。"""
    from datetime import datetime
    hour = datetime.now().hour
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    if 18 <= hour < 24:
        return "evening"
    return ""


def work_summary(prev_days=0):
    """按日期汇总实验记录、实验、储存库变动，用于每日工作弹窗。"""
    initialize_database()
    with get_connection() as connection:
        date_sql = "date('now', ?)" if prev_days else "date('now','localtime')"
        if prev_days:
            date_sql = "date('now','localtime',? )"
        # 今日/昨日实验记录
        if prev_days:
            records = connection.execute(
                "SELECT COUNT(*) AS c FROM lab_records WHERE date(at) = date('now','localtime',?)",
                (f"-{prev_days} day",),
            ).fetchone()["c"]
        else:
            records = connection.execute(
                "SELECT COUNT(*) AS c FROM lab_records WHERE date(at) = date('now','localtime')"
            ).fetchone()["c"]

        # 今日新增储存物品
        if prev_days:
            storage_added = connection.execute(
                "SELECT COUNT(*) AS c FROM storage_items WHERE date(stored_at) = date('now','localtime',?)",
                (f"-{prev_days} day",),
            ).fetchone()["c"]
        else:
            storage_added = connection.execute(
                "SELECT COUNT(*) AS c FROM storage_items WHERE date(stored_at) = date('now','localtime')"
            ).fetchone()["c"]

        # 今日消息数（user）
        if prev_days:
            msgs = connection.execute(
                "SELECT COUNT(*) AS c FROM messages WHERE role='user' AND date(created_at) = date('now','localtime',?)",
                (f"-{prev_days} day",),
            ).fetchone()["c"]
        else:
            msgs = connection.execute(
                "SELECT COUNT(*) AS c FROM messages WHERE role='user' AND date(created_at) = date('now','localtime')"
            ).fetchone()["c"]

    today_records = records
    storage_total = storage_added
    user_messages = msgs
    return {
        "records": today_records,
        "storage_added": storage_total,
        "user_messages": user_messages,
    }


def get_notification_by_period(period, period_date):
    initialize_database()
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM notifications WHERE period=? AND period_date=? ORDER BY id DESC LIMIT 1",
            (period, period_date),
        ).fetchone()
    return dict(row) if row else None


def create_daily_notification(period, period_date, title, body):
    initialize_database()
    with get_connection() as connection:
        existing = connection.execute(
            "SELECT * FROM notifications WHERE period=? AND period_date=? LIMIT 1",
            (period, period_date),
        ).fetchone()
        if existing:
            return dict(existing)
        cursor = connection.execute(
            "INSERT INTO notifications (kind,period,period_date,title,body,source) VALUES ('daily',?,?,?,?,?)",
            (period, period_date, title, body, "system"),
        )
        notification_id = cursor.lastrowid
        summary = work_summary(0)
        stats = storage_stats()
        default_todos = [
            f"确认今日实验记录 {summary['records']} 条",
            f"整理今日新增储存 {summary['storage_added']} 项",
            f"检查用户消息 {summary['user_messages']} 条",
        ]
        if stats.get("expiring") or stats.get("expired"):
            default_todos.append(f"处理储存过期提醒 {stats.get('expiring', 0) + stats.get('expired', 0)} 项")
        for text in default_todos:
            connection.execute(
                "INSERT INTO notification_todos (notification_id,text) VALUES (?,?)",
                (notification_id, text),
            )
        row = connection.execute(
            "SELECT * FROM notifications WHERE id=?", (notification_id,)
        ).fetchone()
    return dict(row)


def mark_notification_shown(notification_id):
    initialize_database()
    with get_connection() as connection:
        connection.execute(
            "UPDATE notifications SET shown_at=CURRENT_TIMESTAMP WHERE id=?",
            (notification_id,),
        )
        row = connection.execute(
            "SELECT * FROM notifications WHERE id=?", (notification_id,)
        ).fetchone()
    return dict(row) if row else None


def mark_notification_ack(notification_id):
    initialize_database()
    with get_connection() as connection:
        connection.execute(
            "UPDATE notifications SET acknowledged_at=CURRENT_TIMESTAMP WHERE id=?",
            (notification_id,),
        )
        row = connection.execute(
            "SELECT * FROM notifications WHERE id=?", (notification_id,)
        ).fetchone()
    return dict(row) if row else None


def list_notifications(limit=50, unread_only=False):
    initialize_database()
    with get_connection() as connection:
        if unread_only:
            rows = connection.execute(
                "SELECT * FROM notifications WHERE acknowledged_at='' ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(row) for row in rows]


# ---------- 通知待办清单 ----------

def list_notification_todos(notification_id):
    initialize_database()
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM notification_todos WHERE notification_id=? ORDER BY done,id",
            (notification_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def add_notification_todo(notification_id, text):
    text = str(text or "").strip()
    if not text:
        raise ValueError("待办内容不能为空。")
    initialize_database()
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO notification_todos (notification_id,text) VALUES (?,?)",
            (notification_id, text),
        )
        row = connection.execute(
            "SELECT * FROM notification_todos WHERE id=?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


def update_notification_todo(todo_id, text=None, done=None):
    initialize_database()
    fields = []
    values = []
    if text is not None:
        text = str(text or "").strip()
        if not text:
            raise ValueError("待办内容不能为空。")
        fields.append("text=?")
        values.append(text)
    if done is not None:
        fields.append("done=?")
        values.append(1 if done else 0)
    if not fields:
        raise ValueError("没有可更新的字段。")
    values.append(todo_id)
    with get_connection() as connection:
        cursor = connection.execute(
            f"UPDATE notification_todos SET {', '.join(fields)} WHERE id=?", values
        )
        if not cursor.rowcount:
            return None
        row = connection.execute(
            "SELECT * FROM notification_todos WHERE id=?", (todo_id,)
        ).fetchone()
    return dict(row)


def delete_notification_todo(todo_id):
    initialize_database()
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM notification_todos WHERE id=?", (todo_id,))
    return bool(cursor.rowcount)


# ---------- 社区 ----------

def list_community_entries(q="", kind="", limit=200):
    initialize_database()
    where = []
    params = []
    if q:
        where.append("(title LIKE ? OR tags LIKE ? OR author LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])
    if kind:
        where.append("kind=?")
        params.append(kind)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    params.append(limit)
    with get_connection() as connection:
        rows = connection.execute(
            f"SELECT id,kind,title,author,tags,downloads,status,created_at,updated_at,content_json FROM community_entries {where_sql} ORDER BY id DESC LIMIT ?",
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def get_community_entry(entry_id):
    initialize_database()
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM community_entries WHERE id=?", (entry_id,)).fetchone()
    return dict(row) if row else None


def create_community_entry(kind, title, content_json, author="", tags=""):
    initialize_database()
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO community_entries (kind,title,author,tags,content_json) VALUES (?,?,?,?,?)",
            (kind, title, author, tags, content_json),
        )
        row = connection.execute("SELECT * FROM community_entries WHERE id=?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def increment_community_downloads(entry_id):
    initialize_database()
    with get_connection() as connection:
        connection.execute("UPDATE community_entries SET downloads=downloads+1 WHERE id=?", (entry_id,))
        row = connection.execute("SELECT * FROM community_entries WHERE id=?", (entry_id,)).fetchone()
    return dict(row) if row else None


def delete_community_entry(entry_id):
    initialize_database()
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM community_entries WHERE id=?", (entry_id,))
    return bool(cursor.rowcount)
