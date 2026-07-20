from datetime import datetime
import json

from src.conversation.conversation_analyzer import analyze_conversation_for_memory
from src.conversation.conversation_memory import save_approved_memory
from src.storage.database import get_connection


PENDING_STATUS = "pending"
APPROVED_STATUS = "approved"
REJECTED_STATUS = "rejected"
VALID_APPROVAL_STATUSES = {
    PENDING_STATUS,
    APPROVED_STATUS,
    REJECTED_STATUS
}


def current_timestamp():

    return datetime.now().isoformat()


def generate_conversation_id():

    return datetime.now().strftime("conv_%Y%m%d_%H%M%S_%f")


def row_to_pending_item(row):

    proposed_supersession = []

    if row[8]:
        proposed_supersession = json.loads(row[8])

    return {
        "pending_id": row[0],
        "conversation_id": row[1],
        "project_name": row[2],
        "memory_type": row[3],
        "title": row[4],
        "content": row[5],
        "detected_reason": row[6],
        "timestamp": row[7],
        "proposed_supersession": proposed_supersession,
        "approval_status": row[9],
        "approved_memory_id": row[10],
        "updated_at": row[11]
    }


def get_pending_item(pending_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        pending_id,
        conversation_id,
        project_name,
        memory_type,
        title,
        content,
        detected_reason,
        timestamp,
        proposed_supersession,
        approval_status,
        approved_memory_id,
        updated_at
    FROM pending_memory_queue
    WHERE pending_id = ?
    """, (pending_id,))

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return row_to_pending_item(row)


def find_duplicate_pending_item(candidate, project_name):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        pending_id,
        conversation_id,
        project_name,
        memory_type,
        title,
        content,
        detected_reason,
        timestamp,
        proposed_supersession,
        approval_status,
        approved_memory_id,
        updated_at
    FROM pending_memory_queue
    WHERE project_name = ?
    AND memory_type = ?
    AND title = ?
    AND content = ?
    """, (
        project_name,
        candidate["memory_type"],
        candidate["title"],
        candidate["content"]
    ))

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    return row_to_pending_item(row)


def create_conversation_history(
    conversation_id,
    original_sentence,
    source="conversation"
):

    timestamp = current_timestamp()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT OR IGNORE INTO conversation_history (
        conversation_id,
        original_sentence,
        timestamp,
        source,
        approved_memory_ids
    )
    VALUES (?, ?, ?, ?, ?)
    """, (
        conversation_id,
        original_sentence,
        timestamp,
        source,
        json.dumps([])
    ))

    conn.commit()
    conn.close()

    return {
        "conversation_id": conversation_id,
        "timestamp": timestamp
    }


def get_conversation_history(conversation_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        id,
        conversation_id,
        original_sentence,
        timestamp,
        source,
        approved_memory_ids
    FROM conversation_history
    WHERE conversation_id = ?
    """, (conversation_id,))

    row = cursor.fetchone()
    conn.close()

    if row is None:
        return None

    approved_memory_ids = []

    if row[5]:
        approved_memory_ids = json.loads(row[5])

    return {
        "id": row[0],
        "conversation_id": row[1],
        "original_sentence": row[2],
        "timestamp": row[3],
        "source": row[4],
        "approved_memory_ids": approved_memory_ids
    }


def add_approved_memory_to_conversation(conversation_id, memory_id):

    history = get_conversation_history(conversation_id)

    if history is None:
        return {
            "success": False,
            "message": "Conversation history not found"
        }

    approved_memory_ids = history["approved_memory_ids"]

    if memory_id not in approved_memory_ids:
        approved_memory_ids.append(memory_id)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE conversation_history
    SET approved_memory_ids = ?
    WHERE conversation_id = ?
    """, (
        json.dumps(approved_memory_ids),
        conversation_id
    ))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "conversation_id": conversation_id,
        "approved_memory_ids": approved_memory_ids
    }


def insert_pending_candidate(candidate, conversation_id):

    project_name = candidate.get("project", "USMOS")
    duplicate = find_duplicate_pending_item(candidate, project_name)

    if duplicate is not None:
        return {
            "created": False,
            "item": duplicate,
            "message": "Duplicate pending memory skipped"
        }

    timestamp = current_timestamp()
    proposed_supersession = json.dumps(candidate.get("possible_supersedes", []))

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO pending_memory_queue (
        conversation_id,
        project_name,
        memory_type,
        title,
        content,
        detected_reason,
        timestamp,
        proposed_supersession,
        approval_status
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        conversation_id,
        project_name,
        candidate["memory_type"],
        candidate["title"],
        candidate["content"],
        candidate.get("reason"),
        timestamp,
        proposed_supersession,
        PENDING_STATUS
    ))

    conn.commit()
    pending_id = cursor.lastrowid
    conn.close()

    return {
        "created": True,
        "item": get_pending_item(pending_id),
        "message": "Pending memory queued"
    }


def queue_conversation_memory_candidates(
    user_message,
    assistant_message=None,
    project_name="USMOS",
    source="conversation"
):

    conversation_id = generate_conversation_id()
    original_sentence = user_message or ""

    create_conversation_history(
        conversation_id=conversation_id,
        original_sentence=original_sentence,
        source=source
    )

    analysis = analyze_conversation_for_memory(
        user_message=user_message,
        assistant_message=assistant_message,
        project_name=project_name
    )
    created_items = []
    duplicate_items = []

    for candidate in analysis["candidates"]:
        insert_result = insert_pending_candidate(
            candidate=candidate,
            conversation_id=conversation_id
        )

        if insert_result["created"]:
            created_items.append(insert_result["item"])
        else:
            duplicate_items.append(insert_result["item"])

    return {
        "success": True,
        "conversation_id": conversation_id,
        "project": project_name,
        "created": len(created_items),
        "duplicates": len(duplicate_items),
        "pending_items": created_items,
        "duplicate_items": duplicate_items
    }


def list_pending_memory_items(
    project_name=None,
    status=None,
    memory_type=None,
    search=None
):

    clauses = []
    params = []

    if project_name:
        clauses.append("project_name = ?")
        params.append(project_name)

    if status:
        clauses.append("approval_status = ?")
        params.append(status)

    if memory_type:
        clauses.append("memory_type = ?")
        params.append(memory_type)

    if search:
        clauses.append("(title LIKE ? OR content LIKE ?)")
        search_term = f"%{search}%"
        params.extend([search_term, search_term])

    where_clause = ""

    if clauses:
        where_clause = "WHERE " + " AND ".join(clauses)

    query = f"""
    SELECT
        pending_id,
        conversation_id,
        project_name,
        memory_type,
        title,
        content,
        detected_reason,
        timestamp,
        proposed_supersession,
        approval_status,
        approved_memory_id,
        updated_at
    FROM pending_memory_queue
    {where_clause}
    ORDER BY pending_id DESC
    """

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [row_to_pending_item(row) for row in rows]


def get_pending_queue_counts(project_name=None):

    items = list_pending_memory_items(project_name=project_name)
    counts = {
        PENDING_STATUS: 0,
        APPROVED_STATUS: 0,
        REJECTED_STATUS: 0
    }

    for item in items:
        counts[item["approval_status"]] += 1

    return counts


def pending_item_to_candidate(item):

    return {
        "project": item["project_name"],
        "memory_type": item["memory_type"],
        "title": item["title"],
        "content": item["content"],
        "confidence": 100,
        "source": "conversation",
        "requires_approval": True,
        "reason": item["detected_reason"],
        "possible_supersedes": item.get("proposed_supersession", [])
    }


def update_pending_status(pending_id, status, approved_memory_id=None):

    if status not in VALID_APPROVAL_STATUSES:
        return {
            "success": False,
            "message": f"Invalid approval status: {status}"
        }

    updated_at = current_timestamp()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE pending_memory_queue
    SET
        approval_status = ?,
        approved_memory_id = ?,
        updated_at = ?
    WHERE pending_id = ?
    """, (
        status,
        approved_memory_id,
        updated_at,
        pending_id
    ))

    changed = cursor.rowcount
    conn.commit()
    conn.close()

    if changed == 0:
        return {
            "success": False,
            "message": "Pending memory not found"
        }

    return {
        "success": True,
        "pending_id": pending_id,
        "approval_status": status,
        "approved_memory_id": approved_memory_id
    }


def get_first_supersession_id(item):

    proposed_supersession = item.get("proposed_supersession") or []

    if not proposed_supersession:
        return None

    return proposed_supersession[0].get("memory_id")


def approve_pending_memory(pending_id):

    item = get_pending_item(pending_id)

    if item is None:
        return {
            "success": False,
            "message": "Pending memory not found"
        }

    if item["approval_status"] == APPROVED_STATUS:
        return {
            "success": True,
            "pending_id": pending_id,
            "memory_id": item["approved_memory_id"],
            "message": "Pending memory already approved"
        }

    if item["approval_status"] == REJECTED_STATUS:
        return {
            "success": False,
            "pending_id": pending_id,
            "message": "Rejected memory cannot be approved"
        }

    supersede_memory_id = get_first_supersession_id(item)
    save_result = save_approved_memory(
        candidate=pending_item_to_candidate(item),
        approved=True,
        supersede_memory_id=supersede_memory_id,
        approve_supersede=supersede_memory_id is not None
    )

    if not save_result["success"]:
        return {
            "success": False,
            "pending_id": pending_id,
            "message": save_result["message"]
        }

    update_result = update_pending_status(
        pending_id=pending_id,
        status=APPROVED_STATUS,
        approved_memory_id=save_result["memory_id"]
    )

    if save_result.get("memory_id"):
        add_approved_memory_to_conversation(
            conversation_id=item["conversation_id"],
            memory_id=save_result["memory_id"]
        )

    return {
        "success": update_result["success"],
        "pending_id": pending_id,
        "memory_id": save_result["memory_id"],
        "superseded": save_result.get("superseded", False),
        "supersede_result": save_result.get("supersede_result"),
        "message": "Pending memory approved"
    }


def reject_pending_memory(pending_id):

    item = get_pending_item(pending_id)

    if item is None:
        return {
            "success": False,
            "message": "Pending memory not found"
        }

    if item["approval_status"] == APPROVED_STATUS:
        return {
            "success": False,
            "pending_id": pending_id,
            "message": "Approved memory cannot be rejected"
        }

    result = update_pending_status(
        pending_id=pending_id,
        status=REJECTED_STATUS,
        approved_memory_id=item.get("approved_memory_id")
    )
    result["message"] = "Pending memory rejected"

    return result


def approve_pending_memories(project_name=None, memory_type=None):

    items = list_pending_memory_items(
        project_name=project_name,
        status=PENDING_STATUS,
        memory_type=memory_type
    )
    results = []

    for item in items:
        results.append(approve_pending_memory(item["pending_id"]))

    return {
        "success": True,
        "count": len(results),
        "results": results
    }


def reject_pending_memories(project_name=None, memory_type=None):

    items = list_pending_memory_items(
        project_name=project_name,
        status=PENDING_STATUS,
        memory_type=memory_type
    )
    results = []

    for item in items:
        results.append(reject_pending_memory(item["pending_id"]))

    return {
        "success": True,
        "count": len(results),
        "results": results
    }
