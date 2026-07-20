import re

from src.memory.memory_engine import list_memories_by_project


DETECTION_RULES = [
    {
        "memory_type": "decision",
        "confidence": 80,
        "phrases": [
            "decision:",
            "decision",
            "we decided",
            "we will use",
            "from now on",
            "instead of",
            "replace",
            "stop using",
            "use ",
            "no longer use"
        ]
    },
    {
        "memory_type": "task",
        "confidence": 75,
        "phrases": [
            "task:",
            "we need to",
            "todo",
            "next step",
            "build",
            "fix",
            "implement"
        ]
    },
    {
        "memory_type": "checkpoint",
        "confidence": 85,
        "phrases": [
            "checkpoint:",
            "completed",
            "phase ",
            "phase x done",
            "verified",
            "passed tests",
            "stable"
        ]
    },
    {
        "memory_type": "event",
        "confidence": 70,
        "phrases": [
            "event:",
            "started",
            "ran benchmark",
            "deployed",
            "tested"
        ]
    },
    {
        "memory_type": "project_note",
        "confidence": 65,
        "phrases": [
            "remember",
            "note",
            "fact",
            "important"
        ]
    }
]

SUPERSESSION_PHRASES = [
    "instead of",
    "replace",
    "stop using",
    "no longer use"
]

COMMON_WORDS = {
    "about",
    "after",
    "again",
    "also",
    "before",
    "build",
    "decided",
    "decision",
    "from",
    "have",
    "instead",
    "into",
    "longer",
    "memory",
    "must",
    "need",
    "next",
    "only",
    "project",
    "replace",
    "should",
    "step",
    "stop",
    "that",
    "this",
    "using",
    "will",
    "with"
}


def normalize_words(text):

    words = re.findall(r"[a-z0-9]+", text.lower())

    return {
        word
        for word in words
        if len(word) > 3 and word not in COMMON_WORDS
    }


def split_conversation_text(text):

    segments = []

    for raw_line in text.splitlines():
        clean_line = raw_line.strip()

        if clean_line:
            segments.extend(
                part.strip()
                for part in re.split(r"(?<=[.!?])\s+", clean_line)
                if part.strip()
            )

    if segments:
        return segments

    return [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", text)
        if part.strip()
    ]


def clean_candidate_content(segment):

    content = segment.strip()

    prefixes = [
        "decision:",
        "checkpoint:",
        "event:",
        "we decided that ",
        "we decided ",
        "from now on ",
        "todo:",
        "task:",
        "remember:",
        "note:",
        "fact:"
    ]

    lower_content = content.lower()

    for prefix in prefixes:
        if lower_content.startswith(prefix):
            content = content[len(prefix):].strip()
            break

    if content:
        content = content[0].upper() + content[1:]

    return content


def build_candidate_title(memory_type, content):

    label = memory_type.replace("_", " ").title()
    short_content = content[:70].strip()

    if len(content) > 70:
        short_content = f"{short_content}..."

    return f"Conversation {label}: {short_content}"


def find_detection_rule(segment):

    lower_segment = segment.lower()

    for rule in DETECTION_RULES:
        for phrase in rule["phrases"]:
            if phrase in lower_segment:
                return rule, phrase

    return None, None


def contains_supersession_phrase(text):

    lower_text = text.lower()

    return any(phrase in lower_text for phrase in SUPERSESSION_PHRASES)


def get_text_after_phrase(text, phrase):

    lower_text = text.lower()
    phrase_index = lower_text.find(phrase)

    if phrase_index == -1:
        return ""

    return text[phrase_index + len(phrase):]


def get_text_before_phrase(text, phrase):

    lower_text = text.lower()
    phrase_index = lower_text.find(phrase)

    if phrase_index == -1:
        return ""

    return text[:phrase_index]


def extract_supersession_terms(content):

    old_text = ""
    new_text = ""
    lower_content = content.lower()

    if "instead of" in lower_content:
        old_text = get_text_after_phrase(content, "instead of")
        new_text = get_text_before_phrase(content, "instead of")
    elif "replace" in lower_content and " with " in lower_content:
        after_replace = get_text_after_phrase(content, "replace")
        lower_after_replace = after_replace.lower()
        with_index = lower_after_replace.find(" with ")

        if with_index != -1:
            old_text = after_replace[:with_index]
            new_text = after_replace[with_index + len(" with "):]
    elif "stop using" in lower_content:
        old_text = get_text_after_phrase(content, "stop using")
    elif "no longer use" in lower_content:
        old_text = get_text_after_phrase(content, "no longer use")

    return {
        "old_terms": normalize_words(old_text),
        "new_terms": normalize_words(new_text),
        "all_terms": normalize_words(content)
    }


def find_possible_superseded_decisions(content, project_name):

    supersession_terms = extract_supersession_terms(content)
    old_terms = supersession_terms["old_terms"]
    new_terms = supersession_terms["new_terms"]
    content_words = supersession_terms["all_terms"]

    if not content_words:
        return []

    possible_matches = []

    for memory in list_memories_by_project(project_name):
        if memory["memory_type"] != "decision":
            continue

        if memory["content"].strip().lower() == content.strip().lower():
            continue

        memory_words = normalize_words(
            f"{memory['title']} {memory['content']}"
        )
        overlap = content_words.intersection(memory_words)
        old_overlap = old_terms.intersection(memory_words)
        new_overlap = new_terms.intersection(memory_words)

        if old_terms and not old_overlap:
            continue

        if not old_terms and len(overlap) < 2:
            continue

        score = (
            len(old_overlap) * 100
            + len(new_overlap) * 20
            + len(overlap) * 10
        )

        if score > 0:
            possible_matches.append({
                "memory_id": memory["id"],
                "title": memory["title"],
                "content": memory["content"],
                "overlap_keywords": sorted(overlap),
                "old_keyword_matches": sorted(old_overlap),
                "new_keyword_matches": sorted(new_overlap),
                "match_score": score
            })

    possible_matches.sort(
        key=lambda memory: memory["match_score"],
        reverse=True
    )

    return possible_matches[:3]


def analyze_conversation_for_memory(
    user_message,
    assistant_message=None,
    project_name="USMOS"
):

    text_parts = [user_message or ""]

    if assistant_message:
        text_parts.append(assistant_message)

    full_text = "\n".join(text_parts)
    candidates = []

    for segment in split_conversation_text(full_text):
        rule, phrase = find_detection_rule(segment)

        if rule is None:
            continue

        content = clean_candidate_content(segment)

        if not content:
            continue

        candidate = {
            "project": project_name,
            "memory_type": rule["memory_type"],
            "title": build_candidate_title(rule["memory_type"], content),
            "content": content,
            "confidence": rule["confidence"],
            "source": "conversation",
            "requires_approval": True,
            "reason": f"Detected phrase: {phrase}"
        }

        if (
            rule["memory_type"] == "decision"
            and contains_supersession_phrase(content)
        ):
            candidate["possible_supersedes"] = (
                find_possible_superseded_decisions(content, project_name)
            )

        candidates.append(candidate)

    return {
        "project": project_name,
        "candidates": candidates
    }
