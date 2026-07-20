import json
from datetime import datetime

from src.storage.database import get_connection


ALLOWED_MEMORY_TYPES = {
    "project_note",
    "decision",
    "task",
    "event",
    "checkpoint"
}


def read_memory(memory_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        id,
        memory_type,
        title,
        content,
        metadata,
        importance,
        status,
        created_at,
        updated_at
    FROM memories
    WHERE id = ?
    """, (memory_id,))

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return {
        "id": row[0],
        "memory_type": row[1],
        "title": row[2],
        "content": row[3],
        "metadata": json.loads(row[4]) if row[4] else None,
        "importance": row[5],
        "status": row[6],
        "created_at": row[7],
        "updated_at": row[8]
    }


def list_memories(memory_type=None):

    conn = get_connection()
    cursor = conn.cursor()

    if memory_type is None:
        cursor.execute("""
        SELECT
            id,
            memory_type,
            title,
            content,
            metadata,
            importance,
            status,
            created_at,
            updated_at
        FROM memories
        WHERE status = 'active'
        ORDER BY importance DESC, id DESC
        """)
    else:
        cursor.execute("""
        SELECT
            id,
            memory_type,
            title,
            content,
            metadata,
            importance,
            status,
            created_at,
            updated_at
        FROM memories
        WHERE status = 'active'
        AND memory_type = ?
        ORDER BY importance DESC, id DESC
        """, (memory_type,))

    rows = cursor.fetchall()
    conn.close()

    memories = []

    for row in rows:
        memories.append({
            "id": row[0],
            "memory_type": row[1],
            "title": row[2],
            "content": row[3],
            "metadata": json.loads(row[4]) if row[4] else None,
            "importance": row[5],
            "status": row[6],
            "created_at": row[7],
            "updated_at": row[8]
        })

    return memories


def memory_exists(memory_type, title, project_name=None):

    memories = list_memories(memory_type=memory_type)

    for memory in memories:
        same_title = memory["title"] == title

        metadata = memory.get("metadata") or {}
        same_project = metadata.get("project") == project_name if project_name else True

        if same_title and same_project:
            return True

    return False


def create_memory(memory_type, title, content, metadata=None, importance=5):

    if not isinstance(importance, int):
        raise ValueError("importance must be an integer")

    if importance < 1 or importance > 10:
        raise ValueError("importance must be between 1 and 10")

    if not memory_type:
        raise ValueError("memory_type is required")

    if memory_type not in ALLOWED_MEMORY_TYPES:
        raise ValueError(f"Invalid memory_type: {memory_type}")

    if not title:
        raise ValueError("title is required")

    if not content:
        raise ValueError("content is required")

    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("metadata must be a dictionary")

    project_name = metadata.get("project") if metadata else None

    if memory_exists(memory_type, title, project_name):
        return {
            "success": False,
            "memory_id": None,
            "message": "Duplicate memory blocked"
        }

    metadata_json = json.dumps(metadata) if metadata else None
    created_at = datetime.now().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO memories (
        memory_type,
        title,
        content,
        metadata,
        importance,
        status,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        memory_type,
        title,
        content,
        metadata_json,
        importance,
        "active",
        created_at
    ))

    conn.commit()
    memory_id = cursor.lastrowid
    conn.close()

    return {
        "success": True,
        "memory_id": memory_id,
        "message": "Memory created successfully"
    }


def update_memory(memory_id, title=None, content=None):

    existing_memory = read_memory(memory_id)

    if existing_memory is None:
        return False

    new_title = title if title is not None else existing_memory["title"]
    new_content = content if content is not None else existing_memory["content"]
    updated_at = datetime.now().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE memories
    SET
        title = ?,
        content = ?,
        updated_at = ?
    WHERE id = ?
    """, (
        new_title,
        new_content,
        updated_at,
        memory_id
    ))

    conn.commit()
    conn.close()

    return True


def update_memory_metadata(memory_id, new_metadata):

    if not isinstance(new_metadata, dict):
        return {
            "success": False,
            "message": "new_metadata must be a dictionary"
        }

    existing_memory = read_memory(memory_id)

    if existing_memory is None:
        return {
            "success": False,
            "message": "Memory not found"
        }

    current_metadata = existing_memory.get("metadata") or {}
    current_metadata.update(new_metadata)

    metadata_json = json.dumps(current_metadata)
    updated_at = datetime.now().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE memories
    SET
        metadata = ?,
        updated_at = ?
    WHERE id = ?
    """, (
        metadata_json,
        updated_at,
        memory_id
    ))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Memory metadata updated successfully"
    }


def delete_memory(memory_id):

    existing_memory = read_memory(memory_id)

    if existing_memory is None:
        return False

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE memories
    SET status = 'inactive'
    WHERE id = ?
    """, (memory_id,))

    conn.commit()
    conn.close()

    return True