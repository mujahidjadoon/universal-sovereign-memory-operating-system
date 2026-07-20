from src.conversation import conversation_queue


def pending(project_name="USMOS", status=None, memory_type=None, search=None):

    return conversation_queue.list_pending_memory_items(
        project_name=project_name,
        status=status,
        memory_type=memory_type,
        search=search
    )


def approve(pending_id):

    return conversation_queue.approve_pending_memory(pending_id)


def reject(pending_id):

    return conversation_queue.reject_pending_memory(pending_id)


def approve_all(project_name="USMOS", memory_type=None):

    return conversation_queue.approve_pending_memories(
        project_name=project_name,
        memory_type=memory_type
    )


def reject_all(project_name="USMOS", memory_type=None):

    return conversation_queue.reject_pending_memories(
        project_name=project_name,
        memory_type=memory_type
    )
