from dataclasses import dataclass


@dataclass
class BookChunk:
    text: str
    chapter: str
    section: str
    chunk_number: int


@dataclass
class BookEvidence:
    memory_id: int
    book_title: str
    chapter: str
    section: str
    excerpt: str
    trust_score: int


@dataclass
class BookAnswerResult:
    success: bool
    answer: str
    project: str
    question: str
    book_title: str | None
    evidence: list
    memory_ids: list
    trust_scores: dict
    retrieval_duration_seconds: float
    answer_duration_seconds: float
    model: str | None = None


@dataclass
class BookIngestionResult:
    success: bool
    project: str
    book_title: str
    author: str
    source_file: str
    chunks_created: int
    duplicates_skipped: int
    items: list
