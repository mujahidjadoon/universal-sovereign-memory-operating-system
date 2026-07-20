import re
from time import perf_counter

from src.books.book_models import BookAnswerResult
from src.memory.memory_engine import (
    extract_keyword_words,
    extract_query_keywords,
    search_memories,
    search_memories_by_keyword_index,
)


NO_BOOK_EVIDENCE_ANSWER = "I do not have evidence for that in the selected book."
UNKNOWN_TECH_TERMS = [
    "kubernetes"
]
MIN_RELEVANCE_SCORE = 2
STRONGEST_BOOK_MARGIN = 1
QUESTION_STOPWORDS = {
    "about",
    "answer",
    "book",
    "books",
    "does",
    "discuss",
    "discusses",
    "do",
    "explain",
    "explains",
    "from",
    "mention",
    "mentions",
    "say",
    "says",
    "selected",
    "talk",
    "talks",
    "that",
    "these",
    "this",
    "what",
    "which",
    "with"
}
BOOK_SEMANTIC_GROUPS = {
    "sqlite": [
        "sqlite",
        "database",
        "local file",
        "index",
        "indexes",
        "indexing",
        "lookup"
    ],
    "context_window": [
        "context",
        "context window",
        "context windows",
        "prompt",
        "model",
        "text limit",
        "memory"
    ],
    "local_first": [
        "local-first",
        "local first",
        "local-first architecture",
        "user control",
        "user-controlled",
        "syncing",
        "synchronization",
        "local data"
    ],
    "kubernetes": [
        "kubernetes",
        "cluster",
        "container orchestration"
    ]
}
QUESTION_LIST_MARKERS = [
    "section 3: long questions",
    "long questions",
    "short questions",
    "inquisitive questions",
    "mcqs",
    "multiple choice",
    "exercises",
    "differentiate between"
]
ANSWER_MARKERS = [
    "consists of",
    "is composed of",
    "composed of",
    "is made up of",
    "structure is",
    "includes",
    "contains",
    "function is",
    "called",
    "bowman's capsule",
    "bowman capsule",
    "glomerulus",
    "proximal convoluted tubule",
    "loop of henle",
    "distal convoluted tubule",
    "collecting duct"
]
EXPLANATORY_CONTENT_PHRASES = [
    "is defined as",
    "consists of",
    "structure",
    "function",
    "composed of",
    "called",
    "includes",
    "bowman's capsule",
    "bowman capsule",
    "glomerulus",
    "proximal convoluted tubule",
    "loop of henle",
    "distal convoluted tubule",
    "collecting duct"
]
STRUCTURE_RELATION_PHRASES = [
    "consists of",
    "includes",
    "composed of"
]


def normalize_title(title):

    if title is None:
        return None

    return " ".join(title.lower().split())


def memory_is_book_knowledge(memory, project_name, book_title=None):

    metadata = memory.get("metadata") or {}

    if metadata.get("project") != project_name:
        return False

    if metadata.get("content_kind") != "book_knowledge":
        return False

    if book_title is None:
        return True

    return normalize_title(metadata.get("book_title")) == normalize_title(book_title)


def get_memory_search_text(memory):

    metadata = memory.get("metadata") or {}
    return " ".join([
        memory.get("title", ""),
        memory.get("content", ""),
        metadata.get("book_title", ""),
        metadata.get("chapter", ""),
        metadata.get("section", "")
    ]).lower()


def get_exercise_filter_text(memory):

    metadata = memory.get("metadata") or {}
    return "\n".join([
        metadata.get("chapter", ""),
        metadata.get("section", ""),
        memory.get("title", ""),
        memory.get("content", "")
    ])


def normalize_text(text):

    return " ".join((text or "").lower().split())


def phrase_in_text(phrase, text):

    return normalize_text(phrase) in normalize_text(text)


def get_question_relevance_keywords(question):

    keywords = []

    for keyword in extract_query_keywords(question):
        if keyword in QUESTION_STOPWORDS:
            continue

        if len(keyword) <= 2:
            continue

        if keyword not in keywords:
            keywords.append(keyword)

    return keywords


def get_semantic_groups_for_text(text):

    groups = []

    for group_name, phrases in BOOK_SEMANTIC_GROUPS.items():
        for phrase in phrases:
            if phrase_in_text(phrase, text):
                groups.append(group_name)
                break

    return groups


def count_exact_content_overlap(question_keywords, memory):

    memory_words = set(extract_keyword_words(memory.get("content", "")))
    overlap = 0

    for keyword in question_keywords:
        if keyword in memory_words:
            overlap += 1

    return overlap


def count_important_phrase_matches(question, memory):

    question_groups = get_semantic_groups_for_text(question)
    content = memory.get("content", "")
    matches = 0

    for group_name in question_groups:
        for phrase in BOOK_SEMANTIC_GROUPS[group_name]:
            if phrase_in_text(phrase, question) and phrase_in_text(phrase, content):
                matches += 1

    return matches


def count_semantic_group_matches(question, memory):

    question_groups = set(get_semantic_groups_for_text(question))
    memory_groups = set(get_semantic_groups_for_text(memory.get("content", "")))

    return len(question_groups.intersection(memory_groups))


def question_mentions_book_title(question, memory):

    metadata = memory.get("metadata") or {}
    book_title = metadata.get("book_title")

    if not book_title:
        return False

    return phrase_in_text(book_title, question)


def count_location_matches(question, memory):

    question_lower = question.lower()

    if "chapter" not in question_lower and "section" not in question_lower:
        return 0

    metadata = memory.get("metadata") or {}
    location_text = " ".join([
        metadata.get("chapter", ""),
        metadata.get("section", "")
    ])
    question_keywords = get_question_relevance_keywords(question)
    location_words = set(extract_keyword_words(location_text))
    matches = 0

    for keyword in question_keywords:
        if keyword in location_words:
            matches += 1

    return matches


def line_is_explain_question_prompt(line):

    clean_line = normalize_text(line)

    return clean_line.startswith("explain ")


def contains_answer_marker(content):

    for marker in ANSWER_MARKERS:
        if phrase_in_text(marker, content):
            return True

    return False


def contains_numbered_question_prompt(content):

    return re.search(
        r"(^|\n)\s*\d+[\.\)]\s*"
        r"(explain|describe|name|differentiate)\b",
        content,
        flags=re.IGNORECASE
    ) is not None


def is_exercise_prompt_chunk(content):

    if contains_answer_marker(content):
        return False

    normalized_content = normalize_text(content)

    for marker in QUESTION_LIST_MARKERS:
        if marker in normalized_content:
            return True

    if contains_numbered_question_prompt(content):
        return True

    for line in content.splitlines():
        if line_is_explain_question_prompt(line):
            return True

    return False


def count_question_prompt_penalties(memory):

    content = memory.get("content", "")
    normalized_content = normalize_text(get_memory_search_text(memory))
    penalty = 0

    for marker in QUESTION_LIST_MARKERS:
        if marker in normalized_content:
            penalty += 1

    for line in content.splitlines():
        if line_is_explain_question_prompt(line):
            penalty += 1

    return penalty


def count_explanatory_content_boosts(memory):

    content = memory.get("content", "")
    boosts = 0

    for phrase in EXPLANATORY_CONTENT_PHRASES:
        if phrase_in_text(phrase, content):
            boosts += 1

    return boosts


def get_structure_question_subject(question):

    question_text = normalize_text(question)

    if "structure of " not in question_text:
        return None

    subject_text = question_text.split("structure of ", 1)[1]
    subject_words = []

    for word in subject_text.split():
        clean_word = word.strip(".,?!:;()[]{}")

        if not clean_word:
            continue

        if clean_word in {"a", "an", "the"}:
            continue

        if clean_word in QUESTION_STOPWORDS:
            break

        subject_words.append(clean_word)

        if len(subject_words) >= 3:
            break

    if not subject_words:
        return None

    return " ".join(subject_words)


def count_structure_answer_boost(question, memory):

    subject = get_structure_question_subject(question)

    if subject is None:
        return 0

    content = memory.get("content", "")

    if not phrase_in_text(subject, content):
        return 0

    for phrase in STRUCTURE_RELATION_PHRASES:
        if phrase_in_text(phrase, content):
            return 3

    if phrase_in_text("structure", content):
        return 1

    return 0


def score_book_memory(memory, question, question_keywords):

    exact_overlap = count_exact_content_overlap(
        question_keywords=question_keywords,
        memory=memory
    )
    phrase_matches = count_important_phrase_matches(
        question=question,
        memory=memory
    )
    semantic_matches = count_semantic_group_matches(
        question=question,
        memory=memory
    )
    title_match = 1 if question_mentions_book_title(question, memory) else 0
    location_matches = count_location_matches(
        question=question,
        memory=memory
    )
    explanatory_boosts = count_explanatory_content_boosts(memory)
    structure_answer_boost = count_structure_answer_boost(
        question=question,
        memory=memory
    )
    question_prompt_penalties = count_question_prompt_penalties(memory)
    relevance_score = (
        exact_overlap
        + phrase_matches * 3
        + semantic_matches * 3
        + title_match * 2
        + location_matches
        + explanatory_boosts * 2
        + structure_answer_boost * 3
        - question_prompt_penalties * 4
    )

    return (
        relevance_score,
        exact_overlap,
        phrase_matches,
        semantic_matches,
        title_match,
        location_matches,
        explanatory_boosts,
        structure_answer_boost,
        question_prompt_penalties,
        memory["trust_score"],
        memory["id"]
    )


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

    memory_text = get_memory_search_text(memory)

    for term in required_terms:
        if term in memory_text:
            return True

    return False


def deduplicate_memories(memories):

    seen_ids = set()
    unique = []

    for memory in memories:
        if memory["id"] in seen_ids:
            continue

        seen_ids.add(memory["id"])
        unique.append(memory)

    return unique


def find_book_memories(question, project_name, book_title=None, max_results=5):

    question_keywords = get_question_relevance_keywords(question)
    required_unknown_terms = get_required_unknown_terms(question)
    candidates = search_memories_by_keyword_index(
        project_name=project_name,
        keywords=question_keywords,
        limit=max(max_results * 20, 50)
    )

    if not candidates:
        fallback_candidates = []

        for keyword in question_keywords:
            fallback_candidates.extend(search_memories(keyword))

        candidates = fallback_candidates

    candidates = deduplicate_memories(candidates)
    ranked = []

    for memory in candidates:
        if not memory_is_book_knowledge(
            memory=memory,
            project_name=project_name,
            book_title=book_title
        ):
            continue

        if not memory_contains_required_terms(
            memory=memory,
            required_terms=required_unknown_terms
        ):
            continue

        if is_exercise_prompt_chunk(get_exercise_filter_text(memory)):
            memory["book_exclusion_reason"] = "excluded_exercise_prompt"
            continue

        score = score_book_memory(
            memory=memory,
            question=question,
            question_keywords=question_keywords
        )

        if score[0] < MIN_RELEVANCE_SCORE:
            continue

        ranked.append((score, memory))

    ranked.sort(
        key=lambda item: item[0],
        reverse=True
    )

    if not book_title:
        ranked = filter_to_strongest_books(ranked)

    selected_memories = []

    for score, memory in ranked:
        scored_memory = memory.copy()
        scored_memory["book_relevance_score"] = score[0]
        selected_memories.append(scored_memory)

        if len(selected_memories) >= max_results:
            break

    return selected_memories


def filter_to_strongest_books(ranked_memories):

    if not ranked_memories:
        return []

    best_score_by_book = {}

    for score, memory in ranked_memories:
        metadata = memory.get("metadata") or {}
        book_title = metadata.get("book_title", "Unknown")
        relevance_score = score[0]

        if (
            book_title not in best_score_by_book
            or relevance_score > best_score_by_book[book_title]
        ):
            best_score_by_book[book_title] = relevance_score

    top_score = max(best_score_by_book.values())
    allowed_books = set()

    for book_title, book_score in best_score_by_book.items():
        if top_score - book_score <= STRONGEST_BOOK_MARGIN:
            allowed_books.add(book_title)

    filtered = []

    for score, memory in ranked_memories:
        metadata = memory.get("metadata") or {}
        book_title = metadata.get("book_title", "Unknown")

        if book_title in allowed_books:
            filtered.append((score, memory))

    return filtered


def make_excerpt(content, max_characters=320):

    clean_content = " ".join(content.split())

    if len(clean_content) <= max_characters:
        return clean_content

    return clean_content[:max_characters].rstrip() + "..."


def memory_to_book_evidence(memory):

    metadata = memory.get("metadata") or {}

    return {
        "memory_id": memory["id"],
        "book_title": metadata.get("book_title", "Unknown"),
        "author": metadata.get("author", ""),
        "chapter": metadata.get("chapter", "Unknown"),
        "section": metadata.get("section", "Unknown"),
        "excerpt": make_excerpt(memory["content"]),
        "full_content": memory["content"],
        "trust_score": memory["trust_score"],
        "relevance_score": memory.get("book_relevance_score")
    }


def build_book_answer(question, evidence, book_title=None):

    if not evidence:
        return NO_BOOK_EVIDENCE_ANSWER

    if book_title:
        first = evidence[0]
        return (
            f"{book_title} says: {first['excerpt']} "
            f"(Memory #{first['memory_id']}, "
            f"{first['chapter']} / {first['section']})."
        )

    books = []

    for item in evidence:
        if item["book_title"] not in books:
            books.append(item["book_title"])

    first = evidence[0]

    if len(books) == 1:
        return (
            f"{books[0]} says: {first['excerpt']} "
            f"(Memory #{first['memory_id']}, "
            f"{first['chapter']} / {first['section']})."
        )

    return (
        "Relevant book evidence was found in "
        + ", ".join(books)
        + f". Strongest evidence: {first['book_title']} says: "
        + f"{first['excerpt']} (Memory #{first['memory_id']})."
    )


def ask_book(
    question,
    project_name,
    book_title=None,
    model=None,
    max_results=5
):

    started_at = perf_counter()
    retrieval_started_at = perf_counter()
    memories = find_book_memories(
        question=question,
        project_name=project_name,
        book_title=book_title,
        max_results=max_results
    )
    retrieval_duration = perf_counter() - retrieval_started_at

    answer_started_at = perf_counter()
    evidence = []
    memory_ids = []
    trust_scores = {}

    for memory in memories:
        evidence_item = memory_to_book_evidence(memory)
        evidence.append(evidence_item)
        memory_ids.append(evidence_item["memory_id"])
        trust_scores[evidence_item["memory_id"]] = evidence_item["trust_score"]

    answer = build_book_answer(
        question=question,
        evidence=evidence,
        book_title=book_title
    )
    answer_duration = perf_counter() - answer_started_at

    return {
        "success": bool(evidence),
        "answer": answer,
        "project": project_name,
        "question": question,
        "book_title": book_title,
        "model": model,
        "evidence": evidence,
        "memory_ids": memory_ids,
        "trust_scores": trust_scores,
        "retrieval_duration_seconds": round(retrieval_duration, 6),
        "answer_duration_seconds": round(answer_duration, 6),
        "total_duration_seconds": round(perf_counter() - started_at, 6)
    }
