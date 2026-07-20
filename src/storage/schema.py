from src.storage.database import get_connection


def add_column_if_missing(cursor, table_name, column_name, column_definition):

    cursor.execute(f"PRAGMA table_info({table_name})")
    existing_columns = cursor.fetchall()
    existing_column_names = []

    for column in existing_columns:
        existing_column_names.append(column[1])

    if column_name not in existing_column_names:
        cursor.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )


def initialize_schema():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS memories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        memory_type TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        metadata TEXT,
        importance INTEGER NOT NULL DEFAULT 5,
        confidence INTEGER NOT NULL DEFAULT 100,
        source TEXT NOT NULL DEFAULT 'user',
        status TEXT NOT NULL DEFAULT 'active',
        content_hash TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT
    )
    """)

    add_column_if_missing(
        cursor=cursor,
        table_name="memories",
        column_name="confidence",
        column_definition="INTEGER NOT NULL DEFAULT 100"
    )

    add_column_if_missing(
        cursor=cursor,
        table_name="memories",
        column_name="source",
        column_definition="TEXT NOT NULL DEFAULT 'user'"
    )

    add_column_if_missing(
        cursor=cursor,
        table_name="memories",
        column_name="status",
        column_definition="TEXT NOT NULL DEFAULT 'active'"
    )

    add_column_if_missing(
        cursor=cursor,
        table_name="memories",
        column_name="content_hash",
        column_definition="TEXT"
    )

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_memories_content_hash
    ON memories(content_hash)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_memories_type_title_status
    ON memories(memory_type, title, status)
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS memory_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_memory_id INTEGER NOT NULL,
        target_memory_id INTEGER NOT NULL,
        link_type TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (source_memory_id) REFERENCES memories(id),
        FOREIGN KEY (target_memory_id) REFERENCES memories(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS memory_keywords (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        memory_id INTEGER NOT NULL,
        project TEXT NOT NULL,
        keyword TEXT NOT NULL,
        FOREIGN KEY (memory_id) REFERENCES memories(id)
    )
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_memory_keywords_project
    ON memory_keywords(project)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_memory_keywords_keyword
    ON memory_keywords(keyword)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_memory_keywords_memory_id
    ON memory_keywords(memory_id)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_memory_keywords_project_keyword
    ON memory_keywords(project, keyword)
    """)

    cursor.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_keywords_unique
    ON memory_keywords(memory_id, project, keyword)
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        description TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL,
        updated_at TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pending_memory_queue (
        pending_id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT,
        project_name TEXT NOT NULL,
        memory_type TEXT NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL,
        detected_reason TEXT,
        timestamp TEXT NOT NULL,
        proposed_supersession TEXT,
        approval_status TEXT NOT NULL DEFAULT 'pending',
        approved_memory_id INTEGER,
        updated_at TEXT
    )
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_pending_memory_queue_project_status
    ON pending_memory_queue(project_name, approval_status)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_pending_memory_queue_type
    ON pending_memory_queue(memory_type)
    """)

    cursor.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_memory_queue_unique_candidate
    ON pending_memory_queue(project_name, memory_type, title, content)
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversation_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id TEXT NOT NULL UNIQUE,
        original_sentence TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        source TEXT NOT NULL,
        approved_memory_ids TEXT
    )
    """)

    cursor.execute("""
    INSERT OR IGNORE INTO projects (
        name,
        description,
        status,
        created_at
    )
    VALUES (
        'USMOS',
        'Universal Sovereign Memory Operating System',
        'active',
        datetime('now')
    )
    """)

    conn.commit()
    conn.close()

    print("USMOS Memory Schema Initialized")
