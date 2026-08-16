import sqlite3
from config import DATABASE_PATH


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _ensure_column(connection, table, name, definition):
    columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    if name not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def initialize_database():
    with get_connection() as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            goal TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending',
            start_at TEXT, end_at TEXT, equipment TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        _ensure_column(connection, "experiments", "status", "TEXT NOT NULL DEFAULT 'pending'")
        _ensure_column(connection, "experiments", "plan_id", "INTEGER")
        _ensure_column(connection, "experiments", "step_order", "INTEGER")
        _ensure_column(connection, "experiments", "depends_on", "TEXT NOT NULL DEFAULT ''")
        connection.execute("UPDATE experiments SET status='pending' WHERE status IS NULL OR status NOT IN ('pending','in_progress','completed')")
        connection.execute("""CREATE TABLE IF NOT EXISTS experiment_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT, template_id TEXT NOT NULL,
            name TEXT NOT NULL, start_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id))""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id,id)")
        connection.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("""CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL DEFAULT 'general',
            content TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS agent_tasks (
            id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, kind TEXT NOT NULL,
            prompt TEXT NOT NULL, status TEXT NOT NULL,
            progress TEXT NOT NULL DEFAULT '', result TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
            delivered_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at TEXT, completed_at TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id))""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_agent_tasks_conversation ON agent_tasks(conversation_id,created_at)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_agent_tasks_status ON agent_tasks(status,created_at)")
        # 实验语音记录：口述原文 + 抽取结果 + 确定性判断，整体 JSON 落盘。
        # 与 conversations/messages 分工不同：后者是聊天流水，这里是结构化实验记录。
        connection.execute("""CREATE TABLE IF NOT EXISTS lab_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            segment_id INTEGER NOT NULL,
            transcript TEXT NOT NULL,
            entities TEXT NOT NULL DEFAULT '{}',
            extraction TEXT,
            extraction_source TEXT NOT NULL DEFAULT 'none',
            evaluation TEXT NOT NULL DEFAULT '{}',
            step TEXT,
            at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, segment_id))""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_lab_records_session ON lab_records(session_id, segment_id)")
