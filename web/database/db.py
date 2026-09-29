import sqlite3
import logging
from contextlib import closing

from config import DATABASE_PATH

logger = logging.getLogger("web.database.db")

# ── Schema 版本管理 ──
# 当前 schema 版本。每次有破坏性 schema 变更时递增，
# 并在 _MIGRATIONS 里加入对应版本的迁移函数。
SCHEMA_VERSION = 1


def _get_schema_version(connection) -> int:
    """读取数据库当前 schema 版本。首次创建返回 0。"""
    try:
        row = connection.execute(
            "SELECT value FROM app_settings WHERE key = 'schema_version'"
        ).fetchone()
        return int(row["value"]) if row else 0
    except (sqlite3.OperationalError, ValueError):
        return 0


def _set_schema_version(connection, version: int) -> None:
    connection.execute(
        "INSERT INTO app_settings (key, value) VALUES ('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(version),),
    )


# 迁移函数注册表：version → callable(connection)
# 每个函数从 (version-1) 升级到 version。
_MIGRATIONS: dict[int, callable] = {}


def migration(version: int):
    """注册一个迁移函数。"""
    def decorator(fn):
        _MIGRATIONS[version] = fn
        return fn
    return decorator


@migration(1)
def _migrate_v1(connection):
    """v1: 初始版本——所有现有表和列已由 initialize_database 创建。

    这个迁移只是记录基准版本，不做额外操作。
    后续 schema 变更从这里开始增量迁移。
    """
    pass


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _ensure_column(connection, table, name, definition):
    columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    if name not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def initialize_database():
    with closing(get_connection()) as connection, connection:
        connection.execute("PRAGMA journal_mode=WAL")
        # 用户与登录会话：函数内导入，避免 user_store -> db 的模块级循环依赖。
        from database.user_store import ensure_schema as _ensure_user_schema
        _ensure_user_schema(connection)
        connection.execute("""CREATE TABLE IF NOT EXISTS phone_login_codes (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at_ms INTEGER NOT NULL,
            expires_at_ms INTEGER NOT NULL)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            goal TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending',
            start_at TEXT, end_at TEXT, equipment TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        _ensure_column(connection, "experiments", "status", "TEXT NOT NULL DEFAULT 'pending'")
        _ensure_column(connection, "experiments", "plan_id", "INTEGER")
        _ensure_column(connection, "experiments", "step_order", "INTEGER")
        _ensure_column(connection, "experiments", "depends_on", "TEXT NOT NULL DEFAULT ''")
        connection.execute("""CREATE TABLE IF NOT EXISTS experiment_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT, template_id TEXT NOT NULL,
            name TEXT NOT NULL, start_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        _ensure_column(connection, "conversations", "title", "TEXT NOT NULL DEFAULT '新会话'")
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
        connection.execute("""CREATE TABLE IF NOT EXISTS reagent_prep_flows (
            conversation_id TEXT PRIMARY KEY,
            prep_id TEXT NOT NULL,
            current_index INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'running',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        # 复合步骤（例如一次称取多种试剂）拆成的小步骤，落进状态机持久记录：
        # {"0": ["称取胰化蛋白胨 2 g...", "称取酵母提取物 0.5 g...", ...], "1": [...]}
        # 由 AI 拆分后通过 set_reagent_prep_substeps 写入，advance 据此确定性推进，
        # 不再依赖模型每轮的记忆。
        _ensure_column(connection, "reagent_prep_flows", "sub_steps_json", "TEXT NOT NULL DEFAULT '{}'")
        _ensure_column(connection, "reagent_prep_flows", "current_sub_index", "INTEGER NOT NULL DEFAULT 0")
        # 储存库：全局存储位置与存储物品资产库
        connection.execute("""CREATE TABLE IF NOT EXISTS storage_locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT '其他',
            temperature TEXT NOT NULL DEFAULT '',
            capacity TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS storage_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_type TEXT NOT NULL DEFAULT '其他',
            name TEXT NOT NULL,
            quantity TEXT NOT NULL DEFAULT '',
            unit TEXT NOT NULL DEFAULT '',
            concentration TEXT NOT NULL DEFAULT '',
            location_id INTEGER,
            position TEXT NOT NULL DEFAULT '',
            storage_condition TEXT NOT NULL DEFAULT '',
            owner TEXT NOT NULL DEFAULT '',
            source_experiment_id TEXT NOT NULL DEFAULT '',
            stored_at TEXT NOT NULL DEFAULT '',
            expires_at TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'in_storage',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(location_id) REFERENCES storage_locations(id))""")
        _ensure_column(connection, 'storage_locations', 'grid_rows', 'INTEGER NOT NULL DEFAULT 2')
        _ensure_column(connection, 'storage_locations', 'grid_cols', 'INTEGER NOT NULL DEFAULT 4')
        _ensure_column(connection, 'storage_locations', 'map_x', 'INTEGER NOT NULL DEFAULT 0')
        _ensure_column(connection, 'storage_locations', 'map_y', 'INTEGER NOT NULL DEFAULT 0')
        connection.execute("CREATE INDEX IF NOT EXISTS idx_storage_items_location ON storage_items(location_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_storage_items_name ON storage_items(name)")
        # 通知/每日工作弹窗：记录创建、展示、确认，用于溯源
        connection.execute("""CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL DEFAULT 'daily',
            period TEXT NOT NULL DEFAULT '',
            period_date TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            shown_at TEXT NOT NULL DEFAULT '',
            acknowledged_at TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '')""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_notifications_period ON notifications(period_date,period)")
        connection.execute("""CREATE TABLE IF NOT EXISTS notification_todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notification_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(notification_id) REFERENCES notifications(id))""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_notification_todos_notification ON notification_todos(notification_id,id)")
        # 社区：用户发布/导入试剂配方与实验方案
        connection.execute("""CREATE TABLE IF NOT EXISTS community_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            author TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '',
            content_json TEXT NOT NULL,
            downloads INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'published',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        _ensure_column(connection, "community_entries", "likes", "INTEGER NOT NULL DEFAULT 0")
        connection.execute("""CREATE TABLE IF NOT EXISTS community_likes (
            entry_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(entry_id, user_id),
            FOREIGN KEY(entry_id) REFERENCES community_entries(id) ON DELETE CASCADE)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS community_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id INTEGER NOT NULL,
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(entry_id) REFERENCES community_entries(id) ON DELETE CASCADE)""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_community_likes_entry ON community_likes(entry_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_community_comments_entry ON community_comments(entry_id,id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_community_kind ON community_entries(kind)")
        # 论文/Protocol 文件上传：保存原文件、OCR 文本和方案草稿，便于回看与二次生成。
        connection.execute("""CREATE TABLE IF NOT EXISTS paper_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '',
            filename TEXT NOT NULL DEFAULT '',
            file_path TEXT NOT NULL DEFAULT '',
            ocr_text TEXT NOT NULL DEFAULT '',
            drafts_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            user_id TEXT)""")
        # 持久化 cron 任务：对应 OpenClaw 的 cron job 表。
        connection.execute("""CREATE TABLE IF NOT EXISTS cron_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            declaration_key TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL,
            schedule_kind TEXT NOT NULL CHECK(schedule_kind IN ('at','every','cron')),
            at TEXT NOT NULL DEFAULT '',
            every_ms INTEGER NOT NULL DEFAULT 0,
            cron_expr TEXT NOT NULL DEFAULT '',
            cron_tz TEXT NOT NULL DEFAULT 'local',
            enabled INTEGER NOT NULL DEFAULT 1,
            payload_kind TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            last_run_at TEXT NOT NULL DEFAULT '',
            next_run_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_cron_jobs_next ON cron_jobs(enabled,next_run_at)")
        connection.execute("""CREATE TABLE IF NOT EXISTS conversation_compactions (
            conversation_id TEXT PRIMARY KEY,
            summary TEXT NOT NULL,
            summarized_until_id INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
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
        _ensure_column(
            connection,
            "experiment_session_state",
            "protocol_step_facts_json",
            "TEXT NOT NULL DEFAULT '{}'",
        )

        # ---- 数据归属 ----
        # 归属根只有这几张表；其余带 conversation_id 的表顺着会话继承归属，
        # 这样不会出现「消息属于甲、会话属于乙」的矛盾状态。
        # 列可为空：升级时既有数据先成为「无主」，由第一个注册的账号认领
        # （见 user_store.claim_orphaned_data），避免升级即丢数据。
        for _owned_table in ("conversations", "memories", "notifications", "experiments"):
            _ensure_column(connection, _owned_table, "user_id", "TEXT")
        # 实验记录署名：id 可追溯，name 是当时的显示名快照（见 attribution.py）。
        _ensure_column(connection, "lab_records", "recorded_by_id", "TEXT")
        _ensure_column(connection, "lab_records", "recorded_by_name", "TEXT")
        _ensure_column(connection, "community_entries", "author_id", "TEXT")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id,updated_at)")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id)")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id)")
        # 方案准备清单缓存：LLM 提取结果持久化，避免每次重启都重新调用。
        # step_signature = "总步数:步骤数"，方案修改后签名变化 → 自动失效重算。
        connection.execute("""CREATE TABLE IF NOT EXISTS protocol_checklists (
            protocol_id TEXT NOT NULL,
            step_signature TEXT NOT NULL,
            extracted_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(protocol_id, step_signature))""")
        # 步骤时间画像：LLM 提取的每步时长、类型(active/passive/flexible)、
        # 占用设备、并行建议。跟准备清单一样持久化缓存。
        connection.execute("""CREATE TABLE IF NOT EXISTS step_time_profiles (
            protocol_id TEXT NOT NULL,
            step_signature TEXT NOT NULL,
            profiles_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(protocol_id, step_signature))""")
        # 方案选择偏好：用户在搜索到多个匹配方案时选了哪个，记住偏好。
        # 下次同样的关键词搜索时自动选定，不再反复追问。
        connection.execute("""CREATE TABLE IF NOT EXISTS protocol_preferences (
            keyword TEXT NOT NULL,
            protocol_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(keyword))""")
        # 实验准备台：一次实验的准备单（挂在本次实验，不是方案上）。
        # prep_run 是协议级的，prep_run_items 是逐条试剂/仪器/耗材。
        # auto_state = 系统判定（ready/prep_now/missing），manual_state = 用户覆盖。
        connection.execute("""CREATE TABLE IF NOT EXISTS prep_runs (
            prep_run_id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL DEFAULT 'lab-session',
            protocol_id TEXT NOT NULL,
            protocol_title TEXT NOT NULL DEFAULT '',
            scale_unit TEXT NOT NULL DEFAULT '',
            scale_basis TEXT NOT NULL DEFAULT '',
            default_scale TEXT NOT NULL DEFAULT '',
            user_scale TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'preparing',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS prep_run_items (
            prep_run_item_id TEXT PRIMARY KEY,
            prep_run_id TEXT NOT NULL,
            item_key TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'reagent',
            name TEXT NOT NULL,
            auto_state TEXT NOT NULL DEFAULT 'missing',
            manual_state TEXT NOT NULL DEFAULT '',
            reagent_prep_id TEXT NOT NULL DEFAULT '',
            storage_hint TEXT NOT NULL DEFAULT '',
            quantity TEXT NOT NULL DEFAULT '',
            estimated_minutes INTEGER,
            time_sensitivity TEXT NOT NULL DEFAULT 'normal',
            note TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(prep_run_id) REFERENCES prep_runs(prep_run_id) ON DELETE CASCADE)""")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_prep_run_items_run ON prep_run_items(prep_run_id, sort_order)")

        # ── 运行增量迁移 ──
        current_version = _get_schema_version(connection)
        if current_version < SCHEMA_VERSION:
            for version in range(current_version + 1, SCHEMA_VERSION + 1):
                fn = _MIGRATIONS.get(version)
                if fn:
                    logger.info("Running schema migration v%d", version)
                    fn(connection)
            _set_schema_version(connection, SCHEMA_VERSION)
            logger.info("Schema upgraded to v%d (was v%d)", SCHEMA_VERSION, current_version)
