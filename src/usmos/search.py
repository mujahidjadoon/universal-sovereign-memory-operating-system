from src.memory import memory_engine


def status(project_name="USMOS"):

    return memory_engine.get_project_phase_summary(project_name)


def search(keyword, project_name="USMOS"):

    memories = memory_engine.search_memories(keyword)
    project_memories = []

    for memory in memories:
        metadata = memory.get("metadata") or {}

        if metadata.get("project") == project_name:
            project_memories.append(memory)

    return project_memories


def answer(question, project_name="USMOS", max_results=5):

    return memory_engine.answer_with_reasoning(
        question=question,
        project_name=project_name,
        max_results=max_results
    )


def timeline(project_name="USMOS", include_tests=False):

    return memory_engine.summarize_project_timeline(
        project_name=project_name,
        include_tests=include_tests
    )


def graph(project_name="USMOS"):

    return memory_engine.get_project_graph(project_name)
