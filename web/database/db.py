import sqlite3
from contextlib import closing

from config import DATABASE_PATH


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _ensure_column(connection, table, name, definition):
    columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    if name not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def initialize_database():
    with closing(get_connection()) as connection, connection:
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
        _ensure_column(connection, "lab_records", "request_id", "TEXT")
        _ensure_column(connection, "lab_records", "conversation_id", "TEXT")
        _ensure_column(connection, "lab_records", "turn_id", "TEXT")
        _ensure_column(connection, "messages", "request_id", "TEXT")
        _ensure_column(connection, "messages", "turn_id", "TEXT")
        _ensure_column(connection, "messages", "block_id", "TEXT")
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_lab_records_request_id "
            "ON lab_records(request_id) WHERE request_id IS NOT NULL"
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_messages_request_role "
            "ON messages(request_id, role) WHERE request_id IS NOT NULL"
        )
        connection.execute("""CREATE TABLE IF NOT EXISTS turn_requests (
            request_id TEXT PRIMARY KEY,
            turn_id TEXT NOT NULL UNIQUE,
            conversation_id TEXT NOT NULL,
            lab_session_id TEXT,
            interaction_mode TEXT NOT NULL,
            experiment_context TEXT NOT NULL,
            mode_version INTEGER NOT NULL,
            input_source TEXT NOT NULL,
            raw_text TEXT,
            request_hash TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('processing','committed','failed')),
            attempt INTEGER NOT NULL DEFAULT 1,
            result_json TEXT,
            timing_json TEXT NOT NULL DEFAULT '{}',
            error_code TEXT,
            error_detail TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            committed_at TEXT,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id))""")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_turn_requests_conversation "
            "ON turn_requests(conversation_id, created_at)"
        )
        connection.execute("""CREATE TABLE IF NOT EXISTS asr_evidence (
            request_id TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            audio_rel_path TEXT NOT NULL,
            audio_sha256 TEXT NOT NULL,
            audio_bytes INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(request_id) REFERENCES turn_requests(request_id) ON DELETE CASCADE)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS experiment_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            event_index INTEGER NOT NULL,
            event_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(request_id, event_index),
            FOREIGN KEY(request_id) REFERENCES turn_requests(request_id) ON DELETE CASCADE)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS experiment_session_state (
            conversation_id TEXT NOT NULL,
            lab_session_id TEXT NOT NULL,
            revision INTEGER NOT NULL,
            reply_coordinator_json TEXT NOT NULL,
            session_context_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(conversation_id, lab_session_id),
            FOREIGN KEY(conversation_id) REFERENCES conversations(id))""")
