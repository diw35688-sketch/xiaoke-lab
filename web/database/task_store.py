import uuid
from database.db import get_connection, initialize_database


def _row(row):
    return dict(row) if row else None


def create_task(conversation_id, prompt, kind="agent_request"):
    initialize_database()
    task_id = str(uuid.uuid4())[:8]
    with get_connection() as connection:
        connection.execute("""INSERT INTO agent_tasks (id,conversation_id,kind,prompt,status,progress)
            VALUES (?,?,?,?, 'queued', '已进入后台队列')""", (task_id, conversation_id, kind, prompt))
        row = connection.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
    return _row(row)


def get_task(task_id):
    initialize_database()
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
    return _row(row)


def list_tasks(conversation_id, limit=20):
    initialize_database()
    with get_connection() as connection:
        rows = connection.execute("SELECT * FROM agent_tasks WHERE conversation_id=? ORDER BY created_at DESC LIMIT ?", (conversation_id, limit)).fetchall()
    return [_row(row) for row in rows]


def claim_task(task_id):
    with get_connection() as connection:
        cursor = connection.execute("""UPDATE agent_tasks SET status='running', progress='正在调用实验助手与工具',
            started_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='queued'""", (task_id,))
        if not cursor.rowcount:
            return None
        row = connection.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
    return _row(row)


def set_progress(task_id, progress):
    with get_connection() as connection:
        connection.execute("UPDATE agent_tasks SET progress=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND status IN ('queued','running','cancelling')", (progress, task_id))


def complete_task(task_id, result):
    with get_connection() as connection:
        task = _row(connection.execute("SELECT status FROM agent_tasks WHERE id=?", (task_id,)).fetchone())
        if not task or task["status"] in {"cancelled", "cancelling"}:
            connection.execute("UPDATE agent_tasks SET status='cancelled',progress='任务已取消',completed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?", (task_id,))
        else:
            connection.execute("""UPDATE agent_tasks SET status='completed', progress='任务已完成', result=?,
                completed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=?""", (result, task_id))
        row = connection.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
    return _row(row)


def fail_task(task_id, error):
    with get_connection() as connection:
        connection.execute("""UPDATE agent_tasks SET status='failed',progress='任务执行失败',error=?,
            completed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=? AND status NOT IN ('cancelled','cancelling')""", (error, task_id))
        row = connection.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
    return _row(row)


def cancel_task(task_id):
    with get_connection() as connection:
        task = _row(connection.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone())
        if not task:
            return None
        if task["status"] == "queued":
            connection.execute("UPDATE agent_tasks SET status='cancelled',progress='任务已取消',completed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?", (task_id,))
        elif task["status"] == "running":
            connection.execute("UPDATE agent_tasks SET status='cancelling',progress='正在取消，当前调用结束后停止',updated_at=CURRENT_TIMESTAMP WHERE id=?", (task_id,))
        row = connection.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
    return _row(row)


def get_undelivered_results(conversation_id):
    with get_connection() as connection:
        rows = connection.execute("""SELECT * FROM agent_tasks WHERE conversation_id=? AND status IN ('completed','failed')
            AND delivered_at IS NULL ORDER BY completed_at,id""", (conversation_id,)).fetchall()
        if rows:
            connection.executemany("UPDATE agent_tasks SET delivered_at=CURRENT_TIMESTAMP WHERE id=?", [(row["id"],) for row in rows])
    return [_row(row) for row in rows]


def queued_task_ids():
    initialize_database()
    with get_connection() as connection:
        rows = connection.execute("SELECT id FROM agent_tasks WHERE status='queued' ORDER BY created_at").fetchall()
    return [row["id"] for row in rows]
