import json
from time import perf_counter

from src.llm import ollama_client
from src.llm.context_builder import build_context_package
from src.llm.context_builder import build_llm_context


SYSTEM_PROMPT = """You answer only from USMOS evidence.
If evidence is missing, say: "I do not have evidence for that."
If the question asks whether a project uses cloud, APIs, internet, or external services,
and evidence says local-only, no cloud access, avoid cloud APIs, sandbox-controlled,
or no external API, answer "No" and cite that evidence.
If evidence directly says something is prohibited or avoided, treat it as negative evidence.
Do not invent facts.
Keep the answer concise."""

NO_EVIDENCE_ANSWER = "I do not have evidence for that."
DEFAULT_MODEL = "llama3.2"
PROMPT_MODES = {
    "compact",
    "full"
}
NEGATIVE_USE_QUESTION_PHRASES = [
    "cloud",
    "api",
    "apis",
    "internet",
    "external service",
    "external services"
]
NEGATIVE_EVIDENCE_PHRASES = [
    "local-only",
    "local only",
    "no cloud",
    "no cloud access",
    "avoid cloud",
    "avoid cloud apis",
    "sandbox-controlled",
    "sandbox controlled",
    "no external api",
    "no external apis",
    "does not send"
]
DATABASE_QUESTION_PHRASES = [
    "database",
    "storage engine",
    "what database"
]
DATABASE_TECHNOLOGIES = [
    ("PostgreSQL", "postgresql"),
    ("SQLite", "sqlite")
]


def choose_default_model():

    models = ollama_client.list_models()

    if models:
        return models[0]

    return DEFAULT_MODEL


def validate_prompt_mode(mode):

    if mode not in PROMPT_MODES:
        raise ValueError("mode must be compact or full")

    return mode


def build_compact_prompt(context_package):

    return (
        SYSTEM_PROMPT
        + "\n\nUSMOS Evidence Context:\n"
        + context_package["context_text"]
        + "\n\nAnswer using only the evidence above."
    )


def build_full_prompt(context_package):

    trusted_context = {
        "project": context_package["project"],
        "question": context_package["question"],
        "selected_memories": context_package["selected_memories"],
        "evidence": context_package["evidence"],
        "reasoning_trace": context_package["reasoning_trace"],
        "memory_ids": context_package["memory_ids"],
        "contradiction_warning": context_package.get("contradiction_warning")
    }

    return (
        SYSTEM_PROMPT
        + "\n\nTrusted USMOS Context:\n"
        + json.dumps(trusted_context, indent=2)
        + "\n\nUser Question:\n"
        + context_package["question"]
        + "\n\nAnswer using only the trusted context."
    )


def build_prompt(context_package, mode="compact"):

    validate_prompt_mode(mode)

    if mode == "full":
        return build_full_prompt(context_package)

    return build_compact_prompt(context_package)


def collect_trust_scores(evidence_trace):

    trust_scores = []

    for evidence in evidence_trace:
        trust_scores.append({
            "memory_id": evidence["memory_id"],
            "trust_score": evidence["trust_score"],
            "trust_explanation": evidence.get("trust_explanation")
        })

    return trust_scores


def question_asks_negative_use(question):

    question_lower = question.lower()

    for phrase in NEGATIVE_USE_QUESTION_PHRASES:
        if phrase in question_lower:
            return True

    return False


def question_asks_database(question):

    question_lower = question.lower()

    for phrase in DATABASE_QUESTION_PHRASES:
        if phrase in question_lower:
            return True

    question_words = question_lower.replace("?", " ").split()

    return "db" in question_words


def clean_evidence_content(content):

    clean_content = " ".join(content.split())

    for prefix in [
        "Decision:",
        "Fact:",
        "Checkpoint:",
        "Task:",
        "Event:"
    ]:
        if clean_content.startswith(prefix):
            clean_content = clean_content[len(prefix):].strip()

    return clean_content


def content_says_use_technology(content, technology_keyword):

    content_lower = content.lower()
    use_phrases = [
        f"will use {technology_keyword}",
        f"uses {technology_keyword}",
        f"use {technology_keyword}"
    ]

    for phrase in use_phrases:
        if phrase in content_lower:
            return True

    return False


def find_database_evidence(context_package):

    if not question_asks_database(context_package["question"]):
        return None

    evidence_items = context_package.get("evidence", [])

    for evidence in evidence_items:
        content = evidence.get("content", "")
        content_lower = content.lower()

        if "instead of" not in content_lower:
            continue

        current_side = content_lower.split("instead of", 1)[0]

        for technology_name, technology_keyword in DATABASE_TECHNOLOGIES:
            if (
                technology_keyword in current_side
                and content_says_use_technology(content, technology_keyword)
            ):
                return technology_name, evidence

    for technology_name, technology_keyword in DATABASE_TECHNOLOGIES:
        for evidence in evidence_items:
            content = evidence.get("content", "")

            if content_says_use_technology(content, technology_keyword):
                return technology_name, evidence

    return None


def build_database_evidence_answer(context_package):

    database_evidence = find_database_evidence(context_package)

    if database_evidence is None:
        return None

    technology_name, evidence = database_evidence
    project_name = context_package["project"]
    evidence_content = clean_evidence_content(evidence["content"])

    return (
        f"{project_name} uses {technology_name}. "
        f"Evidence: {evidence_content} "
        f"(Memory #{evidence['memory_id']})."
    )


def find_negative_evidence(context_package):

    if not question_asks_negative_use(context_package["question"]):
        return None

    for evidence in context_package.get("evidence", []):
        content = evidence.get("content", "")
        content_lower = content.lower()

        for phrase in NEGATIVE_EVIDENCE_PHRASES:
            if phrase in content_lower:
                return evidence

    return None


def build_negative_evidence_answer(context_package):

    evidence = find_negative_evidence(context_package)

    if evidence is None:
        return None

    project_name = context_package["project"]
    question_lower = context_package["question"].lower()

    if "internet" in question_lower:
        denied_target = "internet access"
    elif "external service" in question_lower or "external services" in question_lower:
        denied_target = "external services"
    elif "api" in question_lower or "apis" in question_lower:
        denied_target = "cloud APIs"
    else:
        denied_target = "cloud access"

    evidence_content = clean_evidence_content(evidence["content"])

    return (
        f"No. {project_name} does not use {denied_target}. "
        f"Evidence: {evidence_content} "
        f"(Memory #{evidence['memory_id']})."
    )


def ask(
    question,
    model=None,
    project_name="USMOS",
    max_results=5,
    mode="compact",
    max_memories=None
):

    started_at = perf_counter()
    validate_prompt_mode(mode)

    if max_memories is None:
        max_memories = max_results

    retrieval_started_at = perf_counter()

    if mode == "full":
        context_package = build_context_package(
            question=question,
            project_name=project_name,
            max_results=max_memories
        )
    else:
        context_package = build_llm_context(
            question=question,
            project_name=project_name,
            max_memories=max_memories
        )

    retrieval_duration = perf_counter() - retrieval_started_at
    prompt_started_at = perf_counter()
    prompt = build_prompt(
        context_package=context_package,
        mode=mode
    )
    prompt_build_duration = perf_counter() - prompt_started_at
    selected_model = model or choose_default_model()

    if not context_package["memory_ids"]:
        total_duration = perf_counter() - started_at

        return {
            "success": True,
            "project": context_package["project"],
            "question": question,
            "model": selected_model,
            "mode": mode,
            "max_memories": max_memories,
            "answer": NO_EVIDENCE_ANSWER,
            "context": context_package,
            "prompt": prompt,
            "evidence_trace": [],
            "memory_ids": [],
            "trust_scores": [],
            "retrieval_duration_seconds": round(retrieval_duration, 6),
            "prompt_build_duration_seconds": round(prompt_build_duration, 6),
            "ollama_duration_seconds": 0,
            "total_duration_seconds": round(total_duration, 6),
            "response_time_seconds": round(total_duration, 6)
        }

    database_evidence_answer = None
    negative_evidence_answer = None

    if mode == "compact":
        database_evidence_answer = build_database_evidence_answer(context_package)
        negative_evidence_answer = build_negative_evidence_answer(context_package)

    if database_evidence_answer:
        total_duration = perf_counter() - started_at

        return {
            "success": True,
            "project": context_package["project"],
            "question": question,
            "model": selected_model,
            "mode": mode,
            "max_memories": max_memories,
            "answer": database_evidence_answer,
            "context": context_package,
            "prompt": prompt,
            "evidence_trace": context_package["evidence"],
            "memory_ids": context_package["memory_ids"],
            "trust_scores": collect_trust_scores(context_package["evidence"]),
            "retrieval_duration_seconds": round(retrieval_duration, 6),
            "prompt_build_duration_seconds": round(prompt_build_duration, 6),
            "ollama_duration_seconds": 0,
            "total_duration_seconds": round(total_duration, 6),
            "response_time_seconds": round(total_duration, 6)
        }

    if negative_evidence_answer:
        total_duration = perf_counter() - started_at

        return {
            "success": True,
            "project": context_package["project"],
            "question": question,
            "model": selected_model,
            "mode": mode,
            "max_memories": max_memories,
            "answer": negative_evidence_answer,
            "context": context_package,
            "prompt": prompt,
            "evidence_trace": context_package["evidence"],
            "memory_ids": context_package["memory_ids"],
            "trust_scores": collect_trust_scores(context_package["evidence"]),
            "retrieval_duration_seconds": round(retrieval_duration, 6),
            "prompt_build_duration_seconds": round(prompt_build_duration, 6),
            "ollama_duration_seconds": 0,
            "total_duration_seconds": round(total_duration, 6),
            "response_time_seconds": round(total_duration, 6)
        }

    ollama_started_at = perf_counter()

    try:
        answer = ollama_client.chat(
            model=selected_model,
            prompt=prompt
        )
        success = True
    except RuntimeError as error:
        answer = str(error)
        success = False

    ollama_duration = perf_counter() - ollama_started_at
    total_duration = perf_counter() - started_at

    return {
        "success": success,
        "project": context_package["project"],
        "question": question,
        "model": selected_model,
        "mode": mode,
        "max_memories": max_memories,
        "answer": answer,
        "context": context_package,
        "prompt": prompt,
        "evidence_trace": context_package["evidence"],
        "memory_ids": context_package["memory_ids"],
        "trust_scores": collect_trust_scores(context_package["evidence"]),
        "retrieval_duration_seconds": round(retrieval_duration, 6),
        "prompt_build_duration_seconds": round(prompt_build_duration, 6),
        "ollama_duration_seconds": round(ollama_duration, 6),
        "total_duration_seconds": round(total_duration, 6),
        "response_time_seconds": round(total_duration, 6)
    }
