import hashlib
import json


from datetime import datetime
from pathlib import Path
from time import perf_counter

from src.storage import database
from src.storage.database import get_connection

ALLOWED_MEMORY_TYPES = {
    "project_note",
    "decision",
    "task",
    "event",
    "checkpoint"
}

ALLOWED_LINK_TYPES = {
    "created",
    "creates",
    "depends_on",
    "caused",
    "causes",
    "relates_to",
    "blocks",
    "completes",
    "completed_by",
    "checkpoint_of",
    "snapshot_of",
    "superseded_by"
}

MEMORY_LIFECYCLE_STATUSES = {
    "active",
    "superseded",
    "archived"
}

SNAPSHOT_DIR = Path("sandbox/snapshots")
CURRENT_PROJECT_FILE = Path("sandbox/current_project.json")
BENCHMARK_DIR = Path("sandbox/benchmarks")
BENCHMARK_REPORT_DIR = Path("sandbox/benchmark_reports")
DEFAULT_PROJECT_NAME = "USMOS"
SQLITE_BATCH_SIZE = 500

PHASE_ORDER = [
    "Phase 1",
    "Phase 2",
    "Phase 3",
    "Phase 4",
    "Phase 5",
    "Phase 6",
    "Phase 7",
    "Phase 8",
    "Phase 9",
    "Phase 10",
    "Phase 11",
    "Phase 12",
    "Phase 13",
    "Phase 14"
]

PHASE_LABELS = {
    "Phase 1": "Phase 1 Memory Foundation",
    "Phase 2": "Phase 2 Recall + Context Builder",
    "Phase 3": "Phase 3 Memory Answer + Snapshot Restore",
    "Phase 4": "Phase 4 Memory Quality Layer",
    "Phase 5": "Phase 5 Explainable Memory Reasoning",
    "Phase 6": "Phase 6 Project State Recovery Engine",
    "Phase 7": "Phase 7 Local CLI Interface",
    "Phase 8": "Phase 8 Memory Graph Engine",
    "Phase 9": "Phase 9 Local UI Dashboard",
    "Phase 10": "Phase 10 Local Document Ingestion Layer",
    "Phase 11": "Phase 11 Memory Evolution Engine",
    "Phase 12": "Phase 12 Multi-Project Workspace Engine",
    "Phase 13": "Phase 13 Large-Scale Sovereign Memory Benchmark Engine",
    "Phase 14": "Phase 14 Token-Accurate 30M Benchmark Engine"
}

SUPPORTED_INGESTION_EXTENSIONS = {
    ".txt",
    ".md"
}

INGESTION_IMPORTANCE = {
    "decision": 8,
    "task": 6,
    "event": 5,
    "checkpoint": 9,
    "project_note": 4
}

STRUCTURED_INGESTION_PREFIXES = [
    "decision:",
    "task:",
    "checkpoint:",
    "event:",
    "fact:"
]

SEMANTIC_KEYWORD_GROUPS = {
    "cloud": [
        "cloud",
        "api",
        "internet",
        "external service",
        "network"
    ],
    "security": [
        "local",
        "local-only",
        "local only",
        "sandbox",
        "secure",
        "privacy",
        "user-controlled"
    ],
    "checkpoint": [
        "phase",
        "checkpoint",
        "milestone",
        "completed"
    ]
}

SECURITY_KEYWORDS = [
    "local-only",
    "local only",
    "no cloud",
    "sandbox",
    "secure",
    "security",
    "privacy",
    "user-controlled"
]


def line_has_structured_ingestion_prefix(line):

    line_lower = line.lower()

    for prefix in STRUCTURED_INGESTION_PREFIXES:
        if line_lower.startswith(prefix):
            return True

    return False


def text_contains_any_keyword(text, keywords):

    text_lower = text.lower()

    for keyword in keywords:
        if keyword in text_lower:
            return True

    return False


def get_matching_semantic_groups(text):

    matching_groups = []

    for group_name, keywords in SEMANTIC_KEYWORD_GROUPS.items():
        if text_contains_any_keyword(text, keywords):
            matching_groups.append(group_name)

    return matching_groups


def clean_project_name(name):

    if not isinstance(name, str):
        raise ValueError("project name must be a string")

    clean_name = name.strip()

    if not clean_name:
        raise ValueError("project name is required")

    return clean_name


def row_to_project(row):

    return {
        "id": row[0],
        "name": row[1],
        "description": row[2] or "",
        "status": row[3],
        "created_at": row[4],
        "updated_at": row[5]
    }


def create_project(name, description=""):

    project_name = clean_project_name(name)
    created_at = datetime.now().isoformat()

    if get_project(project_name) is not None:
        return {
            "success": False,
            "project": get_project(project_name),
            "message": "Project already exists"
        }

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO projects (
        name,
        description,
        status,
        created_at
    )
    VALUES (?, ?, ?, ?)
    """, (
        project_name,
        description,
        "active",
        created_at
    ))

    conn.commit()
    project_id = cursor.lastrowid
    conn.close()

    return {
        "success": True,
        "project_id": project_id,
        "name": project_name,
        "message": "Project created successfully"
    }


def list_projects(include_archived=False):

    conn = get_connection()
    cursor = conn.cursor()

    if include_archived:
        cursor.execute("""
        SELECT
            id,
            name,
            description,
            status,
            created_at,
            updated_at
        FROM projects
        ORDER BY name ASC
        """)
    else:
        cursor.execute("""
        SELECT
            id,
            name,
            description,
            status,
            created_at,
            updated_at
        FROM projects
        WHERE status = 'active'
        ORDER BY name ASC
        """)

    rows = cursor.fetchall()
    conn.close()

    projects = []

    for row in rows:
        projects.append(row_to_project(row))

    return projects


def get_project(name):

    project_name = clean_project_name(name)
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        id,
        name,
        description,
        status,
        created_at,
        updated_at
    FROM projects
    WHERE name = ?
    """, (project_name,))

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return row_to_project(row)


def archive_project(name):

    project = get_project(name)

    if project is None:
        return {
            "success": False,
            "message": "Project not found"
        }

    updated_at = datetime.now().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE projects
    SET
        status = 'archived',
        updated_at = ?
    WHERE name = ?
    """, (
        updated_at,
        project["name"]
    ))

    conn.commit()
    conn.close()

    if get_current_project() == project["name"]:
        set_current_project(DEFAULT_PROJECT_NAME)

    return {
        "success": True,
        "name": project["name"],
        "message": "Project archived successfully"
    }


def set_current_project(name):

    project_name = clean_project_name(name)
    project = get_project(project_name)

    if project is None:
        return {
            "success": False,
            "message": "Project not found"
        }

    if project["status"] != "active":
        return {
            "success": False,
            "message": "Cannot switch to an archived project"
        }

    CURRENT_PROJECT_FILE.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "project": project_name,
        "updated_at": datetime.now().isoformat()
    }

    with CURRENT_PROJECT_FILE.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)

    return {
        "success": True,
        "project": project_name,
        "message": "Current project updated"
    }


def get_current_project():

    if not CURRENT_PROJECT_FILE.exists():
        return DEFAULT_PROJECT_NAME

    try:
        with CURRENT_PROJECT_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return DEFAULT_PROJECT_NAME

    project_name = data.get("project")

    if not project_name:
        return DEFAULT_PROJECT_NAME

    return project_name


def add_default_project_to_metadata(metadata):

    if metadata is None:
        metadata = {}
    else:
        metadata = metadata.copy()

    if not metadata.get("project"):
        metadata["project"] = get_current_project()

    return metadata


def normalize_memory_content(content):

    return " ".join(content.strip().lower().split())


def compute_memory_hash(project_name, memory_type, content):

    normalized_content = normalize_memory_content(content)
    hash_input = (
        project_name
        + "|"
        + memory_type
        + "|"
        + normalized_content
    )

    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


def chunk_list(items, chunk_size=SQLITE_BATCH_SIZE):

    for index in range(0, len(items), chunk_size):
        yield items[index:index + chunk_size]


def normalize_keyword(keyword):

    clean_keyword = " ".join(keyword.strip().lower().split())
    clean_keyword = clean_keyword.strip(".,!?;:'\"()[]{}")

    if (
        " " not in clean_keyword
        and clean_keyword.endswith("s")
        and not clean_keyword.endswith("ss")
        and not clean_keyword.endswith("us")
        and len(clean_keyword) > 3
    ):
        clean_keyword = clean_keyword[:-1]

    return clean_keyword


def extract_keyword_words(text):

    clean_characters = []

    for character in text.lower():
        if character.isalnum() or character == "-":
            clean_characters.append(character)
        else:
            clean_characters.append(" ")

    words = []

    for word in "".join(clean_characters).split():
        normalized_word = normalize_keyword(word)

        if len(normalized_word) > 3:
            words.append(normalized_word)

    return words


def extract_semantic_keywords(text):

    keywords = []

    for group_keywords in SEMANTIC_KEYWORD_GROUPS.values():
        if text_contains_any_keyword(text, group_keywords):
            for keyword in group_keywords:
                normalized_keyword = normalize_keyword(keyword)

                if normalized_keyword not in keywords:
                    keywords.append(normalized_keyword)

    return keywords


def extract_memory_keywords(memory_type, title, content, metadata=None):

    metadata = metadata or {}
    combined_text = title + " " + content
    keywords = []

    for keyword in extract_keyword_words(combined_text):
        if keyword not in keywords:
            keywords.append(keyword)

    for keyword in extract_semantic_keywords(combined_text):
        if keyword not in keywords:
            keywords.append(keyword)

    memory_type_keyword = normalize_keyword(memory_type)

    if memory_type_keyword and memory_type_keyword not in keywords:
        keywords.append(memory_type_keyword)

    topic = metadata.get("topic")

    if topic:
        topic_keyword = normalize_keyword(topic)

        if topic_keyword and topic_keyword not in keywords:
            keywords.append(topic_keyword)

    return keywords


def extract_query_keywords(question, topic=None):

    keywords = []

    for keyword in extract_keyword_words(question):
        if keyword not in keywords:
            keywords.append(keyword)

    for keyword in extract_semantic_keywords(question):
        if keyword not in keywords:
            keywords.append(keyword)

    if topic:
        topic_keyword = normalize_keyword(topic)

        if topic_keyword and topic_keyword not in keywords:
            keywords.append(topic_keyword)

    return keywords


def replace_memory_keywords(memory_id, project_name, keywords):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    DELETE FROM memory_keywords
    WHERE memory_id = ?
    """, (memory_id,))

    rows = []

    for keyword in keywords:
        if keyword:
            rows.append((memory_id, project_name, keyword))

    if rows:
        cursor.executemany("""
        INSERT OR IGNORE INTO memory_keywords (
            memory_id,
            project,
            keyword
        )
        VALUES (?, ?, ?)
        """, rows)

    conn.commit()
    conn.close()


def index_memory_keywords(memory_id):

    memory = read_memory(memory_id)

    if memory is None:
        return {
            "success": False,
            "keyword_count": 0,
            "message": "Memory not found"
        }

    metadata = memory.get("metadata") or {}
    project_name = metadata.get("project") or get_current_project()
    keywords = extract_memory_keywords(
        memory_type=memory["memory_type"],
        title=memory["title"],
        content=memory["content"],
        metadata=metadata
    )

    replace_memory_keywords(
        memory_id=memory_id,
        project_name=project_name,
        keywords=keywords
    )

    return {
        "success": True,
        "keyword_count": len(keywords),
        "message": "Memory keywords indexed"
    }


def batch_index_memory_keywords(memory_ids):

    started_at = perf_counter()
    unique_memory_ids = []
    seen_memory_ids = set()

    for memory_id in memory_ids:
        if memory_id and memory_id not in seen_memory_ids:
            unique_memory_ids.append(memory_id)
            seen_memory_ids.add(memory_id)

    if not unique_memory_ids:
        return {
            "success": True,
            "memory_count": 0,
            "keyword_count": 0,
            "duration_seconds": 0,
            "message": "No memories to index"
        }

    conn = get_connection()
    cursor = conn.cursor()
    memory_count = 0
    keyword_count = 0

    for memory_id_chunk in chunk_list(unique_memory_ids):
        placeholders = ", ".join("?" for _ in memory_id_chunk)

        cursor.execute(f"""
        DELETE FROM memory_keywords
        WHERE memory_id IN ({placeholders})
        """, memory_id_chunk)

        cursor.execute(f"""
        SELECT
            id,
            memory_type,
            title,
            content,
            metadata
        FROM memories
        WHERE id IN ({placeholders})
        AND status != 'inactive'
        """, memory_id_chunk)

        rows = cursor.fetchall()
        keyword_rows = []

        for row in rows:
            memory_id = row[0]
            memory_type = row[1]
            title = row[2]
            content = row[3]
            metadata = json.loads(row[4]) if row[4] else {}
            project_name = metadata.get("project") or get_current_project()
            keywords = extract_memory_keywords(
                memory_type=memory_type,
                title=title,
                content=content,
                metadata=metadata
            )

            memory_count += 1

            for keyword in keywords:
                if keyword:
                    keyword_rows.append((memory_id, project_name, keyword))

        if keyword_rows:
            cursor.executemany("""
            INSERT OR IGNORE INTO memory_keywords (
                memory_id,
                project,
                keyword
            )
            VALUES (?, ?, ?)
            """, keyword_rows)
            keyword_count += len(keyword_rows)

    conn.commit()
    conn.close()
    duration_seconds = perf_counter() - started_at

    return {
        "success": True,
        "memory_count": memory_count,
        "keyword_count": keyword_count,
        "duration_seconds": round(duration_seconds, 6),
        "message": "Memory keywords indexed in batch"
    }


def backfill_memory_keywords():

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
        confidence,
        source,
        status,
        content_hash,
        created_at,
        updated_at
    FROM memories
    WHERE status != 'inactive'
    AND NOT EXISTS (
        SELECT 1
        FROM memory_keywords
        WHERE memory_keywords.memory_id = memories.id
    )
    ORDER BY id ASC
    """)

    rows = cursor.fetchall()
    conn.close()
    memory_ids = []

    for row in rows:
        memory_ids.append(row[0])

    result = batch_index_memory_keywords(memory_ids)

    return {
        "success": True,
        "updated": result["memory_count"]
    }


def calculate_trust_score(memory):

    importance = memory.get("importance", 5)
    confidence = memory.get("confidence", 100)

    return (importance * 5) + confidence


def classify_memory_freshness(memory):

    created_at = memory.get("created_at")

    if not created_at:
        return "stale"

    try:
        created_datetime = datetime.fromisoformat(created_at)
    except ValueError:
        return "stale"

    age = datetime.now() - created_datetime
    age_in_days = age.days

    if age_in_days <= 30:
        return "fresh"

    if age_in_days < 180:
        return "aging"

    return "stale"


def row_to_memory(row):

    if len(row) >= 12:
        memory = {
            "id": row[0],
            "memory_type": row[1],
            "title": row[2],
            "content": row[3],
            "metadata": json.loads(row[4]) if row[4] else None,
            "importance": row[5],
            "confidence": row[6],
            "source": row[7],
            "status": row[8],
            "content_hash": row[9],
            "created_at": row[10],
            "updated_at": row[11]
        }
    elif len(row) >= 11:
        memory = {
            "id": row[0],
            "memory_type": row[1],
            "title": row[2],
            "content": row[3],
            "metadata": json.loads(row[4]) if row[4] else None,
            "importance": row[5],
            "confidence": row[6],
            "source": row[7],
            "status": row[8],
            "content_hash": None,
            "created_at": row[9],
            "updated_at": row[10]
        }
    else:
        memory = {
            "id": row[0],
            "memory_type": row[1],
            "title": row[2],
            "content": row[3],
            "metadata": json.loads(row[4]) if row[4] else None,
            "importance": row[5],
            "confidence": 100,
            "source": "user",
            "status": row[6],
            "content_hash": None,
            "created_at": row[7],
            "updated_at": row[8]
        }

    memory["trust_score"] = calculate_trust_score(memory)
    memory["freshness"] = classify_memory_freshness(memory)

    return memory


def create_memory(
    memory_type,
    title,
    content,
    metadata=None,
    importance=5,
    confidence=100,
    source="user"
):

    if not isinstance(importance, int):
        raise ValueError("importance must be an integer")

    if importance < 1 or importance > 10:
        raise ValueError("importance must be between 1 and 10")

    if not isinstance(confidence, int):
        raise ValueError("confidence must be an integer")

    if confidence < 0 or confidence > 100:
        raise ValueError("confidence must be between 0 and 100")

    if not source:
        raise ValueError("source is required")

    if not isinstance(source, str):
        raise ValueError("source must be a string")

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

    metadata = add_default_project_to_metadata(metadata)
    project_name = metadata.get("project") if metadata else None
    content_hash = compute_memory_hash(project_name, memory_type, content)

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
        confidence,
        source,
        status,
        content_hash,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        memory_type,
        title,
        content,
        metadata_json,
        importance,
        confidence,
        source,
        "active",
        content_hash,
        created_at
    ))

    conn.commit()
    memory_id = cursor.lastrowid
    conn.close()
    index_memory_keywords(memory_id)

    return {
        "success": True,
        "memory_id": memory_id,
        "message": "Memory created successfully"
    }


def prepare_batch_memory_item(item):

    memory_type = item.get("memory_type")
    title = item.get("title")
    content = item.get("content")
    metadata = item.get("metadata")
    importance = item.get("importance", 5)
    confidence = item.get("confidence", 100)
    source = item.get("source", "user")

    if not isinstance(importance, int):
        raise ValueError("importance must be an integer")

    if importance < 1 or importance > 10:
        raise ValueError("importance must be between 1 and 10")

    if not isinstance(confidence, int):
        raise ValueError("confidence must be an integer")

    if confidence < 0 or confidence > 100:
        raise ValueError("confidence must be between 0 and 100")

    if not source:
        raise ValueError("source is required")

    if not isinstance(source, str):
        raise ValueError("source must be a string")

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

    metadata = add_default_project_to_metadata(metadata)
    project_name = metadata.get("project") if metadata else get_current_project()
    content_hash = compute_memory_hash(project_name, memory_type, content)

    return {
        "memory_type": memory_type,
        "title": title,
        "content": content,
        "metadata": metadata,
        "metadata_json": json.dumps(metadata) if metadata else None,
        "importance": importance,
        "confidence": confidence,
        "source": source,
        "project": project_name,
        "content_hash": content_hash
    }


def select_memories_by_content_hashes(content_hashes):

    unique_hashes = []
    seen_hashes = set()

    for content_hash in content_hashes:
        if content_hash and content_hash not in seen_hashes:
            unique_hashes.append(content_hash)
            seen_hashes.add(content_hash)

    if not unique_hashes:
        return {}

    conn = get_connection()
    cursor = conn.cursor()
    memories_by_hash = {}

    for hash_chunk in chunk_list(unique_hashes):
        placeholders = ", ".join("?" for _ in hash_chunk)

        cursor.execute(f"""
        SELECT
            id,
            memory_type,
            title,
            content,
            metadata,
            importance,
            confidence,
            source,
            status,
            content_hash,
            created_at,
            updated_at
        FROM memories
        WHERE content_hash IN ({placeholders})
        AND status != 'inactive'
        """, hash_chunk)

        rows = cursor.fetchall()

        for row in rows:
            memory = row_to_memory(row)

            if memory["content_hash"] not in memories_by_hash:
                memories_by_hash[memory["content_hash"]] = memory

    conn.close()

    return memories_by_hash


def batch_create_memories(memory_items):

    batch_started_at = perf_counter()
    prepared_items = []

    for item in memory_items:
        prepared_items.append(prepare_batch_memory_item(item))

    duplicate_check_started_at = perf_counter()
    content_hashes = []

    for item in prepared_items:
        content_hashes.append(item["content_hash"])

    existing_memories_by_hash = select_memories_by_content_hashes(content_hashes)
    duplicate_check_duration = perf_counter() - duplicate_check_started_at

    items_to_insert = []
    seen_new_hashes = {}
    item_results = []
    duplicate_count = 0

    for item in prepared_items:
        content_hash = item["content_hash"]

        if content_hash in existing_memories_by_hash:
            duplicate_memory = existing_memories_by_hash[content_hash]
            duplicate_count += 1
            item_results.append({
                "memory_type": item["memory_type"],
                "title": item["title"],
                "content": item["content"],
                "status": "duplicate",
                "memory_id": duplicate_memory["id"],
                "duplicate_memory": duplicate_memory,
                "content_hash": content_hash,
                "message": "Duplicate memory blocked"
            })
            continue

        if content_hash in seen_new_hashes:
            duplicate_count += 1
            item_results.append({
                "memory_type": item["memory_type"],
                "title": item["title"],
                "content": item["content"],
                "status": "duplicate",
                "memory_id": None,
                "duplicate_memory": None,
                "content_hash": content_hash,
                "message": "Duplicate memory blocked"
            })
            continue

        seen_new_hashes[content_hash] = item
        items_to_insert.append(item)
        item_results.append({
            "memory_type": item["memory_type"],
            "title": item["title"],
            "content": item["content"],
            "status": "pending",
            "memory_id": None,
            "duplicate_memory": None,
            "content_hash": content_hash,
            "message": "Waiting for batch insert"
        })

    insert_started_at = perf_counter()
    created_ids = []
    created_id_by_hash = {}
    created_at = datetime.now().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    for item in items_to_insert:
        cursor.execute("""
        INSERT INTO memories (
            memory_type,
            title,
            content,
            metadata,
            importance,
            confidence,
            source,
            status,
            content_hash,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item["memory_type"],
            item["title"],
            item["content"],
            item["metadata_json"],
            item["importance"],
            item["confidence"],
            item["source"],
            "active",
            item["content_hash"],
            created_at
        ))

        memory_id = cursor.lastrowid
        created_ids.append(memory_id)
        created_id_by_hash[item["content_hash"]] = memory_id

    conn.commit()
    conn.close()
    insert_duration = perf_counter() - insert_started_at

    for item_result in item_results:
        if item_result["status"] == "pending":
            memory_id = created_id_by_hash[item_result["content_hash"]]
            item_result["status"] = "created"
            item_result["memory_id"] = memory_id
            item_result["message"] = "Memory created successfully"
            continue

        if (
            item_result["status"] == "duplicate"
            and item_result["memory_id"] is None
            and item_result["content_hash"] in created_id_by_hash
        ):
            item_result["memory_id"] = created_id_by_hash[item_result["content_hash"]]

    keyword_index_started_at = perf_counter()
    keyword_result = batch_index_memory_keywords(created_ids)
    keyword_index_duration = perf_counter() - keyword_index_started_at
    total_duration = perf_counter() - batch_started_at

    return {
        "success": True,
        "created": len(created_ids),
        "created_ids": created_ids,
        "duplicates": duplicate_count,
        "items": item_results,
        "duplicate_check_duration": round(duplicate_check_duration, 6),
        "insert_duration": round(insert_duration, 6),
        "keyword_index_duration": round(keyword_index_duration, 6),
        "total_duration": round(total_duration, 6),
        "keyword_index": keyword_result,
        "message": "Batch memory creation complete"
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
        confidence,
        source,
        status,
        content_hash,
        created_at,
        updated_at
    FROM memories
    WHERE id = ?
    """, (memory_id,))

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return row_to_memory(row)


def update_memory(memory_id, title=None, content=None):

    existing_memory = read_memory(memory_id)

    if existing_memory is None:
        return False

    new_title = title if title is not None else existing_memory["title"]
    new_content = content if content is not None else existing_memory["content"]
    metadata = existing_memory.get("metadata") or {}
    project_name = metadata.get("project") or get_current_project()
    content_hash = compute_memory_hash(
        project_name=project_name,
        memory_type=existing_memory["memory_type"],
        content=new_content
    )
    updated_at = datetime.now().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE memories
    SET
        title = ?,
        content = ?,
        content_hash = ?,
        updated_at = ?
    WHERE id = ?
    """, (
        new_title,
        new_content,
        content_hash,
        updated_at,
        memory_id
    ))

    conn.commit()
    conn.close()
    index_memory_keywords(memory_id)

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
    index_memory_keywords(memory_id)

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


def update_memory_status(memory_id, status):

    if status not in MEMORY_LIFECYCLE_STATUSES:
        return {
            "success": False,
            "message": f"Invalid memory status: {status}"
        }

    existing_memory = read_memory(memory_id)

    if existing_memory is None:
        return {
            "success": False,
            "message": "Memory not found"
        }

    updated_at = datetime.now().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE memories
    SET
        status = ?,
        updated_at = ?
    WHERE id = ?
    """, (
        status,
        updated_at,
        memory_id
    ))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": f"Memory status updated to {status}"
    }


def list_all_memories(memory_type=None):

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
            confidence,
            source,
            status,
            content_hash,
            created_at,
            updated_at
        FROM memories
        WHERE status != 'inactive'
        ORDER BY id DESC
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
            confidence,
            source,
            status,
            content_hash,
            created_at,
            updated_at
        FROM memories
        WHERE status != 'inactive'
        AND memory_type = ?
        ORDER BY id DESC
        """, (memory_type,))

    rows = cursor.fetchall()
    conn.close()

    memories = []

    for row in rows:
        memories.append(row_to_memory(row))

    memories.sort(
        key=lambda memory: (
            memory["trust_score"],
            memory["id"]
        ),
        reverse=True
    )

    return memories


def get_active_memories():

    return list_memories()


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
            confidence,
            source,
            status,
            content_hash,
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
            confidence,
            source,
            status,
            content_hash,
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
        memories.append(row_to_memory(row))

    memories.sort(
        key=lambda memory: (
            memory["trust_score"],
            memory["id"]
        ),
        reverse=True
    )

    return memories


def memory_exists(memory_type, title, project_name=None):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        metadata
    FROM memories
    WHERE status = 'active'
    AND memory_type = ?
    AND title = ?
    """, (
        memory_type,
        title
    ))

    rows = cursor.fetchall()
    conn.close()

    for row in rows:
        metadata = json.loads(row[0]) if row[0] else {}
        same_project = metadata.get("project") == project_name if project_name else True

        if same_project:
            return True

    return False


def create_decision(
    title,
    content,
    metadata=None,
    importance=8,
    confidence=100,
    source="user"
):

    return create_memory(
        memory_type="decision",
        title=title,
        content=content,
        metadata=metadata,
        importance=importance,
        confidence=confidence,
        source=source
    )


def create_task(
    title,
    content,
    metadata=None,
    importance=6,
    confidence=100,
    source="user"
):

    return create_memory(
        memory_type="task",
        title=title,
        content=content,
        metadata=metadata,
        importance=importance,
        confidence=confidence,
        source=source
    )


def create_event(
    title,
    content,
    metadata=None,
    importance=5,
    confidence=100,
    source="user"
):

    return create_memory(
        memory_type="event",
        title=title,
        content=content,
        metadata=metadata,
        importance=importance,
        confidence=confidence,
        source=source
    )


def create_project_note(
    title,
    content,
    metadata=None,
    importance=5,
    confidence=100,
    source="user"
):

    return create_memory(
        memory_type="project_note",
        title=title,
        content=content,
        metadata=metadata,
        importance=importance,
        confidence=confidence,
        source=source
    )


def split_text_into_memory_chunks(text):

    chunks = []
    current_lines = []

    for line in text.splitlines():
        clean_line = line.strip()

        if not clean_line:
            if current_lines:
                chunks.append(" ".join(current_lines))
                current_lines = []

            continue

        if line_has_structured_ingestion_prefix(clean_line):
            if current_lines:
                chunks.append(" ".join(current_lines))
                current_lines = []

            chunks.append(clean_line)
            continue

        current_lines.append(clean_line)

    if current_lines:
        chunks.append(" ".join(current_lines))

    meaningful_chunks = []

    for chunk in chunks:
        if len(chunk.strip()) >= 8 or line_has_structured_ingestion_prefix(chunk):
            meaningful_chunks.append(chunk.strip())

    return meaningful_chunks


def detect_ingested_memory_type(text):

    text_lower = text.lower()

    if text_lower.startswith("decision:"):
        return "decision"

    if text_lower.startswith("task:"):
        return "task"

    if text_lower.startswith("checkpoint:"):
        return "checkpoint"

    if text_lower.startswith("event:"):
        return "event"

    if text_lower.startswith("fact:"):
        return "project_note"

    checkpoint_words = [
        "phase complete",
        "checkpoint",
        "milestone",
        "snapshot"
    ]
    decision_words = [
        "decided",
        "decision",
        "we chose",
        "must use",
        "rule"
    ]
    task_words = [
        "todo",
        "task",
        "implement",
        "build",
        "next step"
    ]
    event_words = [
        "completed",
        "verified",
        "passed",
        "done"
    ]

    for word in checkpoint_words:
        if word in text_lower:
            return "checkpoint"

    for word in decision_words:
        if word in text_lower:
            return "decision"

    for word in task_words:
        if word in text_lower:
            return "task"

    for word in event_words:
        if word in text_lower:
            return "event"

    return "project_note"


def text_contains_security_keyword(text):

    return text_contains_any_keyword(text, SECURITY_KEYWORDS)


def detect_ingested_topic(text):

    if text_contains_security_keyword(text):
        return "security"

    return None


def normalize_ingested_content(text):

    return normalize_memory_content(text)


def select_memory_by_content_hash(content_hash):

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
        confidence,
        source,
        status,
        content_hash,
        created_at,
        updated_at
    FROM memories
    WHERE content_hash = ?
    AND status != 'inactive'
    LIMIT 1
    """, (content_hash,))

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return row_to_memory(row)


def backfill_content_hashes():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        id,
        memory_type,
        content,
        metadata
    FROM memories
    WHERE content_hash IS NULL
    OR content_hash = ''
    """)

    rows = cursor.fetchall()
    updated_count = 0

    for row in rows:
        memory_id = row[0]
        memory_type = row[1]
        content = row[2]
        metadata = json.loads(row[3]) if row[3] else {}
        project_name = metadata.get("project") or get_current_project()
        content_hash = compute_memory_hash(
            project_name=project_name,
            memory_type=memory_type,
            content=content
        )

        cursor.execute("""
        UPDATE memories
        SET content_hash = ?
        WHERE id = ?
        """, (
            content_hash,
            memory_id
        ))
        updated_count += 1

    conn.commit()
    conn.close()

    return {
        "success": True,
        "updated": updated_count
    }


def ingested_memory_exists(project_name, memory_type, content):

    content_hash = compute_memory_hash(
        project_name=project_name,
        memory_type=memory_type,
        content=content
    )

    return select_memory_by_content_hash(content_hash)


def enrich_duplicate_ingested_metadata(memory, detected_topic, file_path):

    if detected_topic != "security":
        return False

    metadata = memory.get("metadata") or {}
    updates = {}

    if metadata.get("topic") != "security":
        updates["topic"] = "security"

    if not metadata.get("source"):
        updates["source"] = "document_ingestion"

    if not metadata.get("ingested_from"):
        updates["ingested_from"] = str(file_path)

    if not updates:
        return False

    result = update_memory_metadata(
        memory_id=memory["id"],
        new_metadata=updates
    )

    return result["success"]


def build_ingested_memory_title(memory_type, text):

    type_label = memory_type.replace("_", " ").title()
    clean_text = " ".join(text.split())

    if len(clean_text) > 70:
        clean_text = clean_text[:67] + "..."

    return f"Ingested {type_label}: {clean_text}"


def create_ingested_memory(memory_type, title, content, metadata):

    importance = INGESTION_IMPORTANCE[memory_type]

    if memory_type == "decision":
        return create_decision(
            title=title,
            content=content,
            metadata=metadata,
            importance=importance,
            source="document_ingestion"
        )

    if memory_type == "task":
        return create_task(
            title=title,
            content=content,
            metadata=metadata,
            importance=importance,
            source="document_ingestion"
        )

    if memory_type == "event":
        return create_event(
            title=title,
            content=content,
            metadata=metadata,
            importance=importance,
            source="document_ingestion"
        )

    if memory_type == "checkpoint":
        return create_checkpoint(
            title=title,
            content=content,
            metadata=metadata,
            importance=importance,
            source="document_ingestion"
        )

    return create_project_note(
        title=title,
        content=content,
        metadata=metadata,
        importance=importance,
        source="document_ingestion"
    )


def ingest_text_file(file_path, project_name="USMOS"):

    total_started_at = perf_counter()
    path = Path(file_path)

    if path.suffix.lower() not in SUPPORTED_INGESTION_EXTENSIONS:
        return {
            "success": False,
            "file": str(file_path),
            "created": 0,
            "duplicates": 0,
            "memories": [],
            "message": "Only .txt and .md files are supported."
        }

    if not path.exists():
        return {
            "success": False,
            "file": str(file_path),
            "created": 0,
            "duplicates": 0,
            "memories": [],
            "message": "File not found."
        }

    parse_started_at = perf_counter()
    text = path.read_text(encoding="utf-8")
    chunks = split_text_into_memory_chunks(text)
    metadata = {
        "project": project_name,
        "memory_scope": "real",
        "source": "document_ingestion",
        "ingested_from": str(file_path)
    }
    memory_items = []
    parsed_entries = []

    for chunk in chunks:
        memory_type = detect_ingested_memory_type(chunk)
        title = build_ingested_memory_title(memory_type, chunk)
        chunk_metadata = metadata.copy()
        topic = detect_ingested_topic(chunk)

        if topic:
            chunk_metadata["topic"] = topic

        memory_items.append({
            "memory_type": memory_type,
            "title": title,
            "content": chunk,
            "metadata": chunk_metadata,
            "importance": INGESTION_IMPORTANCE[memory_type],
            "confidence": 100,
            "source": "document_ingestion"
        })
        parsed_entries.append({
            "memory_type": memory_type,
            "title": title,
            "content": chunk,
            "topic": topic
        })

    parse_duration = perf_counter() - parse_started_at
    backfill_started_at = perf_counter()
    backfill_content_hashes()
    backfill_duration = perf_counter() - backfill_started_at
    batch_result = batch_create_memories(memory_items)
    memories = []

    for index, item_result in enumerate(batch_result["items"]):
        parsed_entry = parsed_entries[index]
        status = item_result["status"]
        enriched = False

        if status == "duplicate":
            duplicate_memory = item_result.get("duplicate_memory")

            if duplicate_memory is not None:
                enriched = enrich_duplicate_ingested_metadata(
                    memory=duplicate_memory,
                    detected_topic=parsed_entry["topic"],
                    file_path=file_path
                )

            if enriched:
                status = "duplicate_enriched"

        memory_summary = {
            "memory_type": parsed_entry["memory_type"],
            "title": parsed_entry["title"],
            "content": parsed_entry["content"],
            "status": status,
            "memory_id": item_result["memory_id"],
            "message": item_result["message"]
        }

        if item_result["status"] == "duplicate":
            memory_summary["enriched"] = enriched

        memories.append(memory_summary)

    duplicate_check_duration = (
        backfill_duration
        + batch_result["duplicate_check_duration"]
    )
    total_duration = perf_counter() - total_started_at

    return {
        "success": True,
        "file": str(file_path),
        "created": batch_result["created"],
        "duplicates": batch_result["duplicates"],
        "memories": memories,
        "_timings": {
            "parse_duration": round(parse_duration, 6),
            "duplicate_check_duration": round(duplicate_check_duration, 6),
            "insert_duration": batch_result["insert_duration"],
            "keyword_index_duration": batch_result["keyword_index_duration"],
            "total_duration": round(total_duration, 6)
        }
    }


def summarize_ingestion_result(result):

    if not result["success"]:
        return (
            "Ingestion failed\n\n"
            f"File: {result['file']}\n"
            f"Reason: {result['message']}"
        )

    lines = []
    lines.append("Document Ingestion Summary")
    lines.append("")
    lines.append(f"File: {result['file']}")
    lines.append(f"Created: {result['created']}")
    lines.append(f"Duplicates skipped: {result['duplicates']}")
    lines.append("")
    lines.append("Memories:")

    if not result["memories"]:
        lines.append("- No meaningful text found.")
    else:
        for memory in result["memories"]:
            lines.append(
                f"- {memory['status']}: "
                f"{memory['memory_type']} - {memory['title']}"
            )

    return "\n".join(lines)


def build_benchmark_file_path(project_name, memory_count):

    clean_project_name = project_name.strip().replace(" ", "_")
    file_name = f"{clean_project_name}_{memory_count}.md"

    return BENCHMARK_DIR / file_name


def build_token_benchmark_file_path(project_name, target_tokens):

    clean_project_name = project_name.strip().replace(" ", "_")
    file_name = f"{clean_project_name}_{target_tokens}_tokens.md"

    return BENCHMARK_DIR / file_name


def build_benchmark_report_path(project_name, memory_count):

    clean_project_name = project_name.strip().replace(" ", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    file_name = f"{clean_project_name}_{memory_count}_{timestamp}.json"

    return BENCHMARK_REPORT_DIR / file_name


def get_file_size_mb(file_path):

    path = Path(file_path)

    if not path.exists():
        return 0

    return round(path.stat().st_size / (1024 * 1024), 6)


def get_database_size_mb():

    return get_file_size_mb(database.DB_PATH)


def build_benchmark_line(project_name, index):

    line_number = index + 1
    line_type = index % 5
    padded_number = str(line_number).zfill(6)

    if line_type == 0:
        return (
            f"Decision: {project_name} benchmark decision {padded_number} "
            "must avoid cloud APIs and use local-only memory."
        )

    if line_type == 1:
        return (
            f"Task: {project_name} benchmark task {padded_number} "
            "build local ingestion and recall checks."
        )

    if line_type == 2:
        return (
            f"Checkpoint: {project_name} benchmark checkpoint {padded_number} "
            "phase completed successfully."
        )

    if line_type == 3:
        return (
            f"Event: {project_name} benchmark event {padded_number} "
            "completed local verification."
        )

    return (
        f"Fact: {project_name} benchmark fact {padded_number} "
        "sandbox memory stays user-controlled."
    )


def estimate_token_count(text):

    return len(text.split())


def generate_benchmark_file(output_path, project_name, memory_count):

    if not isinstance(memory_count, int):
        raise ValueError("memory_count must be an integer")

    if memory_count < 1:
        raise ValueError("memory_count must be at least 1")

    benchmark_path = Path(output_path)
    benchmark_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []

    for index in range(memory_count):
        lines.append(build_benchmark_line(project_name, index))

    benchmark_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "success": True,
        "file": str(benchmark_path),
        "project": project_name,
        "memory_count": memory_count
    }


def generate_token_benchmark_file(output_path, project_name, target_tokens):

    if not isinstance(target_tokens, int):
        raise ValueError("target_tokens must be an integer")

    if target_tokens < 1:
        raise ValueError("target_tokens must be at least 1")

    benchmark_path = Path(output_path)
    benchmark_path.parent.mkdir(parents=True, exist_ok=True)
    estimated_tokens = 0
    line_count = 0

    with benchmark_path.open("w", encoding="utf-8") as file:
        while estimated_tokens < target_tokens:
            line = build_benchmark_line(project_name, line_count)
            file.write(line + "\n")
            estimated_tokens += estimate_token_count(line)
            line_count += 1

    return {
        "success": True,
        "file": str(benchmark_path),
        "project": project_name,
        "target_tokens": target_tokens,
        "estimated_tokens_generated": estimated_tokens,
        "line_count": line_count,
        "file_size_mb": get_file_size_mb(benchmark_path)
    }


def benchmark_ingestion(file_path, project_name):

    started_at = datetime.now().isoformat()
    start_time = perf_counter()

    ingestion_result = ingest_text_file(
        file_path=file_path,
        project_name=project_name
    )

    duration_seconds = perf_counter() - start_time
    ended_at = datetime.now().isoformat()
    timings = ingestion_result.get("_timings", {})
    total_memories_after = len(
        list_memories_by_project(
            project_name=project_name,
            include_history=True
        )
    )

    return {
        "file": str(file_path),
        "project": project_name,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": round(duration_seconds, 6),
        "parse_duration": timings.get("parse_duration", 0),
        "duplicate_check_duration": timings.get("duplicate_check_duration", 0),
        "insert_duration": timings.get("insert_duration", 0),
        "keyword_index_duration": timings.get("keyword_index_duration", 0),
        "total_duration": timings.get("total_duration", round(duration_seconds, 6)),
        "created": ingestion_result["created"],
        "duplicates": ingestion_result["duplicates"],
        "total_memories_after": total_memories_after,
        "success": ingestion_result["success"]
    }


def benchmark_recall(project_name, questions):

    started_at = datetime.now().isoformat()
    suite_start_time = perf_counter()
    results = []

    for question in questions:
        question_start_time = perf_counter()
        answer = answer_from_memory(
            question=question,
            project_name=project_name
        )
        question_duration = perf_counter() - question_start_time
        answer_found = "No relevant memory found" not in answer

        results.append({
            "question": question,
            "answer": answer,
            "answer_found": answer_found,
            "duration_seconds": round(question_duration, 6)
        })

    duration_seconds = perf_counter() - suite_start_time
    ended_at = datetime.now().isoformat()

    return {
        "project": project_name,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": round(duration_seconds, 6),
        "results": results,
        "success": True
    }


def benchmark_recall_index(project_name, questions):

    started_at = datetime.now().isoformat()
    suite_start_time = perf_counter()
    results = []

    for question in questions:
        question_start_time = perf_counter()
        analysis = analyze_question(question)
        topic = analysis.get("topic")

        if topic is None:
            topic = detect_question_topic(question)

        keyword_candidates = extract_query_keywords(question, topic)
        memories = search_memories_by_keyword_index(
            project_name=project_name,
            keywords=keyword_candidates,
            limit=10
        )
        question_duration = perf_counter() - question_start_time

        results.append({
            "question": question,
            "keyword_candidates": keyword_candidates,
            "answer_found": len(memories) > 0,
            "memory_count": len(memories),
            "memory_ids": [memory["id"] for memory in memories],
            "duration_seconds": round(question_duration, 6)
        })

    duration_seconds = perf_counter() - suite_start_time
    ended_at = datetime.now().isoformat()

    return {
        "project": project_name,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": round(duration_seconds, 6),
        "results": results,
        "success": True
    }


def get_default_benchmark_questions(project_name):

    return [
        f"What is the {project_name} security rule?",
        f"What checkpoints are completed for {project_name}?",
        f"Does {project_name} use cloud?",
        f"What tasks are pending for {project_name}?"
    ]


def save_benchmark_report(report):

    BENCHMARK_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    benchmark_size = report.get("memory_count")

    if benchmark_size is None:
        benchmark_size = report.get("target_tokens", "benchmark")

    report_path = build_benchmark_report_path(
        project_name=report["project"],
        memory_count=benchmark_size
    )

    report["report_file"] = str(report_path)

    with report_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, indent=2)

    return report


def benchmark_token_ingestion(project_name, target_tokens):

    benchmark_file = build_token_benchmark_file_path(
        project_name=project_name,
        target_tokens=target_tokens
    )
    generated_file = generate_token_benchmark_file(
        output_path=benchmark_file,
        project_name=project_name,
        target_tokens=target_tokens
    )
    ingestion_result = benchmark_ingestion(
        file_path=generated_file["file"],
        project_name=project_name
    )
    duplicate_ingestion_result = benchmark_ingestion(
        file_path=generated_file["file"],
        project_name=project_name
    )
    recall_result = benchmark_recall(
        project_name=project_name,
        questions=get_default_benchmark_questions(project_name)
    )
    recall_index_result = benchmark_recall_index(
        project_name=project_name,
        questions=get_default_benchmark_questions(project_name)
    )
    snapshot_result = save_snapshot(
        project_name=project_name,
        snapshot_name=f"TokenBenchmark_{target_tokens}"
    )
    snapshot_size_mb = get_file_size_mb(snapshot_result["snapshot_file"])
    db_size_mb = get_database_size_mb()

    report = {
        "success": (
            generated_file["success"]
            and ingestion_result["success"]
            and duplicate_ingestion_result["success"]
            and recall_result["success"]
            and recall_index_result["success"]
            and snapshot_result["success"]
        ),
        "project": project_name,
        "target_tokens": target_tokens,
        "estimated_tokens_generated": generated_file["estimated_tokens_generated"],
        "file_size_mb": generated_file["file_size_mb"],
        "ingest_duration": ingestion_result["duration_seconds"],
        "duplicate_duration": duplicate_ingestion_result["duration_seconds"],
        "recall_duration": recall_result["duration_seconds"],
        "recall_index_duration": recall_index_result["duration_seconds"],
        "snapshot_size_mb": snapshot_size_mb,
        "db_size_mb": db_size_mb,
        "generated_file": generated_file,
        "ingestion": ingestion_result,
        "duplicate_ingestion": duplicate_ingestion_result,
        "recall": recall_result,
        "recall_index": recall_index_result,
        "snapshot": snapshot_result,
        "created_at": datetime.now().isoformat()
    }

    return save_benchmark_report(report)


def run_benchmark_suite(project_name, memory_count):

    benchmark_file = build_benchmark_file_path(
        project_name=project_name,
        memory_count=memory_count
    )
    generated_file = generate_benchmark_file(
        output_path=benchmark_file,
        project_name=project_name,
        memory_count=memory_count
    )
    ingestion_result = benchmark_ingestion(
        file_path=generated_file["file"],
        project_name=project_name
    )
    duplicate_ingestion_result = benchmark_ingestion(
        file_path=generated_file["file"],
        project_name=project_name
    )
    recall_result = benchmark_recall(
        project_name=project_name,
        questions=get_default_benchmark_questions(project_name)
    )
    recall_index_result = benchmark_recall_index(
        project_name=project_name,
        questions=get_default_benchmark_questions(project_name)
    )
    snapshot_result = save_snapshot(
        project_name=project_name,
        snapshot_name=f"Benchmark_{memory_count}"
    )
    restore_result = restore_snapshot(snapshot_result["snapshot_file"])

    report = {
        "success": True,
        "project": project_name,
        "memory_count": memory_count,
        "generated_file": generated_file,
        "ingestion": ingestion_result,
        "duplicate_ingestion": duplicate_ingestion_result,
        "recall": recall_result,
        "recall_index": recall_index_result,
        "snapshot": snapshot_result,
        "restore": restore_result,
        "created_at": datetime.now().isoformat()
    }

    return save_benchmark_report(report)


def create_memory_link(source_memory_id, target_memory_id, link_type):

    if link_type not in ALLOWED_LINK_TYPES:
        return {
            "success": False,
            "link_id": None,
            "message": f"Invalid link_type: {link_type}"
        }

    source = read_memory(source_memory_id)
    target = read_memory(target_memory_id)

    if source is None:
        return {
            "success": False,
            "link_id": None,
            "message": "Source memory not found"
        }

    if target is None:
        return {
            "success": False,
            "link_id": None,
            "message": "Target memory not found"
        }

    created_at = datetime.now().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO memory_links (
        source_memory_id,
        target_memory_id,
        link_type,
        created_at
    )
    VALUES (?, ?, ?, ?)
    """, (
        source_memory_id,
        target_memory_id,
        link_type,
        created_at
    ))

    conn.commit()
    link_id = cursor.lastrowid
    conn.close()

    return {
        "success": True,
        "link_id": link_id,
        "message": "Memory link created successfully"
    }


def create_relationship(source_memory_id, target_memory_id, relationship_type):

    return create_memory_link(
        source_memory_id=source_memory_id,
        target_memory_id=target_memory_id,
        link_type=relationship_type
    )


def get_memory_links(memory_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        id,
        source_memory_id,
        target_memory_id,
        link_type,
        created_at
    FROM memory_links
    WHERE source_memory_id = ?
    ORDER BY id ASC
    """, (memory_id,))

    rows = cursor.fetchall()
    conn.close()

    links = []

    for row in rows:
        links.append({
            "id": row[0],
            "source_memory_id": row[1],
            "target_memory_id": row[2],
            "link_type": row[3],
            "created_at": row[4]
        })

    return links


def get_all_memory_links():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        id,
        source_memory_id,
        target_memory_id,
        link_type,
        created_at
    FROM memory_links
    ORDER BY id ASC
    """)

    rows = cursor.fetchall()
    conn.close()

    links = []

    for row in rows:
        links.append({
            "id": row[0],
            "source_memory_id": row[1],
            "target_memory_id": row[2],
            "link_type": row[3],
            "relationship_type": row[3],
            "created_at": row[4]
        })

    return links


def supersede_memory(old_memory_id, new_memory_id):

    old_memory = read_memory(old_memory_id)
    new_memory = read_memory(new_memory_id)

    if old_memory is None:
        return {
            "success": False,
            "message": "Old memory not found"
        }

    if new_memory is None:
        return {
            "success": False,
            "message": "New memory not found"
        }

    if old_memory_id == new_memory_id:
        return {
            "success": False,
            "message": "A memory cannot supersede itself"
        }

    status_result = update_memory_status(
        memory_id=old_memory_id,
        status="superseded"
    )

    if not status_result["success"]:
        return status_result

    relationship_result = create_relationship(
        source_memory_id=old_memory_id,
        target_memory_id=new_memory_id,
        relationship_type="superseded_by"
    )

    return {
        "success": relationship_result["success"],
        "old_memory_id": old_memory_id,
        "new_memory_id": new_memory_id,
        "relationship_id": relationship_result.get("link_id"),
        "message": "Memory superseded successfully"
    }


def archive_memory(memory_id):

    status_result = update_memory_status(
        memory_id=memory_id,
        status="archived"
    )

    if not status_result["success"]:
        return status_result

    return {
        "success": True,
        "memory_id": memory_id,
        "message": "Memory archived successfully"
    }


def get_memory_status_counts(project_name):

    memories = list_memories_by_project(
        project_name=project_name,
        include_history=True
    )
    counts = {
        "active": 0,
        "superseded": 0,
        "archived": 0
    }

    for memory in memories:
        status = memory.get("status")

        if status in counts:
            counts[status] += 1

    return counts


def get_incoming_relationships(memory_id, relationship_type=None):

    incoming_links = []

    for link in get_all_memory_links():
        if link["target_memory_id"] != memory_id:
            continue

        if relationship_type and link["relationship_type"] != relationship_type:
            continue

        incoming_links.append(link)

    return incoming_links


def get_first_outgoing_relationship(memory_id, relationship_type):

    for link in get_memory_links(memory_id):
        if link["link_type"] == relationship_type:
            return link

    return None


def get_memory_history_chain(memory_id):

    selected_memory = read_memory(memory_id)

    if selected_memory is None:
        return []

    current_memory = selected_memory
    visited_ids = set()

    while current_memory is not None:
        if current_memory["id"] in visited_ids:
            break

        visited_ids.add(current_memory["id"])
        incoming_links = get_incoming_relationships(
            memory_id=current_memory["id"],
            relationship_type="superseded_by"
        )

        if not incoming_links:
            break

        previous_memory = read_memory(incoming_links[0]["source_memory_id"])

        if previous_memory is None:
            break

        current_memory = previous_memory

    chain = []
    visited_ids = set()

    while current_memory is not None:
        if current_memory["id"] in visited_ids:
            break

        chain.append(current_memory)
        visited_ids.add(current_memory["id"])

        next_link = get_first_outgoing_relationship(
            memory_id=current_memory["id"],
            relationship_type="superseded_by"
        )

        if next_link is None:
            break

        current_memory = read_memory(next_link["target_memory_id"])

    return chain


def get_memory_history(memory_id):

    chain = get_memory_history_chain(memory_id)

    if not chain:
        return "Memory not found."

    lines = []
    lines.append("Memory History")
    lines.append("")

    for index, memory in enumerate(chain):
        if index == 0:
            label = "Original Memory"
        elif index == len(chain) - 1:
            label = "Current Memory"
        else:
            label = "Superseded By"

        lines.append(label)
        lines.append(
            f"#{memory['id']} "
            f"{memory['memory_type'].replace('_', ' ').title()}: "
            f"{memory['title']}"
        )
        lines.append(f"Status: {memory['status']}")

        if index < len(chain) - 1:
            lines.append("↓")
            lines.append("Superseded By")

    return "\n".join(lines)


def get_linked_memories(memory_id):

    links = get_memory_links(memory_id)
    results = []

    for link in links:
        target_memory = read_memory(link["target_memory_id"])

        results.append({
            "link_id": link["id"],
            "link_type": link["link_type"],
            "source_memory_id": link["source_memory_id"],
            "target_memory": target_memory
        })

    return results


def get_project_graph(project_name):

    memories = list_memories_by_project(project_name)
    memory_ids = set()
    memory_by_id = {}

    for memory in memories:
        memory_ids.add(memory["id"])
        memory_by_id[memory["id"]] = memory

    edges = []

    for link in get_all_memory_links():
        source_id = link["source_memory_id"]
        target_id = link["target_memory_id"]

        if source_id not in memory_ids:
            continue

        if target_id not in memory_ids:
            continue

        edges.append({
            "id": link["id"],
            "source_memory_id": source_id,
            "target_memory_id": target_id,
            "relationship_type": link["relationship_type"],
            "link_type": link["link_type"],
            "created_at": link["created_at"],
            "source_title": memory_by_id[source_id]["title"],
            "target_title": memory_by_id[target_id]["title"]
        })

    return {
        "project": project_name,
        "nodes": memories,
        "edges": edges
    }


def format_graph_memory_label(memory):

    return (
        f"{memory['memory_type'].replace('_', ' ').title()} "
        f"#{memory['id']}"
    )


def summarize_project_graph(project_name):

    graph = get_project_graph(project_name)
    lines = []

    lines.append("Project Graph Summary")
    lines.append("")
    lines.append(f"Project: {project_name}")
    lines.append(f"Nodes: {len(graph['nodes'])}")
    lines.append(f"Edges: {len(graph['edges'])}")
    lines.append("")
    lines.append("Key Relationships:")

    if not graph["edges"]:
        lines.append("No relationships found.")
        return "\n".join(lines)

    memory_by_id = {}

    for memory in graph["nodes"]:
        memory_by_id[memory["id"]] = memory

    for edge in graph["edges"][:10]:
        source_memory = memory_by_id[edge["source_memory_id"]]
        target_memory = memory_by_id[edge["target_memory_id"]]

        lines.append("")
        lines.append(format_graph_memory_label(source_memory))
        lines.append(f"-> {edge['relationship_type']}")
        lines.append(format_graph_memory_label(target_memory))

    return "\n".join(lines)


def get_memory_neighbors(memory_id):

    neighbors = []

    for link in get_all_memory_links():
        if link["source_memory_id"] == memory_id:
            neighbor_memory = read_memory(link["target_memory_id"])

            if neighbor_memory:
                neighbors.append({
                    "direction": "outgoing",
                    "relationship_type": link["relationship_type"],
                    "link_id": link["id"],
                    "memory": neighbor_memory
                })

        elif link["target_memory_id"] == memory_id:
            neighbor_memory = read_memory(link["source_memory_id"])

            if neighbor_memory:
                neighbors.append({
                    "direction": "incoming",
                    "relationship_type": link["relationship_type"],
                    "link_id": link["id"],
                    "memory": neighbor_memory
                })

    return neighbors


def get_memory_chain(start_memory_id, max_depth=3):

    chain = []
    current_memory_id = start_memory_id
    depth = 0

    while current_memory_id is not None and depth < max_depth:

        current_memory = read_memory(current_memory_id)

        if current_memory is None:
            break

        links = get_memory_links(current_memory_id)

        chain.append({
            "depth": depth,
            "memory": current_memory,
            "links": links
        })

        if not links:
            break

        next_link = links[0]
        current_memory_id = next_link["target_memory_id"]

        depth += 1

    return chain


def graph_recovery_trace(memory_id, max_depth=10):

    current_memory = read_memory(memory_id)

    if current_memory is None:
        return "Memory not found."

    lines = []
    visited_memory_ids = set()
    depth = 0

    while current_memory is not None and depth < max_depth:
        lines.append(format_graph_memory_label(current_memory))
        lines.append(current_memory["title"])

        visited_memory_ids.add(current_memory["id"])

        links = get_memory_links(current_memory["id"])
        next_link = None

        for link in links:
            if link["target_memory_id"] not in visited_memory_ids:
                next_link = link
                break

        if next_link is None:
            break

        lines.append("|")
        lines.append(f"v {next_link['link_type']}")

        current_memory = read_memory(next_link["target_memory_id"])
        depth += 1

    return "\n".join(lines)


def summarize_memory_chain(start_memory_id, max_depth=3):

    chain = get_memory_chain(start_memory_id, max_depth)
    summary_lines = []

    for item in chain:
        memory = item["memory"]
        links = item["links"]

        summary_lines.append(
            f"{item['depth'] + 1}. "
            f"{memory['memory_type'].replace('_', ' ').title()}: "
            f"{memory['title']}"
        )

        summary_lines.append(f"   Content: {memory['content']}")

        if links:
            first_link = links[0]
            summary_lines.append(
                f"   Link: This memory {first_link['link_type']} "
                f"memory #{first_link['target_memory_id']}."
            )
        else:
            summary_lines.append("   Link: No further linked memory.")

        summary_lines.append("")

    return "\n".join(summary_lines)


def search_memories(keyword):

    conn = get_connection()
    cursor = conn.cursor()

    search_term = f"%{keyword}%"

    cursor.execute("""
    SELECT
        id,
        memory_type,
        title,
        content,
        metadata,
        importance,
        confidence,
        source,
        status,
        content_hash,
        created_at,
        updated_at
    FROM memories
    WHERE status = 'active'
    AND (
        title LIKE ?
        OR content LIKE ?
    )
    ORDER BY importance DESC, id DESC
    """, (
        search_term,
        search_term
    ))

    rows = cursor.fetchall()
    conn.close()

    results = []

    for row in rows:
        results.append(row_to_memory(row))

    results.sort(
        key=lambda memory: (
            memory["trust_score"],
            memory["id"]
        ),
        reverse=True
    )

    return results


def search_memories_by_keyword_index(project_name, keywords, limit=20):

    normalized_keywords = []

    for keyword in keywords:
        normalized_keyword = normalize_keyword(keyword)

        if normalized_keyword and normalized_keyword not in normalized_keywords:
            normalized_keywords.append(normalized_keyword)

    if not normalized_keywords:
        return []

    placeholders = ", ".join("?" for _ in normalized_keywords)
    query = f"""
    SELECT
        memories.id,
        memories.memory_type,
        memories.title,
        memories.content,
        memories.metadata,
        memories.importance,
        memories.confidence,
        memories.source,
        memories.status,
        memories.content_hash,
        memories.created_at,
        memories.updated_at,
        COUNT(memory_keywords.keyword) AS match_count
    FROM memory_keywords
    JOIN memories
    ON memory_keywords.memory_id = memories.id
    WHERE memory_keywords.project = ?
    AND memory_keywords.keyword IN ({placeholders})
    AND memories.status = 'active'
    GROUP BY memories.id
    ORDER BY match_count DESC, memories.importance DESC, memories.id DESC
    LIMIT ?
    """

    params = [project_name]
    params.extend(normalized_keywords)
    params.append(limit)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    memories = []

    for row in rows:
        memories.append(row_to_memory(row[:12]))

    memories.sort(
        key=lambda memory: (
            memory["trust_score"],
            memory["id"]
        ),
        reverse=True
    )

    return memories


def search_all_projects(keyword):

    results = search_memories(keyword)
    grouped_results = {}

    for memory in results:
        metadata = memory.get("metadata") or {}
        project_name = metadata.get("project", "Unassigned")

        if project_name not in grouped_results:
            grouped_results[project_name] = []

        grouped_results[project_name].append(memory)

    return grouped_results


def find_security_keyword_memories():

    security_memories = []

    for memory in list_memories():
        combined_text = memory["title"] + " " + memory["content"]

        if text_contains_security_keyword(combined_text):
            security_memories.append(memory)

    return security_memories


def find_semantic_group_memories(question):

    matching_groups = get_matching_semantic_groups(question)
    semantic_memories = []

    if not matching_groups:
        return semantic_memories

    for memory in list_memories():
        combined_text = memory["title"] + " " + memory["content"]

        for group_name in matching_groups:
            keywords = SEMANTIC_KEYWORD_GROUPS[group_name]

            if text_contains_any_keyword(combined_text, keywords):
                semantic_memories.append(memory)
                break

    return semantic_memories


def get_known_memory_projects():

    project_names = []

    for memory in list_all_memories():
        metadata = memory.get("metadata") or {}
        project_name = metadata.get("project")

        if project_name and project_name not in project_names:
            project_names.append(project_name)

    return project_names


def infer_project_from_question(question, default_project_name):

    if default_project_name != DEFAULT_PROJECT_NAME:
        return default_project_name

    question_lower = question.lower()
    project_names = []

    for project in list_projects(include_archived=True):
        project_names.append(project["name"])

    for project_name in get_known_memory_projects():
        if project_name not in project_names:
            project_names.append(project_name)

    for project_name in project_names:
        if project_name.lower() in question_lower:
            return project_name

    return default_project_name


def summarize_search_results(keyword):

    results = search_memories(keyword)

    if not results:
        return f"No memories found for '{keyword}'."

    summary_lines = []
    summary_lines.append(f"Found {len(results)} memories for '{keyword}':")
    summary_lines.append("")

    for index, memory in enumerate(results, start=1):
        summary_lines.append(
            f"{index}. "
            f"{memory['memory_type'].replace('_', ' ').title()}: "
            f"{memory['title']}"
        )
        summary_lines.append(f"   Content: {memory['content']}")
        summary_lines.append(f"   Importance: {memory['importance']}")
        summary_lines.append(f"   Confidence: {memory['confidence']}")
        summary_lines.append(f"   Source: {memory['source']}")
        summary_lines.append(f"   Freshness: {memory['freshness']}")
        summary_lines.append(f"   Trust Score: {memory['trust_score']}")

        metadata = memory.get("metadata")

        if metadata and "project" in metadata:
            summary_lines.append(f"   Project: {metadata['project']}")

        summary_lines.append("")

    return "\n".join(summary_lines)


def list_memories_by_project(project_name, include_history=False):

    if include_history:
        all_memories = list_all_memories()
    else:
        all_memories = list_memories()

    project_memories = []

    for memory in all_memories:
        metadata = memory.get("metadata") or {}

        if metadata.get("project") == project_name:
            project_memories.append(memory)

    return project_memories


def build_snapshot_file_name(project_name, snapshot_name):

    clean_project_name = project_name.strip().replace(" ", "_")
    clean_snapshot_name = snapshot_name.strip().replace(" ", "_")

    return f"{clean_project_name}_{clean_snapshot_name}.json"


def get_snapshot_path(snapshot_file):

    snapshot_path = Path(snapshot_file)

    if snapshot_path.parent == Path("."):
        snapshot_path = SNAPSHOT_DIR / snapshot_path

    return snapshot_path


def save_snapshot(project_name, snapshot_name):

    memories = list_memories_by_project(project_name)
    memories.sort(key=lambda memory: memory["created_at"])

    snapshot_data = {
        "project": project_name,
        "snapshot_name": snapshot_name,
        "created_at": datetime.now().isoformat(),
        "memories": memories
    }

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    snapshot_file_name = build_snapshot_file_name(
        project_name=project_name,
        snapshot_name=snapshot_name
    )
    snapshot_path = SNAPSHOT_DIR / snapshot_file_name

    with snapshot_path.open("w", encoding="utf-8") as file:
        json.dump(snapshot_data, file, indent=2)

    return {
        "success": True,
        "snapshot_file": str(snapshot_path),
        "memory_count": len(memories)
    }


def restore_snapshot(snapshot_file):

    snapshot_path = get_snapshot_path(snapshot_file)

    if not snapshot_path.exists():
        return {
            "success": False,
            "message": "Snapshot file not found",
            "snapshot_file": str(snapshot_path)
        }

    with snapshot_path.open("r", encoding="utf-8") as file:
        snapshot_data = json.load(file)

    memories = snapshot_data.get("memories", [])
    restored_count = 0
    skipped_duplicates = 0

    for memory in memories:
        result = create_memory(
            memory_type=memory["memory_type"],
            title=memory["title"],
            content=memory["content"],
            metadata=memory.get("metadata"),
            importance=memory.get("importance", 5),
            confidence=memory.get("confidence", 100),
            source=memory.get("source", "user")
        )

        if result["success"]:
            restored_count += 1
        else:
            skipped_duplicates += 1

    return {
        "success": True,
        "snapshot_file": str(snapshot_path),
        "project": snapshot_data.get("project"),
        "snapshot_name": snapshot_data.get("snapshot_name"),
        "total_memories": len(memories),
        "restored": restored_count,
        "skipped_duplicates": skipped_duplicates
    }


def list_snapshots():

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    snapshot_files = []

    for snapshot_path in SNAPSHOT_DIR.glob("*.json"):
        snapshot_files.append(snapshot_path.name)

    snapshot_files.sort()

    return snapshot_files


def find_database_terms(text):

    text_lower = text.lower()
    terms = []

    if "sqlite" in text_lower:
        terms.append("SQLite")

    if "postgresql" in text_lower or "postgres" in text_lower:
        terms.append("PostgreSQL")

    if "mysql" in text_lower:
        terms.append("MySQL")

    if "mongodb" in text_lower or "mongo" in text_lower:
        terms.append("MongoDB")

    return terms


def detect_contradictions(project_name):

    memories = list_memories_by_project(project_name)
    database_terms = {}

    for memory in memories:
        combined_text = (
            memory["title"] + " " + memory["content"]
        )

        terms = find_database_terms(combined_text)

        for term in terms:
            if term not in database_terms:
                database_terms[term] = []

            database_terms[term].append(memory["id"])

    contradictions = []
    detected_terms = sorted(database_terms.keys())

    if len(detected_terms) > 1:
        memory_ids = []

        for term in detected_terms:
            memory_ids.extend(database_terms[term])

        contradictions.append({
            "topic": "database",
            "values": detected_terms,
            "memory_ids": sorted(set(memory_ids)),
            "message": (
                "Potential contradiction detected: project database mentions "
                + " and ".join(detected_terms)
                + "."
            )
        })

    has_contradictions = len(contradictions) > 0

    if has_contradictions:
        message = "Potential contradiction detected."
    else:
        message = "No potential contradictions found."

    return {
        "project": project_name,
        "has_contradictions": has_contradictions,
        "message": message,
        "contradictions": contradictions
    }


def get_project_timeline(project_name, include_tests=False):

    memories = list_memories_by_project(project_name)
    filtered_memories = []

    for memory in memories:
        metadata = memory.get("metadata") or {}
        memory_scope = metadata.get("memory_scope", "real")

        if include_tests:
            filtered_memories.append(memory)
        else:
            if memory_scope != "test":
                filtered_memories.append(memory)

    filtered_memories.sort(key=lambda memory: memory["created_at"])

    return filtered_memories


def summarize_project_timeline(project_name, include_tests=False):

    timeline = get_project_timeline(
        project_name=project_name,
        include_tests=include_tests
    )

    if not timeline:
        return f"No timeline found for project '{project_name}'."

    lines = []
    lines.append(f"Timeline for project '{project_name}':")
    lines.append("")

    for index, memory in enumerate(timeline, start=1):
        metadata = memory.get("metadata") or {}
        scope = metadata.get("memory_scope", "real")

        lines.append(f"{index}. {memory['created_at']}")
        lines.append(
            f"   {memory['memory_type'].replace('_', ' ').title()}: {memory['title']}"
        )
        lines.append(f"   {memory['content']}")
        lines.append(f"   Importance: {memory['importance']}")
        lines.append(f"   Confidence: {memory['confidence']}")
        lines.append(f"   Source: {memory['source']}")
        lines.append(f"   Freshness: {memory['freshness']}")
        lines.append(f"   Trust Score: {memory['trust_score']}")
        lines.append(f"   Scope: {scope}")
        lines.append("")

    return "\n".join(lines)


def mark_metadata_scope(metadata=None, scope="real"):

    if metadata is None:
        metadata = {}

    metadata["memory_scope"] = scope

    return metadata


def mark_metadata_topic(metadata=None, topic=None):

    if metadata is None:
        metadata = {}

    if topic:
        metadata["topic"] = topic

    return metadata


def list_memories_by_topic(topic):

    all_memories = list_memories()
    topic_memories = []

    for memory in all_memories:
        metadata = memory.get("metadata") or {}

        if metadata.get("topic") == topic:
            topic_memories.append(memory)

    return topic_memories


def deduplicate_memories(memories):

    seen = set()
    unique_memories = []

    for memory in memories:
        key = (
            memory["memory_type"],
            memory["title"].strip().lower(),
            memory["content"].strip().lower()
        )

        if key not in seen:
            seen.add(key)
            unique_memories.append(memory)

    return unique_memories


def recall_memory(keyword):

    memories = search_memories(keyword)
    memories = deduplicate_memories(memories)

    if not memories:
        return f"No memory found for '{keyword}'."

    lines = []
    lines.append(f"Memory Recall for '{keyword}'")
    lines.append("")

    for memory in memories:
        lines.append(
            f"- {memory['title']} "
            f"[importance: {memory['importance']}, "
            f"confidence: {memory['confidence']}, "
            f"source: {memory['source']}, "
            f"freshness: {memory['freshness']}, "
            f"trust: {memory['trust_score']}]"
        )
        lines.append(f"  {memory['content']}")

    return "\n".join(lines)


def recall_topic(topic):

    memories = list_memories_by_topic(topic)
    memories = deduplicate_memories(memories)

    if not memories:
        return f"No memories found for topic '{topic}'."

    lines = []
    lines.append(f"Topic Recall: {topic}")
    lines.append("")

    for memory in memories:
        lines.append(
            f"- {memory['memory_type'].replace('_', ' ').title()}: "
            f"{memory['title']} "
            f"[importance: {memory['importance']}, "
            f"confidence: {memory['confidence']}, "
            f"source: {memory['source']}, "
            f"freshness: {memory['freshness']}, "
            f"trust: {memory['trust_score']}]"
        )
        lines.append(f"  {memory['content']}")

    return "\n".join(lines)


def consolidate_memory(keyword, project_name=None):

    memories = search_memories(keyword)

    if project_name:
        filtered = []

        for memory in memories:
            metadata = memory.get("metadata") or {}

            if metadata.get("project") == project_name:
                filtered.append(memory)

        memories = filtered

    memories = deduplicate_memories(memories)

    if not memories:
        return {
            "success": False,
            "keyword": keyword,
            "message": "No memories found to consolidate",
            "summary": None
        }

    contents = []

    for memory in memories:
        contents.append(memory["content"])

    unique_contents = []

    for content in contents:
        clean_content = content.strip()

        if clean_content not in unique_contents:
            unique_contents.append(clean_content)

    compressed_facts = compress_similar_facts(unique_contents)

    summary_lines = []
    summary_lines.append(f"Consolidated Memory for '{keyword}'")

    if project_name:
        summary_lines.append(f"Project: {project_name}")

    summary_lines.append("")
    summary_lines.append("Known facts:")

    for content in compressed_facts:
        summary_lines.append(f"- {content}")

    return {
        "success": True,
        "keyword": keyword,
        "project": project_name,
        "source_memory_count": len(memories),
        "summary": "\n".join(summary_lines)
    }


def compress_similar_facts(facts):

    compressed = []
    sandbox_facts = []
    other_facts = []

    for fact in facts:
        fact_lower = fact.lower()

        if "sandbox" in fact_lower and (
            "database" in fact_lower
            or "sqlite" in fact_lower
            or "usmos.db" in fact_lower
        ):
            sandbox_facts.append(fact)
        else:
            other_facts.append(fact)

    if sandbox_facts:
        compressed.append(
            "USMOS database must remain inside the local sandbox, specifically sandbox/data/usmos.db."
        )

    for fact in other_facts:
        if fact not in compressed:
            compressed.append(fact)

    return compressed


def detect_question_topic(question):

    question_lower = question.lower()
    matching_groups = get_matching_semantic_groups(question_lower)

    if (
        text_contains_security_keyword(question_lower)
        or "cloud" in matching_groups
        or "security" in matching_groups
    ):
        return "security"

    if "sqlite" in question_lower or "database" in question_lower or "storage" in question_lower:
        return "storage"

    if (
        "phase" in question_lower
        or "status" in question_lower
        or "progress" in question_lower
        or "checkpoint" in matching_groups
    ):
        return "project_status"

    return None


def detect_question_memory_type(question):

    normalized_words = extract_keyword_words(question)

    if "task" in normalized_words:
        return "task"

    if "checkpoint" in normalized_words:
        return "checkpoint"

    if "decision" in normalized_words:
        return "decision"

    if "event" in normalized_words:
        return "event"

    if "fact" in normalized_words:
        return "project_note"

    return None


def filter_memories_by_memory_type(memories, memory_type):

    if memory_type is None:
        return memories

    filtered_memories = []

    for memory in memories:
        if memory["memory_type"] == memory_type:
            filtered_memories.append(memory)

    return filtered_memories


def auto_recall(question, project_name="USMOS", max_results=5):
    project_name = infer_project_from_question(question, project_name)
    analysis = analyze_question(question)
    topic = analysis["topic"]
    requested_memory_type = analysis.get("memory_type")

    if topic is None:
        topic = detect_question_topic(question)

    keyword_candidates = extract_query_keywords(question, topic)

    if requested_memory_type:
        type_keyword = normalize_keyword(requested_memory_type)

        if type_keyword and type_keyword not in keyword_candidates:
            keyword_candidates.append(type_keyword)

        if requested_memory_type == "project_note" and "fact" not in keyword_candidates:
            keyword_candidates.append("fact")

    memories = search_memories_by_keyword_index(
        project_name=project_name,
        keywords=keyword_candidates,
        limit=max_results * 3
    )

    if not memories:
        if topic:
            memories = list_memories_by_topic(topic)

        if topic == "security":
            memories.extend(find_security_keyword_memories())

        memories.extend(find_semantic_group_memories(question))

    if not memories:
        words = question.lower().split()

        for word in words:
            if len(word) > 3:
                results = search_memories(word)
                memories.extend(results)

    project_filtered = []

    for memory in memories:
        metadata = memory.get("metadata") or {}

        if metadata.get("project") == project_name:
            project_filtered.append(memory)

    memories = deduplicate_memories(project_filtered)
    memories = filter_memories_by_memory_type(memories, requested_memory_type)

    if not memories and requested_memory_type:
        project_memories = list_memories_by_project(project_name)
        memories = filter_memories_by_memory_type(
            memories=project_memories,
            memory_type=requested_memory_type
        )

    memories.sort(
        key=lambda memory: (
            memory["trust_score"],
            memory["id"]
        ),
        reverse=True
    )

    memories = memories[:max_results]

    if not memories:
        return {
            "success": False,
            "question": question,
            "project": project_name,
            "topic": topic,
            "memories": [],
            "summary": "No relevant memories found."
        }

    lines = []

    lines.append(f"Auto Recall for Question: {question}")
    lines.append("")

    if topic:
        lines.append(f"Detected Topic: {topic}")
    else:
        lines.append("Detected Topic: unknown")

    if requested_memory_type:
        lines.append(f"Detected Memory Type: {requested_memory_type}")

    lines.append("")
    lines.append("Relevant Memories:")

    for memory in memories:
        lines.append(
            f"- {memory['title']} "
            f"[type: {memory['memory_type']}, "
            f"importance: {memory['importance']}, "
            f"confidence: {memory['confidence']}, "
            f"source: {memory['source']}, "
            f"freshness: {memory['freshness']}, "
            f"trust: {memory['trust_score']}]"
        )
        lines.append(f"  {memory['content']}")

    return {
        "analysis": analysis,
        "success": True,
        "question": question,
        "project": project_name,
        "topic": topic,
        "memory_type": requested_memory_type,
        "memories": memories,
        "summary": "\n".join(lines)
    }


def analyze_question(question):

    question_lower = question.lower()
    matching_groups = get_matching_semantic_groups(question_lower)

    result = {
        "question": question,
        "topic": None,
        "intent": "unknown",
        "memory_type": detect_question_memory_type(question),
        "keywords": []
    }

    # Topic Detection

    if (
        text_contains_security_keyword(question_lower)
        or "cloud" in matching_groups
        or "security" in matching_groups
    ):
        result["topic"] = "security"

    elif any(word in question_lower for word in [
        "sqlite",
        "database",
        "storage"
    ]):
        result["topic"] = "storage"

    elif (
        any(word in question_lower for word in [
            "status",
            "progress",
            "phase"
        ])
        or "checkpoint" in matching_groups
    ):
        result["topic"] = "project_status"

    # Intent Detection

    if question_lower.startswith("why"):
        result["intent"] = "reason"

    elif question_lower.startswith("what"):
        result["intent"] = "information"

    elif question_lower.startswith("how"):
        result["intent"] = "process"

    elif question_lower.startswith("where"):
        result["intent"] = "location"

    # Keyword Extraction

    words = question_lower.split()

    for word in words:

        clean_word = word.strip("?,.!")

        if len(clean_word) > 3:
            result["keywords"].append(clean_word)

    return result


def build_context(question, project_name="USMOS"):

    recall_result = auto_recall(
        question=question,
        project_name=project_name,
        max_results=10
    )

    if not recall_result["success"]:
        return {
            "success": False,
            "context": None
        }

    memories = recall_result["memories"]

    lines = []

    lines.append("USMOS Context Package")
    lines.append("")
    lines.append(f"Question: {question}")
    lines.append("")

    for memory in memories:

        lines.append(
            f"[{memory['memory_type'].upper()}]"
        )

        lines.append(
            f"Title: {memory['title']}"
        )

        lines.append(
            f"Content: {memory['content']}"
        )

        lines.append(
            f"Importance: {memory['importance']}"
        )

        lines.append(
            f"Confidence: {memory['confidence']}"
        )

        lines.append(
            f"Source: {memory['source']}"
        )

        lines.append(
            f"Freshness: {memory['freshness']}"
        )

        lines.append(
            f"Trust Score: {memory['trust_score']}"
        )

        lines.append("")

    return {
        "success": True,
        "question": question,
        "memory_count": len(memories),
        "context": "\n".join(lines)
    }


def create_checkpoint(
    title,
    content,
    metadata=None,
    importance=9,
    confidence=100,
    source="checkpoint"
):

    return create_memory(
        memory_type="checkpoint",
        title=title,
        content=content,
        metadata=metadata,
        importance=importance,
        confidence=confidence,
        source=source
    )


def clean_answer_sentence(text):

    sentence = " ".join(text.split())

    if not sentence:
        return ""

    if sentence[-1] not in ".!?":
        sentence = sentence + "."

    return sentence


def memory_matches_project(memory, project_name):

    metadata = memory.get("metadata") or {}
    return metadata.get("project") == project_name


def get_related_support_memories(question, project_name, existing_memories):

    question_lower = question.lower()
    existing_ids = set()

    for memory in existing_memories:
        existing_ids.add(memory["id"])

    support_memories = []

    asks_about_storage = (
        "sqlite" in question_lower
        or "database" in question_lower
        or "storage" in question_lower
    )

    if asks_about_storage:
        security_memories = list_memories_by_topic("security")

        for memory in security_memories:
            if memory["id"] in existing_ids:
                continue

            if memory_matches_project(memory, project_name):
                support_memories.append(memory)

    return support_memories


def memory_text_contains(memory, words):

    combined_text = (
        memory["title"] + " " + memory["content"]
    ).lower()

    for word in words:
        if word in combined_text:
            return True

    return False


def summarize_memory_fact(memory):

    memory_type = memory["memory_type"]
    content = clean_answer_sentence(memory["content"])

    if memory_type == "decision":
        return f"A stored decision says: {content}"

    if memory_type == "task":
        return f"A stored task shows this work item: {content}"

    if memory_type == "event":
        return f"A stored event confirms: {content}"

    if memory_type == "checkpoint":
        return f"A stored checkpoint records: {content}"

    return content


def build_storage_answer(question, memories):

    sentences = []
    has_sqlite = False

    for memory in memories:
        if memory_text_contains(memory, ["sqlite"]):
            has_sqlite = True

    if "sqlite" in question.lower() or has_sqlite:
        sentences.append(
            "USMOS is using SQLite because the stored memories connect it to Phase 1 local storage work."
        )
    else:
        sentences.append(
            "USMOS is using local storage because the stored memories connect it to the local-first sandbox design."
        )

    for memory in memories:
        combined_text = (
            memory["title"] + " " + memory["content"]
        ).lower()

        if memory["memory_type"] == "task" and "sqlite" in combined_text:
            sentences.append(
                "The memories show that SQLite storage was implemented inside the local sandbox folder."
            )

        elif memory["memory_type"] == "event" and (
            "verified" in combined_text
            or "works" in combined_text
        ):
            sentences.append(
                "They also show that Phase 1 storage was verified successfully."
            )

        elif memory["memory_type"] == "decision" and "sandbox/data/usmos.db" in combined_text:
            sentences.append(
                "This supports the sandbox security rule that the database stays at sandbox/data/usmos.db."
            )

    return remove_duplicate_sentences(sentences)


def build_storage_location_answer(memories):

    sentences = [
        "USMOS stores its database inside the local sandbox."
    ]

    for memory in memories:
        combined_text = (
            memory["title"] + " " + memory["content"]
        ).lower()

        if "sandbox/data/usmos.db" in combined_text:
            sentences.append(
                "The stored security decision says the database path is sandbox/data/usmos.db."
            )

        elif "local sandbox folder" in combined_text:
            sentences.append(
                "The storage memory also says SQLite storage was implemented inside the local sandbox folder."
            )

    return remove_duplicate_sentences(sentences)


def build_security_answer(memories, project_name):

    sentences = [
        f"{project_name} security is centered on keeping memory local and sandbox-controlled."
    ]

    for memory in memories:
        sentences.append(summarize_memory_fact(memory))

    return remove_duplicate_sentences(sentences)


def build_cloud_answer(memories):

    sentences = []
    has_avoid_rule = False

    for memory in memories:
        if memory_text_contains(memory, [
            "avoid cloud",
            "no cloud",
            "must avoid",
            "external service",
            "network"
        ]):
            has_avoid_rule = True

    if has_avoid_rule:
        sentences.append("No.")
    else:
        sentences.append("Based on stored memories, here is what USMOS knows about cloud use.")

    for memory in memories:
        sentences.append(summarize_memory_fact(memory))

    return remove_duplicate_sentences(sentences)


def build_status_answer(memories):

    sentences = [
        "USMOS status is based on the latest stored project memories."
    ]

    for memory in memories:
        sentences.append(summarize_memory_fact(memory))

    return remove_duplicate_sentences(sentences)


def build_generic_answer(memories):

    sentences = [
        "Based on stored memories, here is what USMOS currently knows."
    ]

    for memory in memories:
        sentences.append(summarize_memory_fact(memory))

    return remove_duplicate_sentences(sentences)


def remove_duplicate_sentences(sentences):

    clean_sentences = []
    seen = set()

    for sentence in sentences:
        clean_sentence = clean_answer_sentence(sentence)

        if not clean_sentence:
            continue

        key = clean_sentence.lower()

        if key not in seen:
            seen.add(key)
            clean_sentences.append(clean_sentence)

    return clean_sentences


def answer_from_memory(question, project_name="USMOS"):

    recall_result = auto_recall(
        question=question,
        project_name=project_name,
        max_results=5
    )

    if not recall_result["success"]:
        return "No relevant memory found."

    memories = recall_result["memories"]
    project_name = recall_result.get("project", project_name)
    support_memories = get_related_support_memories(
        question=question,
        project_name=project_name,
        existing_memories=memories
    )

    memories = deduplicate_memories(memories + support_memories)
    analysis = recall_result.get("analysis") or analyze_question(question)
    topic = recall_result.get("topic") or analysis.get("topic")
    requested_memory_type = analysis.get("memory_type")
    memories = filter_memories_by_memory_type(memories, requested_memory_type)
    question_groups = get_matching_semantic_groups(question)

    if "cloud" in question_groups:
        answer_sentences = build_cloud_answer(memories)
    elif topic == "storage" and analysis.get("intent") == "location":
        answer_sentences = build_storage_location_answer(memories)
    elif topic == "storage":
        answer_sentences = build_storage_answer(question, memories)
    elif topic == "security":
        answer_sentences = build_security_answer(memories, project_name)
    elif topic == "project_status":
        answer_sentences = build_status_answer(memories)
    else:
        answer_sentences = build_generic_answer(memories)

    return " ".join(answer_sentences)


def get_memories_for_answer(question, project_name="USMOS", max_results=5):

    recall_result = auto_recall(
        question=question,
        project_name=project_name,
        max_results=max_results
    )

    if not recall_result["success"]:
        return {
            "success": False,
            "question": question,
            "project": project_name,
            "analysis": recall_result.get("analysis") or analyze_question(question),
            "topic": recall_result.get("topic"),
            "memories": []
        }

    memories = recall_result["memories"]
    project_name = recall_result.get("project", project_name)
    support_memories = get_related_support_memories(
        question=question,
        project_name=project_name,
        existing_memories=memories
    )

    memories = deduplicate_memories(memories + support_memories)
    analysis = recall_result.get("analysis") or analyze_question(question)
    requested_memory_type = analysis.get("memory_type")
    memories = filter_memories_by_memory_type(memories, requested_memory_type)
    memories.sort(
        key=lambda memory: (
            memory["trust_score"],
            memory["id"]
        ),
        reverse=True
    )

    return {
        "success": True,
        "question": question,
        "project": project_name,
        "analysis": analysis,
        "topic": recall_result.get("topic") or analysis.get("topic"),
        "memories": memories
    }


def explain_trust_score(memory):

    return (
        f"trust = importance({memory['importance']}) * 5 "
        f"+ confidence({memory['confidence']}) "
        f"= {memory['trust_score']}"
    )


def get_keyword_matches(memory, keywords):

    combined_text = (
        memory["title"] + " " + memory["content"]
    ).lower()

    matches = []

    for keyword in keywords:
        if keyword in combined_text and keyword not in matches:
            matches.append(keyword)

    return matches


def explain_single_memory_selection(memory, analysis):

    metadata = memory.get("metadata") or {}
    reasons = []
    topic = analysis.get("topic")
    keywords = analysis.get("keywords", [])

    if topic and metadata.get("topic") == topic:
        reasons.append(f"topic match: {topic}")

    if topic == "storage" and metadata.get("topic") == "security":
        reasons.append("supporting security rule for storage question")

    keyword_matches = get_keyword_matches(memory, keywords)

    if keyword_matches:
        reasons.append("keyword match: " + ", ".join(keyword_matches))

    reasons.append(f"trust score: {memory['trust_score']}")
    reasons.append(f"source: {memory['source']}")
    reasons.append(f"freshness: {memory['freshness']}")

    return "; ".join(reasons)


def build_memory_evidence_trace(memories, analysis):

    evidence_trace = []

    for memory in memories:
        evidence_trace.append({
            "memory_id": memory["id"],
            "memory_type": memory["memory_type"],
            "title": memory["title"],
            "content": memory["content"],
            "importance": memory["importance"],
            "confidence": memory["confidence"],
            "source": memory["source"],
            "freshness": memory["freshness"],
            "trust_score": memory["trust_score"],
            "trust_explanation": explain_trust_score(memory),
            "selection_reason": explain_single_memory_selection(
                memory=memory,
                analysis=analysis
            )
        })

    return evidence_trace


def get_relevant_contradiction_warning(question, project_name, memories, topic):

    contradiction_result = detect_contradictions(project_name)

    if not contradiction_result["has_contradictions"]:
        return None

    selected_memory_ids = set()

    for memory in memories:
        selected_memory_ids.add(memory["id"])

    question_lower = question.lower()
    asks_about_database = (
        topic == "storage"
        or "database" in question_lower
        or "sqlite" in question_lower
        or "storage" in question_lower
    )

    for contradiction in contradiction_result["contradictions"]:
        contradiction_memory_ids = set(contradiction["memory_ids"])
        memory_overlap = selected_memory_ids.intersection(contradiction_memory_ids)

        if asks_about_database or memory_overlap:
            return {
                "topic": contradiction["topic"],
                "message": contradiction["message"],
                "memory_ids": contradiction["memory_ids"],
                "values": contradiction["values"]
            }

    return None


def explain_memory_selection(question, project_name="USMOS", max_results=5):

    answer_memory_result = get_memories_for_answer(
        question=question,
        project_name=project_name,
        max_results=max_results
    )

    if not answer_memory_result["success"]:
        return {
            "success": False,
            "question": question,
            "project": project_name,
            "answer": "No relevant memory found.",
            "selected_memory_ids": [],
            "evidence_trace": [],
            "contradiction_warning": None,
            "message": "No relevant memory found."
        }

    memories = answer_memory_result["memories"]
    analysis = answer_memory_result["analysis"]
    topic = answer_memory_result["topic"]
    selected_memory_ids = []

    for memory in memories:
        selected_memory_ids.append(memory["id"])

    contradiction_warning = get_relevant_contradiction_warning(
        question=question,
        project_name=project_name,
        memories=memories,
        topic=topic
    )

    return {
        "success": True,
        "question": question,
        "project": project_name,
        "topic": topic,
        "intent": analysis.get("intent"),
        "keywords": analysis.get("keywords", []),
        "selected_memory_ids": selected_memory_ids,
        "evidence_trace": build_memory_evidence_trace(
            memories=memories,
            analysis=analysis
        ),
        "contradiction_warning": contradiction_warning,
        "message": "Memory selection explained."
    }


def answer_with_reasoning(question, project_name="USMOS", max_results=5):

    explanation = explain_memory_selection(
        question=question,
        project_name=project_name,
        max_results=max_results
    )

    if not explanation["success"]:
        return "No relevant memory found."

    answer = answer_from_memory(
        question=question,
        project_name=project_name
    )

    memory_ids = []

    for memory_id in explanation["selected_memory_ids"]:
        memory_ids.append(f"#{memory_id}")

    lines = []
    lines.append("Answer:")
    lines.append(answer)
    lines.append("")
    lines.append("Memory IDs:")
    lines.append(", ".join(memory_ids))

    contradiction_warning = explanation["contradiction_warning"]

    if contradiction_warning:
        lines.append("")
        lines.append("Contradiction Warning:")
        lines.append(contradiction_warning["message"])
        lines.append(
            "Related memory IDs: "
            + ", ".join(
                f"#{memory_id}"
                for memory_id in contradiction_warning["memory_ids"]
            )
        )

    lines.append("")
    lines.append("Evidence Trace:")

    for evidence in explanation["evidence_trace"]:
        lines.append(
            f"- Memory #{evidence['memory_id']} "
            f"({evidence['memory_type']}): {evidence['title']}"
        )
        lines.append(f"  Evidence: {evidence['content']}")
        lines.append(f"  Selected because: {evidence['selection_reason']}")
        lines.append(f"  Trust: {evidence['trust_explanation']}")

    return "\n".join(lines)


def get_latest_checkpoint(project_name):

    memories = list_memories_by_project(project_name)
    checkpoints = []

    for memory in memories:
        if memory["memory_type"] == "checkpoint":
            checkpoints.append(memory)

    if not checkpoints:
        return None

    checkpoints.sort(
        key=lambda memory: (
            memory["created_at"],
            memory["id"]
        ),
        reverse=True
    )

    return checkpoints[0]


def detect_phase_key_from_text(text):

    text_lower = text.lower()

    for phase_key in PHASE_ORDER:
        if phase_key.lower() in text_lower:
            return phase_key

    return None


def detect_phase_key_from_memory(memory):

    metadata = memory.get("metadata") or {}
    text_parts = [
        metadata.get("phase", ""),
        metadata.get("completed_phase", ""),
        memory["title"],
        memory["content"]
    ]

    combined_text = " ".join(text_parts)

    return detect_phase_key_from_text(combined_text)


def get_completed_phase_label(memory):

    metadata = memory.get("metadata") or {}
    completed_phase = metadata.get("completed_phase")

    if completed_phase:
        return completed_phase

    phase_key = detect_phase_key_from_memory(memory)

    if phase_key:
        return PHASE_LABELS.get(phase_key, phase_key)

    return None


def sort_phase_labels(phase_labels):

    def phase_sort_key(phase_label):
        phase_key = detect_phase_key_from_text(phase_label)

        if phase_key in PHASE_ORDER:
            return PHASE_ORDER.index(phase_key)

        return len(PHASE_ORDER)

    phase_labels.sort(key=phase_sort_key)

    return phase_labels


def get_completed_phases_from_checkpoints(checkpoints):

    completed_phases = []
    seen = set()

    for checkpoint in checkpoints:
        phase_label = get_completed_phase_label(checkpoint)

        if not phase_label:
            continue

        if phase_label not in seen:
            seen.add(phase_label)
            completed_phases.append(phase_label)

    return sort_phase_labels(completed_phases)


def get_current_phase_from_completed(completed_phases):

    latest_completed_index = -1

    for phase_label in completed_phases:
        phase_key = detect_phase_key_from_text(phase_label)

        if phase_key in PHASE_ORDER:
            phase_index = PHASE_ORDER.index(phase_key)

            if phase_index > latest_completed_index:
                latest_completed_index = phase_index

    if latest_completed_index == -1:
        return "Unknown"

    next_phase_index = latest_completed_index + 1

    if next_phase_index < len(PHASE_ORDER):
        next_phase_key = PHASE_ORDER[next_phase_index]
        return PHASE_LABELS[next_phase_key]

    latest_phase_key = PHASE_ORDER[latest_completed_index]
    return PHASE_LABELS[latest_phase_key]


def get_project_phase_summary(project_name):

    memories = list_memories_by_project(project_name)
    all_project_memories = list_memories_by_project(
        project_name=project_name,
        include_history=True
    )
    checkpoints = []
    active_decisions = []
    historical_decisions = []
    superseded_memories = []

    for memory in memories:
        if memory["memory_type"] == "checkpoint":
            checkpoints.append(memory)

        if memory["memory_type"] == "decision":
            active_decisions.append(memory)

    for memory in all_project_memories:
        if memory["status"] == "superseded":
            superseded_memories.append(memory)

        if memory["memory_type"] == "decision" and memory["status"] != "active":
            historical_decisions.append(memory)

    latest_checkpoint = get_latest_checkpoint(project_name)
    completed_phases = get_completed_phases_from_checkpoints(checkpoints)
    current_phase = get_current_phase_from_completed(completed_phases)

    highest_trust_memories = list(memories)
    highest_trust_memories.sort(
        key=lambda memory: (
            memory["trust_score"],
            memory["id"]
        ),
        reverse=True
    )
    highest_trust_memories = highest_trust_memories[:5]

    return {
        "project": project_name,
        "latest_checkpoint": latest_checkpoint,
        "completed_phases": completed_phases,
        "current_phase": current_phase,
        "memory_count": len(memories),
        "highest_trust_memories": highest_trust_memories,
        "active_decisions": active_decisions,
        "historical_decisions": historical_decisions,
        "superseded_memories": superseded_memories,
        "status_counts": get_memory_status_counts(project_name)
    }


def get_recommended_next_step(current_phase):

    if current_phase == PHASE_LABELS["Phase 6"]:
        return "Build a local CLI or project recovery command."

    if current_phase == PHASE_LABELS["Phase 11"]:
        return "Use memory evolution to supersede outdated decisions and archive inactive work."

    if current_phase == "Unknown":
        return "Create a clear project checkpoint before planning the next step."

    return "Continue the current phase and create a checkpoint when it passes."


def recover_project_state(project_name):

    summary = get_project_phase_summary(project_name)
    latest_checkpoint = summary["latest_checkpoint"]

    lines = []
    lines.append(f"{project_name} Project State Recovery")
    lines.append("")
    lines.append("Latest checkpoint:")

    if latest_checkpoint:
        lines.append(latest_checkpoint["title"])
        lines.append(f"Memory ID: #{latest_checkpoint['id']}")
        lines.append(f"Trust Score: {latest_checkpoint['trust_score']}")
    else:
        lines.append("No checkpoint found.")

    lines.append("")
    lines.append("Completed:")

    if summary["completed_phases"]:
        for phase in summary["completed_phases"]:
            lines.append(f"- {phase}")
    else:
        lines.append("- No completed phases found.")

    lines.append("")
    lines.append("Current focus:")
    lines.append(summary["current_phase"])
    lines.append("")
    lines.append("Recommended next step:")
    lines.append(get_recommended_next_step(summary["current_phase"]))
    lines.append("")
    lines.append(f"Memory count: {summary['memory_count']}")
    lines.append("")
    lines.append("Active decisions:")

    if summary["active_decisions"]:
        for memory in summary["active_decisions"][:5]:
            lines.append(f"- #{memory['id']} {memory['title']}")
    else:
        lines.append("- No active decisions found.")

    lines.append("")
    lines.append("Historical decisions:")

    if summary["historical_decisions"]:
        for memory in summary["historical_decisions"][:5]:
            lines.append(
                f"- #{memory['id']} {memory['title']} "
                f"({memory['status']})"
            )
    else:
        lines.append("- No historical decisions found.")

    lines.append("")
    lines.append("Superseded memories:")

    if summary["superseded_memories"]:
        for memory in summary["superseded_memories"][:5]:
            lines.append(f"- #{memory['id']} {memory['title']}")
    else:
        lines.append("- No superseded memories found.")

    if summary["highest_trust_memories"]:
        lines.append("")
        lines.append("Highest trust memories:")

        for memory in summary["highest_trust_memories"][:3]:
            lines.append(
                f"- #{memory['id']} {memory['title']} "
                f"(trust {memory['trust_score']})"
            )

    return "\n".join(lines)


def is_project_state_question(question):

    question_lower = question.lower()
    state_phrases = [
        "current project state",
        "project state",
        "current status",
        "latest checkpoint",
        "what phase",
        "phase are we",
        "what is completed",
        "completed",
        "done next",
        "should be done next"
    ]

    for phrase in state_phrases:
        if phrase in question_lower:
            return True

    return False


def answer_project_state_question(question, project_name="USMOS"):

    if is_project_state_question(question):
        return recover_project_state(project_name)

    return answer_with_reasoning(
        question=question,
        project_name=project_name
    )
