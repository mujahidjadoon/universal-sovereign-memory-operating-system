from src.conversation.conversation_queue import queue_conversation_memory_candidates
from src.llm.conversation_bridge import ask as ask_ollama


def chat(
    question,
    project_name="USMOS",
    model=None,
    mode="compact",
    max_memories=5
):

    return ask_ollama(
        question=question,
        model=model,
        project_name=project_name,
        mode=mode,
        max_memories=max_memories
    )


def queue(
    user_message,
    assistant_message=None,
    project_name="USMOS",
    source="conversation"
):

    return queue_conversation_memory_candidates(
        user_message=user_message,
        assistant_message=assistant_message,
        project_name=project_name,
        source=source
    )
