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


def ensure_conversation(conversation_id=None):
    initialize_database(); conversation_id = conversation_id or str(uuid.uuid4())
    with get_connection() as connection:
        connection.execute("INSERT OR IGNORE INTO conversations (id) VALUES (?)", (conversation_id,))
    return conversation_id


def add_message(conversation_id, role, content):
    with get_connection() as connection:
        connection.execute("INSERT INTO messages (conversation_id,role,content) VALUES (?,?,?)", (conversation_id, role, content))
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