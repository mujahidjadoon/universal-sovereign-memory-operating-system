import re
from pathlib import Path

from src.books.book_models import BookChunk
from src.usmos import MemoryClient


SUPPORTED_BOOK_EXTENSIONS = {
    ".txt",
    ".md"
}

DEFAULT_CHAPTER = "Unknown"
DEFAULT_SECTION = "Unknown"


def normalize_space(text):

    return " ".join(text.split())


def detect_book_heading(line):

    clean_line = line.strip()

    if not clean_line:
        return None

    heading_text = clean_line.lstrip("#").strip()
    heading_lower = heading_text.lower()

    if re.match(r"^chapter\b", heading_lower):
        return {
            "type": "chapter",
            "title": heading_text.rstrip(":")
        }

    if clean_line.startswith("##"):
        return {
            "type": "section",
            "title": heading_text.rstrip(":")
        }

    if clean_line.endswith(":") and len(clean_line.split()) <= 12:
        return {
            "type": "section",
            "title": clean_line.rstrip(":")
        }

    return None


def read_book_text(file_path):

    path = Path(file_path)

    if path.suffix.lower() not in SUPPORTED_BOOK_EXTENSIONS:
        raise ValueError("Phase 20 supports .txt and .md files first.")

    return path.read_text(encoding="utf-8")


def extract_paragraph_records(text):

    chapter = DEFAULT_CHAPTER
    section = DEFAULT_SECTION
    paragraph_lines = []
    records = []

    def flush_paragraph():
        if not paragraph_lines:
            return

        paragraph_text = normalize_space(" ".join(paragraph_lines))
        paragraph_lines.clear()

        if paragraph_text:
            records.append({
                "text": paragraph_text,
                "chapter": chapter,
                "section": section
            })

    for raw_line in text.splitlines():
        line = raw_line.strip()
        heading = detect_book_heading(line)

        if heading:
            flush_paragraph()

            if heading["type"] == "chapter":
                chapter = heading["title"]
                section = DEFAULT_SECTION
            else:
                section = heading["title"]

            continue

        if not line:
            flush_paragraph()
            continue

        paragraph_lines.append(line)

    flush_paragraph()

    return records


def split_long_words(words, chunk_words, overlap_words, chapter, section, start_number):

    chunks = []
    index = 0
    chunk_number = start_number
    step = max(1, chunk_words - overlap_words)

    while index < len(words):
        word_slice = words[index:index + chunk_words]
        text = " ".join(word_slice).strip()

        if text:
            chunks.append(BookChunk(
                text=text,
                chapter=chapter,
                section=section,
                chunk_number=chunk_number
            ))
            chunk_number += 1

        if index + chunk_words >= len(words):
            break

        index += step

    return chunks, chunk_number


def chunk_book_text(text, chunk_words=250, overlap_words=40):

    if chunk_words <= 0:
        raise ValueError("chunk_words must be greater than zero")

    if overlap_words < 0:
        raise ValueError("overlap_words must be zero or greater")

    if overlap_words >= chunk_words:
        raise ValueError("overlap_words must be smaller than chunk_words")

    paragraph_records = extract_paragraph_records(text)
    chunks = []
    current_words = []
    current_chapter = DEFAULT_CHAPTER
    current_section = DEFAULT_SECTION
    chunk_number = 1

    def flush_current():
        nonlocal current_words
        nonlocal chunk_number

        if not current_words:
            return

        chunk_text = " ".join(current_words).strip()

        if chunk_text:
            chunks.append(BookChunk(
                text=chunk_text,
                chapter=current_chapter,
                section=current_section,
                chunk_number=chunk_number
            ))
            chunk_number += 1

        current_words = []

    for record in paragraph_records:
        paragraph_words = record["text"].split()

        if not paragraph_words:
            continue

        if len(paragraph_words) > chunk_words:
            flush_current()
            long_chunks, chunk_number = split_long_words(
                words=paragraph_words,
                chunk_words=chunk_words,
                overlap_words=overlap_words,
                chapter=record["chapter"],
                section=record["section"],
                start_number=chunk_number
            )
            chunks.extend(long_chunks)
            continue

        same_location = (
            current_chapter == record["chapter"]
            and current_section == record["section"]
        )

        if current_words and (
            not same_location
            or len(current_words) + len(paragraph_words) > chunk_words
        ):
            flush_current()

        current_chapter = record["chapter"]
        current_section = record["section"]
        current_words.extend(paragraph_words)

    flush_current()

    return chunks


def classify_book_chunk(text, chunk_number):

    text_lower = text.lower()

    if "definition" in text_lower or "defined as" in text_lower:
        return "definition", "Book Definition"

    if "concept" in text_lower:
        return "concept", "Book Concept"

    if chunk_number == 1:
        return "chapter_summary", "Book Chapter Summary"

    if "important" in text_lower or "key point" in text_lower:
        return "important_point", "Book Important Point"

    if '"' in text or "'" in text:
        return "quote_like_excerpt", "Book Excerpt"

    return "book_fact", "Book Fact"


def build_book_metadata(
    project_name,
    book_title,
    author,
    source_file,
    chapter,
    section,
    tags,
    book_memory_kind,
    original_source_file=None,
    extracted_source_file="",
    original_format=None,
    extraction_method=None
):

    source_file_value = original_source_file or source_file
    format_value = original_format or Path(source_file_value).suffix.lower().lstrip(".")
    extraction_method_value = extraction_method or "plain_text"

    return {
        "project": project_name,
        "book_title": book_title,
        "author": author or "",
        "source_file": str(source_file_value),
        "extracted_text_file": str(extracted_source_file or ""),
        "original_format": format_value,
        "extraction_method": extraction_method_value,
        "chapter": chapter,
        "section": section,
        "memory_scope": "real",
        "source": "book_ingestion",
        "content_kind": "book_knowledge",
        "book_memory_kind": book_memory_kind,
        "tags": tags or []
    }


def ingest_book_file(
    file_path,
    project_name,
    book_title,
    author="",
    tags=None,
    chunk_words=250,
    overlap_words=40,
    original_source_file=None,
    extracted_source_file="",
    original_format=None,
    extraction_method=None
):

    source_file = Path(file_path)
    text = read_book_text(source_file)
    chunks = chunk_book_text(
        text=text,
        chunk_words=chunk_words,
        overlap_words=overlap_words
    )
    memory = MemoryClient(project_name=project_name)
    created_count = 0
    duplicate_count = 0
    items = []

    for chunk in chunks:
        book_memory_kind, title_prefix = classify_book_chunk(
            text=chunk.text,
            chunk_number=chunk.chunk_number
        )
        title = f"{title_prefix}: {book_title} #{chunk.chunk_number}"
        metadata = build_book_metadata(
            project_name=project_name,
            book_title=book_title,
            author=author,
            source_file=source_file,
            chapter=chunk.chapter,
            section=chunk.section,
            tags=tags,
            book_memory_kind=book_memory_kind,
            original_source_file=original_source_file,
            extracted_source_file=extracted_source_file,
            original_format=original_format,
            extraction_method=extraction_method
        )
        save_result = memory.save(
            memory_type="project_note",
            title=title,
            content=chunk.text,
            metadata=metadata,
            importance=6,
            confidence=95,
            source="book_ingestion"
        )

        if save_result["success"]:
            created_count += 1
            status = "created"
        else:
            duplicate_count += 1
            status = "duplicate"

        items.append({
            "status": status,
            "memory_id": save_result.get("memory_id"),
            "title": title,
            "chapter": chunk.chapter,
            "section": chunk.section,
            "book_memory_kind": book_memory_kind
        })

    return {
        "success": True,
        "project": project_name,
        "book_title": book_title,
        "author": author or "",
        "source_file": str(original_source_file or source_file),
        "extracted_text_file": str(extracted_source_file or ""),
        "original_format": original_format or source_file.suffix.lower().lstrip("."),
        "extraction_method": extraction_method or "plain_text",
        "chunks_created": created_count,
        "duplicates_skipped": duplicate_count,
        "total_chunks": len(chunks),
        "items": items,
        "message": "Book ingestion complete"
    }
