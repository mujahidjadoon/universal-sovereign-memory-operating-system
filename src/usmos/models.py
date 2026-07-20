from dataclasses import dataclass
from typing import Any

from src.memory import memory_engine


@dataclass
class MemoryAnswerResult:
    answer: str
    memory_ids: list
    trust_scores: dict
    retrieval_duration_seconds: float
    prompt_build_duration_seconds: float
    ollama_duration_seconds: float
    total_duration_seconds: float
    answered_without_llm: bool
    raw: dict[str, Any] | None = None

    def __str__(self):

        return self.answer

    def __contains__(self, value):

        return value in self.answer


def metadata_for_project(metadata=None, project_name="USMOS"):

    clean_metadata = metadata.copy() if metadata else {}

    if not clean_metadata.get("project"):
        clean_metadata["project"] = project_name

    return clean_metadata


def save_memory(
    memory_type,
    title,
    content,
    project_name="USMOS",
    metadata=None,
    importance=5,
    confidence=100,
    source="user"
):

    return memory_engine.create_memory(
        memory_type=memory_type,
        title=title,
        content=content,
        metadata=metadata_for_project(metadata, project_name),
        importance=importance,
        confidence=confidence,
        source=source
    )


def save_decision(
    title,
    content,
    project_name="USMOS",
    metadata=None,
    importance=8,
    confidence=100,
    source="user"
):

    return memory_engine.create_decision(
        title=title,
        content=content,
        metadata=metadata_for_project(metadata, project_name),
        importance=importance,
        confidence=confidence,
        source=source
    )


def save_task(
    title,
    content,
    project_name="USMOS",
    metadata=None,
    importance=6,
    confidence=100,
    source="user"
):

    return memory_engine.create_task(
        title=title,
        content=content,
        metadata=metadata_for_project(metadata, project_name),
        importance=importance,
        confidence=confidence,
        source=source
    )


def save_checkpoint(
    title,
    content,
    project_name="USMOS",
    metadata=None,
    importance=9,
    confidence=100,
    source="checkpoint"
):

    return memory_engine.create_checkpoint(
        title=title,
        content=content,
        metadata=metadata_for_project(metadata, project_name),
        importance=importance,
        confidence=confidence,
        source=source
    )


def save_event(
    title,
    content,
    project_name="USMOS",
    metadata=None,
    importance=5,
    confidence=100,
    source="user"
):

    return memory_engine.create_event(
        title=title,
        content=content,
        metadata=metadata_for_project(metadata, project_name),
        importance=importance,
        confidence=confidence,
        source=source
    )


def save_fact(
    title,
    content,
    project_name="USMOS",
    metadata=None,
    importance=5,
    confidence=100,
    source="user"
):

    return memory_engine.create_project_note(
        title=title,
        content=content,
        metadata=metadata_for_project(metadata, project_name),
        importance=importance,
        confidence=confidence,
        source=source
    )
