from datetime import datetime
import json

from src.memory.memory_engine import (
    create_memory,
    get_connection,
    index_memory_keywords,
    list_memories_by_project,
    read_memory,
    supersede_memory,
)


IMPORTANCE_BY_TYPE = {
    "decision": 9,
    "task": 7,
    "checkpoint": 9,
    "event": 6,
    "project_note": 5
}


def generate_conversation_session_id():

    return datetime.now().strftime("conv_%Y%m%d_%H%M%S")


def build_conversation_metadata(candidate, session_id):

    return {
        "project": candidate.get("project", "USMOS"),
        "memory_scope": "real",
        "source": "conversation",
        "conversation_approved": True,
        "detected_reason": candidate.get("reason"),
        "created_from": "conversation",
        "conversation_session_id": session_id
    }


def get_candidate_list(candidates):

    if isinstance(candidates, dict):
        return candidates.get("candidates", [])

    return candidates or []


def preview_memory_candidates(candidates, include_save_prompt=True):

    candidate_list = get_candidate_list(candidates)

    if not candidate_list:
        return "No conversation memories detected."

    lines = ["Potential memories detected:", ""]

    for index, candidate in enumerate(candidate_list, start=1):
        label = candidate["memory_type"].replace("_", " ").title()

        lines.append(f"{index}. {label}")
        lines.append(f"Title: {candidate['title']}")
        lines.append(f"Content: {candidate['content']}")
        lines.append(f"Reason: {candidate['reason']}")

        possible_supersedes = candidate.get("possible_supersedes") or []

        if possible_supersedes:
            lines.append("Possible existing decision to supersede:")

            for memory in possible_supersedes:
                lines.append(f"#{memory['memory_id']}: {memory['title']}")

        if include_save_prompt:
            lines.append("Save? yes/no/edit")

        lines.append("")

    return "\n".join(lines).rstrip()


def find_existing_duplicate_memory(candidate):

    project_name = candidate.get("project", "USMOS")

    for memory in list_memories_by_project(project_name):
        if memory["memory_type"] != candidate["memory_type"]:
            continue

        if memory["title"] == candidate["title"]:
            return memory

    return None


def upgrade_existing_conversation_memory(
    memory_id,
    candidate,
    conversation_session_id=None
):

    existing_memory = read_memory(memory_id)

    if existing_memory is None:
        return {
            "success": False,
            "memory_id": memory_id,
            "message": "Memory not found"
        }

    session_id = conversation_session_id or generate_conversation_session_id()
    metadata = existing_memory.get("metadata") or {}
    metadata.update(build_conversation_metadata(candidate, session_id))
    metadata_json = json.dumps(metadata)
    importance = IMPORTANCE_BY_TYPE.get(candidate["memory_type"], 5)
    updated_at = datetime.now().isoformat()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    UPDATE memories
    SET
        metadata = ?,
        importance = ?,
        confidence = ?,
        source = ?,
        updated_at = ?
    WHERE id = ?
    """, (
        metadata_json,
        importance,
        100,
        "conversation",
        updated_at,
        memory_id
    ))

    conn.commit()
    conn.close()
    index_memory_keywords(memory_id)

    return {
        "success": True,
        "memory_id": memory_id,
        "conversation_session_id": session_id,
        "message": "Existing conversation memory upgraded"
    }


def save_approved_memory(
    candidate,
    approved=True,
    edited_title=None,
    edited_content=None,
    supersede_memory_id=None,
    approve_supersede=False,
    conversation_session_id=None
):

    if not approved:
        return {
            "success": True,
            "saved": False,
            "memory_id": None,
            "message": "Candidate rejected"
        }

    session_id = conversation_session_id or generate_conversation_session_id()
    title = edited_title or candidate["title"]
    content = edited_content or candidate["content"]
    memory_type = candidate["memory_type"]
    metadata = build_conversation_metadata(candidate, session_id)

    create_result = create_memory(
        memory_type=memory_type,
        title=title,
        content=content,
        metadata=metadata,
        importance=IMPORTANCE_BY_TYPE.get(memory_type, 5),
        confidence=100,
        source="conversation"
    )
    was_duplicate = False

    if not create_result["success"]:
        existing_duplicate = find_existing_duplicate_memory(candidate)

        if existing_duplicate is not None:
            upgrade_result = upgrade_existing_conversation_memory(
                memory_id=existing_duplicate["id"],
                candidate=candidate,
                conversation_session_id=session_id
            )

            if upgrade_result["success"]:
                create_result = {
                    "success": True,
                    "memory_id": existing_duplicate["id"],
                    "message": "Duplicate memory reused and upgraded"
                }
                was_duplicate = True

    result = {
        "success": create_result["success"],
        "saved": create_result["success"],
        "memory_id": create_result.get("memory_id"),
        "message": create_result["message"],
        "conversation_session_id": session_id,
        "duplicate_reused": was_duplicate,
        "superseded": False,
        "supersede_result": None
    }

    if (
        create_result["success"]
        and approve_supersede
        and supersede_memory_id is not None
    ):
        supersede_result = supersede_memory(
            old_memory_id=supersede_memory_id,
            new_memory_id=create_result["memory_id"]
        )
        result["superseded"] = supersede_result["success"]
        result["supersede_result"] = supersede_result

    return result
