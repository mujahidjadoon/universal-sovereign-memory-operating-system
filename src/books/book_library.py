import json
import re
from datetime import datetime
from pathlib import Path

from src.storage.database import get_connection


BOOK_UPLOAD_DIR = Path("sandbox/uploads/books")
SUPPORTED_UPLOAD_EXTENSIONS = {
    ".txt",
    ".md",
    ".pdf",
    ".docx"
}
INTERNET_URL_PREFIXES = (
    "http://",
    "https://"
)


def reject_internet_url(value):

    if not isinstance(value, str):
        return

    value_lower = value.strip().lower()

    for prefix in INTERNET_URL_PREFIXES:
        if value_lower.startswith(prefix):
            raise ValueError(
                "Online links are not supported yet. Download the "
                "book/document as .txt or .md first."
            )


def sanitize_filename(filename):

    reject_internet_url(filename)
    safe_name = Path(filename or "uploaded_book").name.strip()

    if not safe_name:
        safe_name = "uploaded_book"

    stem = Path(safe_name).stem
    suffix = Path(safe_name).suffix.lower()
    clean_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")

    if not clean_stem:
        clean_stem = "uploaded_book"

    return clean_stem + suffix


def validate_supported_book_file(filename):

    reject_internet_url(filename)
    suffix = Path(filename).suffix.lower()

    if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise ValueError("Only .txt, .md, .pdf, and .docx uploads are supported.")


def build_unique_upload_path(upload_dir, filename):

    upload_dir = Path(upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(filename)
    target_path = upload_dir / safe_name

    if not target_path.exists():
        return target_path

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    stem = target_path.stem
    suffix = target_path.suffix

    return upload_dir / f"{stem}_{timestamp}{suffix}"


def read_uploaded_file_bytes(uploaded_file):

    if hasattr(uploaded_file, "getbuffer"):
        return bytes(uploaded_file.getbuffer())

    if hasattr(uploaded_file, "read"):
        data = uploaded_file.read()

        if isinstance(data, str):
            return data.encode("utf-8")

        return bytes(data)

    raise ValueError("Uploaded file object must provide getbuffer() or read().")


def save_uploaded_book_file(uploaded_file, upload_dir=BOOK_UPLOAD_DIR):

    if isinstance(uploaded_file, str):
        reject_internet_url(uploaded_file)
        raise ValueError("A local uploaded file object is required.")

    if uploaded_file is None:
        raise ValueError("Choose a .txt or .md file first.")

    original_filename = getattr(uploaded_file, "name", "")
    validate_supported_book_file(original_filename)
    target_path = build_unique_upload_path(upload_dir, original_filename)
    file_bytes = read_uploaded_file_bytes(uploaded_file)

    target_path.write_bytes(file_bytes)

    return {
        "success": True,
        "original_filename": original_filename,
        "filename": target_path.name,
        "file_path": str(target_path)
    }


def parse_metadata(metadata_json):

    if not metadata_json:
        return {}

    try:
        return json.loads(metadata_json)
    except json.JSONDecodeError:
        return {}


def row_to_book(row):

    return {
        "title": row[0],
        "author": row[1] or "",
        "source_file": row[2] or "",
        "memory_count": row[3],
        "first_ingested_at": row[4],
        "latest_ingested_at": row[5]
    }


def list_books_with_json(project_name):

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT
        json_extract(metadata, '$.book_title') AS book_title,
        COALESCE(json_extract(metadata, '$.author'), '') AS author,
        COALESCE(json_extract(metadata, '$.source_file'), '') AS source_file,
        COUNT(*) AS memory_count,
        MIN(created_at) AS first_ingested_at,
        MAX(created_at) AS latest_ingested_at
    FROM memories
    WHERE status = 'active'
    AND memory_type = 'project_note'
    AND json_extract(metadata, '$.project') = ?
    AND json_extract(metadata, '$.content_kind') = 'book_knowledge'
    GROUP BY book_title, author, source_file
    ORDER BY latest_ingested_at DESC, book_title ASC
    """, (project_name,))
    rows = cursor.fetchall()
    conn.close()

    return [row_to_book(row) for row in rows if row[0]]


def list_books_without_json(project_name):

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT
        metadata,
        created_at
    FROM memories
    WHERE status = 'active'
    AND memory_type = 'project_note'
    AND metadata LIKE '%book_knowledge%'
    """)
    rows = cursor.fetchall()
    conn.close()
    grouped = {}

    for metadata_json, created_at in rows:
        metadata = parse_metadata(metadata_json)

        if metadata.get("project") != project_name:
            continue

        if metadata.get("content_kind") != "book_knowledge":
            continue

        key = (
            metadata.get("book_title"),
            metadata.get("author", ""),
            metadata.get("source_file", "")
        )

        if not key[0]:
            continue

        if key not in grouped:
            grouped[key] = {
                "title": key[0],
                "author": key[1],
                "source_file": key[2],
                "memory_count": 0,
                "first_ingested_at": created_at,
                "latest_ingested_at": created_at
            }

        grouped[key]["memory_count"] += 1

        if created_at < grouped[key]["first_ingested_at"]:
            grouped[key]["first_ingested_at"] = created_at

        if created_at > grouped[key]["latest_ingested_at"]:
            grouped[key]["latest_ingested_at"] = created_at

    books = list(grouped.values())
    books.sort(
        key=lambda book: (
            book["latest_ingested_at"] or "",
            book["title"]
        ),
        reverse=True
    )

    return books


def list_books(project_name):

    try:
        return list_books_with_json(project_name)
    except Exception:
        return list_books_without_json(project_name)


def get_book_titles(project_name):

    titles = []

    for book in list_books(project_name):
        if book["title"] not in titles:
            titles.append(book["title"])

    return sorted(titles)


def get_book_stats(project_name, title):

    matching_books = []

    for book in list_books(project_name):
        if book["title"] == title:
            matching_books.append(book)

    if not matching_books:
        return {
            "project": project_name,
            "title": title,
            "memory_count": 0,
            "source_files": [],
            "first_ingested_at": None,
            "latest_ingested_at": None
        }

    source_files = []
    memory_count = 0
    first_ingested_at = None
    latest_ingested_at = None

    for book in matching_books:
        memory_count += book["memory_count"]

        if book["source_file"] and book["source_file"] not in source_files:
            source_files.append(book["source_file"])

        if (
            first_ingested_at is None
            or book["first_ingested_at"] < first_ingested_at
        ):
            first_ingested_at = book["first_ingested_at"]

        if (
            latest_ingested_at is None
            or book["latest_ingested_at"] > latest_ingested_at
        ):
            latest_ingested_at = book["latest_ingested_at"]

    return {
        "project": project_name,
        "title": title,
        "memory_count": memory_count,
        "source_files": source_files,
        "first_ingested_at": first_ingested_at,
        "latest_ingested_at": latest_ingested_at
    }
