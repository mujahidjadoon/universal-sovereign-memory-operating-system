from src.memory.memory_engine import analyze_question
from src.memory.memory_engine import detect_question_topic
from src.memory.memory_engine import detect_question_memory_type
from src.memory.memory_engine import explain_memory_selection
from src.memory.memory_engine import extract_keyword_words
from src.memory.memory_engine import extract_query_keywords
from src.memory.memory_engine import get_matching_semantic_groups
from src.memory.memory_engine import search_memories_by_keyword_index


QUERY_PRIORITY_PHRASES = {
    "cloud": [
        "cloud",
        "no cloud",
        "local-only",
        "local only",
        "avoid cloud",
        "cloud api",
        "cloud apis"
    ],
    "sqlite": [
        "sqlite",
        "database",
        "storage",
        "local storage"
    ],
    "snapshot": [
        "snapshot",
        "snapshots",
        "sandbox/snapshots"
    ],
    "approval": [
        "approval",
        "human approval",
        "deleting files",
        "delete files"
    ]
}

UNKNOWN_TECH_TERMS = [
    "kubernetes"
]

SUPERSESSION_INTENT_PHRASES = [
    "instead of",
    "replace",
    "no longer",
    "stop using"
]


def build_context_package(question, project_name="USMOS", max_results=5):

    explanation = explain_memory_selection(
        question=question,
        project_name=project_name,
        max_results=max_results
    )

    evidence_trace = explanation.get("evidence_trace", [])
    selected_memories = []
    memory_ids = []
    reasoning_trace = []

    for evidence in evidence_trace:
        memory_id = evidence["memory_id"]
        memory_ids.append(memory_id)
        reasoning_trace.append(evidence["selection_reason"])
        selected_memories.append({
            "memory_id": memory_id,
            "memory_type": evidence["memory_type"],
            "title": evidence["title"],
            "content": evidence["content"],
            "trust_score": evidence["trust_score"],
            "trust_explanation": evidence["trust_explanation"]
        })

    return {
        "success": explanation.get("success", False),
        "project": explanation.get("project", project_name),
        "question": question,
        "selected_memories": selected_memories,
        "evidence": evidence_trace,
        "reasoning_trace": reasoning_trace,
        "memory_ids": memory_ids,
        "contradiction_warning": explanation.get("contradiction_warning")
    }


def build_compact_evidence_line(index, evidence):

    return (
        f"{index}. "
        f"[{evidence['memory_type']} #{evidence['memory_id']} | "
        f"trust {evidence['trust_score']}] "
        f"{evidence['content']}"
    )


def get_memory_text(memory):

    return (
        memory["title"]
        + " "
        + memory["content"]
    ).lower()


def get_query_priority_phrases(question):

    question_lower = question.lower()
    priority_phrases = []

    for phrase_group in QUERY_PRIORITY_PHRASES.values():
        question_mentions_group = False

        for phrase in phrase_group:
            if phrase in question_lower:
                question_mentions_group = True
                break

        if question_mentions_group:
            for phrase in phrase_group:
                if phrase not in priority_phrases:
                    priority_phrases.append(phrase)

    return priority_phrases


def get_required_unknown_terms(question):

    question_lower = question.lower()
    required_terms = []

    for term in UNKNOWN_TECH_TERMS:
        if term in question_lower:
            required_terms.append(term)

    return required_terms


def memory_contains_required_terms(memory, required_terms):

    if not required_terms:
        return True

    memory_text = get_memory_text(memory)

    for term in required_terms:
        if term in memory_text:
            return True

    return False


def count_keyword_overlap(question_keywords, memory):

    memory_text = get_memory_text(memory)
    memory_keywords = set(extract_keyword_words(memory_text))
    overlap_count = 0

    for keyword in question_keywords:
        if keyword in memory_keywords:
            overlap_count += 1

    return overlap_count


def count_semantic_group_overlap(question, memory):

    question_groups = set(get_matching_semantic_groups(question))
    memory_groups = set(get_matching_semantic_groups(get_memory_text(memory)))

    return len(question_groups.intersection(memory_groups))


def count_priority_phrase_overlap(priority_phrases, memory):

    memory_text = get_memory_text(memory)
    overlap_count = 0

    for phrase in priority_phrases:
        if phrase in memory_text:
            overlap_count += 1

    return overlap_count


def get_conversation_approval_boost(memory):

    metadata = memory.get("metadata") or {}

    if metadata.get("conversation_approved") is True:
        return 100

    return 0


def get_conversation_source_boost(memory):

    if memory.get("source") == "conversation":
        return 50

    return 0


def get_supersession_intent_boost(memory):

    memory_text = get_memory_text(memory)

    for phrase in SUPERSESSION_INTENT_PHRASES:
        if phrase in memory_text:
            return 150

    return 0


def score_fast_llm_memory(memory, question, question_keywords, priority_phrases, requested_memory_type):

    keyword_overlap = count_keyword_overlap(
        question_keywords=question_keywords,
        memory=memory
    )
    semantic_overlap = count_semantic_group_overlap(
        question=question,
        memory=memory
    )
    priority_overlap = count_priority_phrase_overlap(
        priority_phrases=priority_phrases,
        memory=memory
    )
    memory_type_match = 0

    if requested_memory_type and memory["memory_type"] == requested_memory_type:
        memory_type_match = 1

    base_relevance_score = (
        keyword_overlap * 100
        + semantic_overlap * 50
        + memory_type_match * 75
        + priority_overlap * 100
    )
    boosted_score = (
        base_relevance_score
        + get_conversation_approval_boost(memory)
        + get_conversation_source_boost(memory)
        + get_supersession_intent_boost(memory)
    )

    return (
        boosted_score,
        base_relevance_score,
        memory["trust_score"],
        memory["id"]
    )


def get_fast_llm_memories(question, project_name="USMOS", max_memories=5):

    analysis = analyze_question(question)
    topic = analysis.get("topic")

    if topic is None:
        topic = detect_question_topic(question)

    requested_memory_type = analysis.get("memory_type")

    if requested_memory_type is None:
        requested_memory_type = detect_question_memory_type(question)

    keyword_candidates = extract_query_keywords(question, topic)

    if requested_memory_type:
        if requested_memory_type == "project_note":
            memory_type_keywords = [
                "project_note",
                "fact"
            ]
        else:
            memory_type_keywords = [
                requested_memory_type
            ]

        for keyword in memory_type_keywords:
            if keyword not in keyword_candidates:
                keyword_candidates.append(keyword)

    candidate_limit = max(25, max_memories * 10)
    indexed_memories = search_memories_by_keyword_index(
        project_name=project_name,
        keywords=keyword_candidates,
        limit=candidate_limit
    )
    question_keywords = extract_query_keywords(question, topic)
    priority_phrases = get_query_priority_phrases(question)
    required_unknown_terms = get_required_unknown_terms(question)
    ranked_memories = []

    for memory in indexed_memories:
        if requested_memory_type and memory["memory_type"] != requested_memory_type:
            continue

        if not memory_contains_required_terms(
            memory=memory,
            required_terms=required_unknown_terms
        ):
            continue

        score = score_fast_llm_memory(
            memory=memory,
            question=question,
            question_keywords=question_keywords,
            priority_phrases=priority_phrases,
            requested_memory_type=requested_memory_type
        )

        if score[1] <= 0:
            continue

        ranked_memories.append((score, memory))

    ranked_memories.sort(
        key=lambda item: item[0],
        reverse=True
    )
    selected_memories = []

    for score, memory in ranked_memories:
        selected_memories.append(memory)

        if len(selected_memories) >= max_memories:
            break

    return selected_memories


def build_llm_context(question, project_name="USMOS", max_memories=5):

    memories = get_fast_llm_memories(
        question=question,
        project_name=project_name,
        max_memories=max_memories
    )
    selected_memories = []
    memory_ids = []
    evidence = []
    context_lines = []

    context_lines.append(f"Project: {project_name}")
    context_lines.append(f"Question: {question}")
    context_lines.append("")
    context_lines.append("Evidence:")

    if not memories:
        context_lines.append("None.")

    for index, memory in enumerate(memories, start=1):
        compact_memory = {
            "memory_id": memory["id"],
            "memory_type": memory["memory_type"],
            "title": memory["title"],
            "content": memory["content"],
            "trust_score": memory["trust_score"]
        }
        selected_memories.append(compact_memory)
        evidence.append(compact_memory)
        memory_ids.append(memory["id"])
        context_lines.append(
            build_compact_evidence_line(
                index=index,
                evidence=compact_memory
            )
        )

    return {
        "success": bool(memories),
        "project": project_name,
        "question": question,
        "selected_memories": selected_memories,
        "evidence": evidence,
        "reasoning_trace": [],
        "memory_ids": memory_ids,
        "context_text": "\n".join(context_lines),
        "contradiction_warning": None
    }
