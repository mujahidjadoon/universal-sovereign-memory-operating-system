import contextlib
import io
import sys
import tempfile
import types
import unittest
from pathlib import Path

from src.books import book_benchmark
from src.books import book_validation
from src.books.book_benchmark import run_book_benchmark
from src.books.book_ingestion import (
    chunk_book_text,
    detect_book_heading,
    ingest_book_file,
)
from src.books.book_library import (
    get_book_stats,
    get_book_titles,
    list_books,
    save_uploaded_book_file,
    sanitize_filename,
)
from src.books.book_qa import ask_book
from src.books.book_validation import (
    add_validation_question,
    count_keyword_matches,
    create_validation_set,
    run_validation_set,
)
from src.books.document_extractors import (
    extract_text_from_docx,
    extract_text_from_document,
    extract_text_from_md,
    extract_text_from_pdf,
    extract_text_from_txt,
    prepare_document_for_ingestion,
)
from src.cli import usmos_cli
from src.memory import memory_engine
from src.memory.memory_engine import list_memories_by_project
from src.storage import database
from src.storage.schema import initialize_schema
from src.ui import dashboard


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "books"


class DummyUploadedFile:

    def __init__(self, name, content):
        self.name = name
        self.content = content

    def getbuffer(self):
        return self.content.encode("utf-8")


class BookKnowledgeTests(unittest.TestCase):

    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.original_snapshot_dir = memory_engine.SNAPSHOT_DIR
        self.original_current_project_file = memory_engine.CURRENT_PROJECT_FILE
        self.original_book_report_dir = book_benchmark.BOOK_BENCHMARK_REPORT_DIR
        self.original_validation_set_dir = book_validation.BOOK_VALIDATION_SET_DIR
        self.original_validation_report_dir = (
            book_validation.BOOK_VALIDATION_REPORT_DIR
        )
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

        database.DB_PATH = self.temp_path / "sandbox" / "data" / "usmos.db"
        memory_engine.SNAPSHOT_DIR = self.temp_path / "sandbox" / "snapshots"
        memory_engine.CURRENT_PROJECT_FILE = (
            self.temp_path / "sandbox" / "current_project.json"
        )
        book_benchmark.BOOK_BENCHMARK_REPORT_DIR = (
            self.temp_path / "sandbox" / "book_benchmark_reports"
        )
        book_validation.BOOK_VALIDATION_SET_DIR = (
            self.temp_path / "sandbox" / "book_validation_sets"
        )
        book_validation.BOOK_VALIDATION_REPORT_DIR = (
            self.temp_path / "sandbox" / "book_validation_reports"
        )

        initialize_schema()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        memory_engine.SNAPSHOT_DIR = self.original_snapshot_dir
        memory_engine.CURRENT_PROJECT_FILE = self.original_current_project_file
        book_benchmark.BOOK_BENCHMARK_REPORT_DIR = self.original_book_report_dir
        book_validation.BOOK_VALIDATION_SET_DIR = self.original_validation_set_dir
        book_validation.BOOK_VALIDATION_REPORT_DIR = (
            self.original_validation_report_dir
        )
        self.temp_dir.cleanup()

    def run_cli(self, argv):
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            exit_code = usmos_cli.main(argv)

        return exit_code, output.getvalue()

    def ingest_standard_book_set(self):
        ingest_book_file(
            file_path=FIXTURE_DIR / "book_a.md",
            project_name="BookTest",
            book_title="AI Memory Book"
        )
        ingest_book_file(
            file_path=FIXTURE_DIR / "book_b.md",
            project_name="BookTest",
            book_title="SQLite Book"
        )
        ingest_book_file(
            file_path=FIXTURE_DIR / "book_c.md",
            project_name="BookTest",
            book_title="Local First Book"
        )

    def evidence_book_titles(self, result):
        titles = []

        for evidence in result["evidence"]:
            if evidence["book_title"] not in titles:
                titles.append(evidence["book_title"])

        return titles

    def test_chapter_and_section_detection(self):
        chapter = detect_book_heading("# Chapter 1")
        plain_chapter = detect_book_heading("CHAPTER 2")
        section = detect_book_heading("## Section")
        colon_section = detect_book_heading("Important Ideas:")

        self.assertEqual(chapter["type"], "chapter")
        self.assertEqual(chapter["title"], "Chapter 1")
        self.assertEqual(plain_chapter["type"], "chapter")
        self.assertEqual(section["type"], "section")
        self.assertEqual(section["title"], "Section")
        self.assertEqual(colon_section["type"], "section")

    def test_upload_save_helper_sanitizes_filenames(self):
        uploaded_file = DummyUploadedFile(
            name="../My Unsafe Book!.md",
            content="# Chapter 1\nSafe local upload."
        )

        result = save_uploaded_book_file(
            uploaded_file=uploaded_file,
            upload_dir=self.temp_path / "uploads"
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["filename"], "My_Unsafe_Book.md")
        self.assertTrue(Path(result["file_path"]).exists())
        self.assertEqual(
            sanitize_filename("../My Unsafe Book!.md"),
            "My_Unsafe_Book.md"
        )

    def test_upload_save_helper_avoids_overwrite(self):
        upload_dir = self.temp_path / "uploads"
        first = save_uploaded_book_file(
            uploaded_file=DummyUploadedFile("same.md", "first"),
            upload_dir=upload_dir
        )
        second = save_uploaded_book_file(
            uploaded_file=DummyUploadedFile("same.md", "second"),
            upload_dir=upload_dir
        )

        self.assertNotEqual(first["file_path"], second["file_path"])
        self.assertEqual(Path(first["file_path"]).read_text(), "first")
        self.assertEqual(Path(second["file_path"]).read_text(), "second")

    def test_unsupported_file_extension_is_rejected(self):
        with self.assertRaises(ValueError):
            save_uploaded_book_file(
                uploaded_file=DummyUploadedFile("book.epub", "epub"),
                upload_dir=self.temp_path / "uploads"
            )

    def test_no_internet_url_support(self):
        with self.assertRaises(ValueError):
            save_uploaded_book_file("https://example.com/book.md")

    def test_extract_txt(self):
        text_file = self.temp_path / "sample.txt"
        text_file.write_text("Plain text extraction works.", encoding="utf-8")

        result = extract_text_from_txt(text_file)

        self.assertTrue(result["success"])
        self.assertEqual(result["format"], "txt")
        self.assertIn("Plain text extraction works.", result["text"])
        self.assertEqual(result["word_count"], 4)

    def test_extract_md(self):
        md_file = self.temp_path / "sample.md"
        md_file.write_text("# Title\n\nMarkdown extraction works.", encoding="utf-8")

        result = extract_text_from_md(md_file)

        self.assertTrue(result["success"])
        self.assertEqual(result["format"], "md")
        self.assertIn("Markdown extraction works.", result["text"])

    def test_extract_pdf_with_simple_text(self):
        pdf_file = self.temp_path / "sample.pdf"
        pdf_file.write_bytes(b"%PDF fake")

        class FakePage:

            def extract_text(self):
                return "PDF extraction works with local text."

        class FakeReader:

            def __init__(self, file):
                self.pages = [FakePage()]

        original_pypdf = sys.modules.get("pypdf")
        sys.modules["pypdf"] = types.SimpleNamespace(PdfReader=FakeReader)

        try:
            result = extract_text_from_pdf(pdf_file)
        finally:
            if original_pypdf is None:
                del sys.modules["pypdf"]
            else:
                sys.modules["pypdf"] = original_pypdf

        self.assertTrue(result["success"])
        self.assertEqual(result["format"], "pdf")
        self.assertEqual(result["page_count"], 1)
        self.assertIn("PDF extraction works", result["text"])

    def test_empty_pdf_returns_scanned_warning(self):
        pdf_file = self.temp_path / "empty.pdf"
        pdf_file.write_bytes(b"%PDF fake")

        class EmptyPage:

            def extract_text(self):
                return ""

        class FakeReader:

            def __init__(self, file):
                self.pages = [EmptyPage()]

        original_pypdf = sys.modules.get("pypdf")
        sys.modules["pypdf"] = types.SimpleNamespace(PdfReader=FakeReader)

        try:
            result = extract_text_from_pdf(pdf_file)
        finally:
            if original_pypdf is None:
                del sys.modules["pypdf"]
            else:
                sys.modules["pypdf"] = original_pypdf

        self.assertFalse(result["success"])
        self.assertIn("OCR is not supported yet", result["error"])

    def test_extract_docx_with_paragraphs_and_tables(self):
        docx_file = self.temp_path / "sample.docx"
        docx_file.write_bytes(b"docx fake")

        fake_paragraphs = [
            types.SimpleNamespace(text="DOCX paragraph extraction works.")
        ]
        fake_table = types.SimpleNamespace(rows=[
            types.SimpleNamespace(cells=[
                types.SimpleNamespace(text="Table cell one"),
                types.SimpleNamespace(text="Table cell two")
            ])
        ])
        fake_document = types.SimpleNamespace(
            paragraphs=fake_paragraphs,
            tables=[fake_table]
        )

        def fake_document_loader(path):
            return fake_document

        original_docx = sys.modules.get("docx")
        sys.modules["docx"] = types.SimpleNamespace(Document=fake_document_loader)

        try:
            result = extract_text_from_docx(docx_file)
        finally:
            if original_docx is None:
                del sys.modules["docx"]
            else:
                sys.modules["docx"] = original_docx

        self.assertTrue(result["success"])
        self.assertEqual(result["format"], "docx")
        self.assertEqual(result["paragraph_count"], 1)
        self.assertIn("DOCX paragraph extraction works.", result["text"])
        self.assertIn("Table cell one | Table cell two", result["text"])

    def test_chunking_works(self):
        text = (
            "# Chapter 1\n\n"
            "## Small Section\n\n"
            "one two three four five six seven eight nine ten.\n\n"
            "eleven twelve thirteen fourteen fifteen sixteen seventeen."
        )

        chunks = chunk_book_text(text, chunk_words=8, overlap_words=2)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.text.strip() for chunk in chunks))
        self.assertEqual(chunks[0].chapter, "Chapter 1")
        self.assertEqual(chunks[0].section, "Small Section")

    def test_book_ingest_creates_project_note_memories_with_metadata(self):
        result = ingest_book_file(
            file_path=FIXTURE_DIR / "book_a.md",
            project_name="BookTest",
            book_title="Book A",
            author="Author A"
        )
        memories = list_memories_by_project("BookTest")

        self.assertTrue(result["success"])
        self.assertGreater(result["chunks_created"], 0)
        self.assertEqual(memories[0]["memory_type"], "project_note")
        self.assertEqual(memories[0]["metadata"]["book_title"], "Book A")
        self.assertEqual(memories[0]["metadata"]["author"], "Author A")
        self.assertEqual(memories[0]["metadata"]["source"], "book_ingestion")
        self.assertEqual(memories[0]["metadata"]["content_kind"], "book_knowledge")

    def test_pdf_metadata_includes_original_format_and_extracted_text_file(self):
        extracted_file = self.temp_path / "extracted_pdf.txt"
        original_file = self.temp_path / "sample.pdf"
        extracted_file.write_text(
            "PDF Book Topic. This PDF is about local document memory.",
            encoding="utf-8"
        )
        original_file.write_bytes(b"%PDF fake")

        result = ingest_book_file(
            file_path=extracted_file,
            project_name="PdfMetaTest",
            book_title="PDF Metadata Book",
            original_source_file=original_file,
            extracted_source_file=extracted_file,
            original_format="pdf",
            extraction_method="pypdf"
        )
        memories = list_memories_by_project("PdfMetaTest")
        metadata = memories[0]["metadata"]

        self.assertTrue(result["success"])
        self.assertEqual(metadata["source_file"], str(original_file))
        self.assertEqual(metadata["extracted_text_file"], str(extracted_file))
        self.assertEqual(metadata["original_format"], "pdf")
        self.assertEqual(metadata["extraction_method"], "pypdf")

    def test_prepare_document_for_ingestion_saves_pdf_extracted_text(self):
        pdf_file = self.temp_path / "sample.pdf"
        pdf_file.write_bytes(b"%PDF fake")

        class FakePage:

            def extract_text(self):
                return "Prepared PDF extraction works."

        class FakeReader:

            def __init__(self, file):
                self.pages = [FakePage()]

        original_pypdf = sys.modules.get("pypdf")
        sys.modules["pypdf"] = types.SimpleNamespace(PdfReader=FakeReader)

        try:
            result = prepare_document_for_ingestion(
                path=pdf_file,
                extracted_text_dir=self.temp_path / "extracted"
            )
        finally:
            if original_pypdf is None:
                del sys.modules["pypdf"]
            else:
                sys.modules["pypdf"] = original_pypdf

        self.assertTrue(result["success"])
        self.assertEqual(result["original_format"], "pdf")
        self.assertEqual(result["extraction_method"], "pypdf")
        self.assertTrue(Path(result["extracted_text_file"]).exists())
        self.assertIn(
            "Prepared PDF extraction works.",
            Path(result["extracted_text_file"]).read_text()
        )

    def test_library_listing_groups_books_correctly(self):
        self.ingest_standard_book_set()
        books = list_books("BookTest")
        titles = []

        for book in books:
            titles.append(book["title"])

        self.assertEqual(
            set(titles),
            {"AI Memory Book", "SQLite Book", "Local First Book"}
        )
        self.assertTrue(all(book["memory_count"] >= 1 for book in books))

    def test_library_stats_count_memories_by_book(self):
        self.ingest_standard_book_set()
        stats = get_book_stats("BookTest", "SQLite Book")
        titles = get_book_titles("BookTest")

        self.assertEqual(stats["title"], "SQLite Book")
        self.assertGreaterEqual(stats["memory_count"], 1)
        self.assertTrue(stats["source_files"])
        self.assertIn("SQLite Book", titles)

    def test_duplicate_book_ingest_skips_duplicates(self):
        first = ingest_book_file(
            file_path=FIXTURE_DIR / "book_a.md",
            project_name="BookTest",
            book_title="Book A"
        )
        second = ingest_book_file(
            file_path=FIXTURE_DIR / "book_a.md",
            project_name="BookTest",
            book_title="Book A"
        )

        self.assertGreater(first["chunks_created"], 0)
        self.assertEqual(second["chunks_created"], 0)
        self.assertEqual(second["duplicates_skipped"], second["total_chunks"])

    def test_book_ask_returns_evidence_for_known_content(self):
        ingest_book_file(
            file_path=FIXTURE_DIR / "book_a.md",
            project_name="BookTest",
            book_title="Book A"
        )

        result = ask_book(
            question="What does Book A say about context windows?",
            project_name="BookTest",
            book_title="Book A"
        )

        self.assertTrue(result["success"])
        self.assertIn("Context windows limit", result["answer"])
        self.assertEqual(result["evidence"][0]["book_title"], "Book A")
        self.assertTrue(result["memory_ids"])

    def test_unknown_book_question_returns_no_evidence(self):
        ingest_book_file(
            file_path=FIXTURE_DIR / "book_a.md",
            project_name="BookTest",
            book_title="Book A"
        )

        result = ask_book(
            question="Do these books mention Kubernetes?",
            project_name="BookTest",
            book_title="Book A"
        )

        self.assertFalse(result["success"])
        self.assertEqual(
            result["answer"],
            "I do not have evidence for that in the selected book."
        )
        self.assertEqual(result["memory_ids"], [])

    def test_cross_book_search_identifies_correct_book(self):
        self.ingest_standard_book_set()

        result = ask_book(
            question="Which book discusses SQLite indexes?",
            project_name="BookTest"
        )

        self.assertTrue(result["success"])
        self.assertIn("SQLite Book", result["answer"])
        self.assertEqual(self.evidence_book_titles(result), ["SQLite Book"])

    def test_sqlite_indexes_question_returns_only_sqlite_book(self):
        self.ingest_standard_book_set()

        result = ask_book(
            question="Which book discusses SQLite indexes?",
            project_name="BookTest"
        )

        self.assertTrue(result["success"])
        self.assertEqual(self.evidence_book_titles(result), ["SQLite Book"])
        self.assertTrue(
            all("SQLite" in evidence["excerpt"] for evidence in result["evidence"])
        )

    def test_user_controlled_local_data_returns_only_local_first_book(self):
        self.ingest_standard_book_set()

        result = ask_book(
            question="Which book talks about user-controlled local data?",
            project_name="BookTest"
        )

        self.assertTrue(result["success"])
        self.assertEqual(self.evidence_book_titles(result), ["Local First Book"])
        self.assertIn("user data under user control", result["answer"])

    def test_context_window_title_question_returns_ai_memory_book_only(self):
        self.ingest_standard_book_set()

        result = ask_book(
            question="What does the AI Memory Book say about context windows?",
            project_name="BookTest",
            book_title="AI Memory Book"
        )

        self.assertTrue(result["success"])
        self.assertEqual(self.evidence_book_titles(result), ["AI Memory Book"])
        self.assertIn("Context windows limit", result["answer"])

    def test_kubernetes_cross_book_unknown_returns_no_evidence(self):
        self.ingest_standard_book_set()

        result = ask_book(
            question="Do these books mention Kubernetes?",
            project_name="BookTest"
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["memory_ids"], [])
        self.assertEqual(result["evidence"], [])

    def test_shared_concept_returns_multiple_matching_books(self):
        first_book = self.temp_path / "shared_one.md"
        second_book = self.temp_path / "shared_two.md"
        first_book.write_text(
            "# Chapter 1\n\n"
            "Durable memory evidence keeps validation local.",
            encoding="utf-8"
        )
        second_book.write_text(
            "# Chapter 1\n\n"
            "Durable memory evidence supports local validation across documents.",
            encoding="utf-8"
        )
        ingest_book_file(
            file_path=first_book,
            project_name="SharedBookTest",
            book_title="Shared One"
        )
        ingest_book_file(
            file_path=second_book,
            project_name="SharedBookTest",
            book_title="Shared Two"
        )

        result = ask_book(
            question="Which books discuss durable memory evidence?",
            project_name="SharedBookTest"
        )

        self.assertTrue(result["success"])
        self.assertEqual(
            set(self.evidence_book_titles(result)),
            {"Shared One", "Shared Two"}
        )

    def test_selected_wrong_title_returns_no_evidence(self):
        self.ingest_standard_book_set()

        result = ask_book(
            question="Which book discusses SQLite indexes?",
            project_name="BookTest",
            book_title="AI Memory Book"
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["memory_ids"], [])

    def test_evidence_excerpts_only_include_filtered_candidates(self):
        self.ingest_standard_book_set()

        result = ask_book(
            question="Which book discusses SQLite indexes?",
            project_name="BookTest"
        )
        excerpts = " ".join(evidence["excerpt"] for evidence in result["evidence"])

        self.assertTrue(result["success"])
        self.assertIn("SQLite", excerpts)
        self.assertNotIn("Local-first systems", excerpts)
        self.assertNotIn("Context windows limit", excerpts)

    def test_structure_question_prefers_explanatory_nephron_chunk(self):
        book_file = self.temp_path / "nephron.md"
        book_file.write_text(
            "# Chapter 1\n\n"
            "## LONG QUESTIONS\n\n"
            "Explain the detailed structure of nephron.\n\n"
            "## Nephron Structure\n\n"
            "The nephron consists of Bowman's capsule, glomerulus, "
            "proximal convoluted tubule, loop of Henle, "
            "distal convoluted tubule, and collecting duct.",
            encoding="utf-8"
        )
        ingest_book_file(
            file_path=book_file,
            project_name="BiologyBookTest",
            book_title="Biology Book"
        )

        result = ask_book(
            question="Structure of Nephron?",
            project_name="BiologyBookTest",
            book_title="Biology Book"
        )

        self.assertTrue(result["success"])
        self.assertIn("Bowman's capsule", result["evidence"][0]["excerpt"])
        self.assertIn("consists of", result["evidence"][0]["excerpt"])
        self.assertEqual(result["evidence"][0]["section"], "Nephron Structure")
        self.assertTrue(
            all(
                evidence["section"] != "LONG QUESTIONS"
                for evidence in result["evidence"]
            )
        )

    def test_question_prompt_chunk_is_excluded_from_evidence(self):
        book_file = self.temp_path / "exercise_vs_answer.md"
        book_file.write_text(
            "# Chapter 1\n\n"
            "## Exercises\n\n"
            "2. Explain the detailed structure of nephron.\n\n"
            "## Answer\n\n"
            "A nephron is composed of Bowman's capsule, glomerulus, "
            "proximal convoluted tubule, loop of Henle, "
            "distal convoluted tubule, and collecting duct.",
            encoding="utf-8"
        )
        ingest_book_file(
            file_path=book_file,
            project_name="ExerciseBookTest",
            book_title="Exercise Book"
        )

        result = ask_book(
            question="What is the structure of the nephron?",
            project_name="ExerciseBookTest",
            book_title="Exercise Book"
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["evidence"][0]["section"], "Answer")
        self.assertTrue(
            all(evidence["section"] != "Exercises" for evidence in result["evidence"])
        )

    def test_only_exercise_prompt_chunk_returns_no_book_evidence(self):
        book_file = self.temp_path / "exercise_only.md"
        book_file.write_text(
            "# Chapter 1\n\n"
            "Explain the detailed structure of nephron.",
            encoding="utf-8"
        )
        ingest_book_file(
            file_path=book_file,
            project_name="ExerciseOnlyBookTest",
            book_title="Exercise Only Book"
        )

        result = ask_book(
            question="Structure of Nephron?",
            project_name="ExerciseOnlyBookTest",
            book_title="Exercise Only Book"
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["memory_ids"], [])
        self.assertEqual(result["evidence"], [])

    def test_book_evidence_exposes_relevance_score(self):
        self.ingest_standard_book_set()

        result = ask_book(
            question="Which book discusses SQLite indexes?",
            project_name="BookTest"
        )

        self.assertTrue(result["success"])
        self.assertIsNotNone(result["evidence"][0]["relevance_score"])

    def test_validation_set_create_and_add_question(self):
        dataset = create_validation_set(
            project_name="BookTest",
            dataset_name="PrecisionTest"
        )
        added = add_validation_question(
            project_name="BookTest",
            dataset_name="PrecisionTest",
            question="Which book discusses SQLite indexes?",
            expected_book_title="SQLite Book",
            expected_keywords="SQLite,indexes",
            should_have_evidence=True
        )

        self.assertTrue(dataset["success"])
        self.assertTrue(Path(dataset["path"]).exists())
        self.assertEqual(added["question"]["question_id"], 1)
        self.assertEqual(
            added["question"]["expected_keywords"],
            ["SQLite", "indexes"]
        )

    def test_validation_run_with_known_evidence_and_report_saved(self):
        self.ingest_standard_book_set()
        create_validation_set(
            project_name="BookTest",
            dataset_name="PrecisionRun"
        )
        add_validation_question(
            project_name="BookTest",
            dataset_name="PrecisionRun",
            question="Which book discusses SQLite indexes?",
            expected_book_title="SQLite Book",
            expected_keywords="SQLite,indexes",
            should_have_evidence=True
        )

        report = run_validation_set(
            project_name="BookTest",
            dataset_name="PrecisionRun"
        )

        self.assertTrue(report["success"])
        self.assertEqual(report["metrics"]["total_questions"], 1)
        self.assertEqual(report["metrics"]["passed"], 1)
        self.assertEqual(report["results"][0]["expected_book_matched"], True)
        self.assertEqual(report["results"][0]["keyword_match_count"], 2)
        self.assertTrue(Path(report["report_file"]).exists())

    def test_validation_no_evidence_question_passes_when_expected(self):
        self.ingest_standard_book_set()
        create_validation_set(
            project_name="BookTest",
            dataset_name="NoEvidenceRun"
        )
        add_validation_question(
            project_name="BookTest",
            dataset_name="NoEvidenceRun",
            question="Do these books mention Kubernetes?",
            should_have_evidence=False
        )

        report = run_validation_set(
            project_name="BookTest",
            dataset_name="NoEvidenceRun"
        )

        self.assertEqual(report["metrics"]["passed"], 1)
        self.assertEqual(report["metrics"]["no_evidence_accuracy"], 1.0)
        self.assertFalse(report["results"][0]["answer_found"])

    def test_validation_expected_book_matching_works(self):
        self.ingest_standard_book_set()
        create_validation_set(
            project_name="BookTest",
            dataset_name="BookMatchRun"
        )
        add_validation_question(
            project_name="BookTest",
            dataset_name="BookMatchRun",
            question="Which book talks about user-controlled local data?",
            expected_book_title="Local First Book",
            expected_keywords="user-controlled,local data",
            should_have_evidence=True
        )

        report = run_validation_set(
            project_name="BookTest",
            dataset_name="BookMatchRun"
        )

        self.assertTrue(report["results"][0]["passed"])
        self.assertEqual(report["results"][0]["expected_book_matched"], True)
        self.assertEqual(report["results"][0]["keyword_match_count"], 2)

    def test_validation_keywords_match_full_evidence_content(self):
        book_file = self.temp_path / "long_nephron.md"
        filler = "background " * 90
        book_file.write_text(
            "# Chapter 1\n\n"
            "## Nephron Structure\n\n"
            "Structure of Nephron. "
            + filler
            + "The nephron includes Bowman’s capsule, glomerulus, "
            "proximal convoluted tubule, loop of Henle, "
            "distal convoluted tubule, and collecting duct.",
            encoding="utf-8"
        )
        ingest_book_file(
            file_path=book_file,
            project_name="BiologyValidationTest",
            book_title="Biology Validation Book"
        )
        create_validation_set(
            project_name="BiologyValidationTest",
            dataset_name="NephronValidation"
        )
        add_validation_question(
            project_name="BiologyValidationTest",
            dataset_name="NephronValidation",
            question="Structure of Nephron?",
            expected_book_title="Biology Validation Book",
            expected_keywords="Bowman's capsule,Loop of Henle",
            should_have_evidence=True
        )

        report = run_validation_set(
            project_name="BiologyValidationTest",
            dataset_name="NephronValidation"
        )
        result = report["results"][0]

        self.assertTrue(result["passed"])
        self.assertEqual(result["keyword_match_count"], 2)
        self.assertEqual(result["missing_keywords"], [])

    def test_validation_no_evidence_ignores_expected_book_and_keywords(self):
        self.ingest_standard_book_set()
        create_validation_set(
            project_name="BookTest",
            dataset_name="NoEvidenceWithExpectations"
        )
        add_validation_question(
            project_name="BookTest",
            dataset_name="NoEvidenceWithExpectations",
            question="Do these books mention Kubernetes?",
            expected_book_title="SQLite Book",
            expected_keywords="SQLite,indexes",
            should_have_evidence=False
        )

        report = run_validation_set(
            project_name="BookTest",
            dataset_name="NoEvidenceWithExpectations"
        )
        result = report["results"][0]

        self.assertTrue(result["passed"])
        self.assertEqual(result["expected_book_matched"], None)
        self.assertEqual(result["keyword_match_count"], 0)
        self.assertEqual(result["reason"], "no evidence correctly returned")

    def test_validation_keyword_normalization_handles_curly_apostrophes(self):
        result = {
            "answer": "Short answer only.",
            "evidence": [
                {
                    "excerpt": "The nephron includes Bowman’s capsule.",
                    "full_content": ""
                }
            ]
        }

        matched, missing = count_keyword_matches(
            result=result,
            expected_keywords=["Bowman's capsule"]
        )

        self.assertEqual(matched, ["Bowman's capsule"])
        self.assertEqual(missing, [])

    def test_cli_book_validation_workflow(self):
        self.ingest_standard_book_set()

        exit_code, output = self.run_cli([
            "book-validation-create",
            "--project",
            "BookTest",
            "--name",
            "CliValidation"
        ])

        self.assertEqual(exit_code, 0)
        self.assertIn("Book validation set ready:", output)

        exit_code, output = self.run_cli([
            "book-validation-add-question",
            "--project",
            "BookTest",
            "--name",
            "CliValidation",
            "--question",
            "Which book discusses SQLite indexes?",
            "--expected-book",
            "SQLite Book",
            "--keywords",
            "SQLite,indexes"
        ])

        self.assertEqual(exit_code, 0)
        self.assertIn("Validation question added:", output)

        exit_code, output = self.run_cli([
            "book-validation-run",
            "--project",
            "BookTest",
            "--name",
            "CliValidation"
        ])

        self.assertEqual(exit_code, 0)
        self.assertIn("Book validation complete:", output)
        self.assertIn("Passed: 1", output)
        self.assertIn("Report file:", output)

    def test_cli_book_ingest_and_book_ask(self):
        exit_code, output = self.run_cli([
            "book-ingest",
            str(FIXTURE_DIR / "book_a.md"),
            "--project",
            "BookTest",
            "--title",
            "Book A",
            "--author",
            "Author A"
        ])

        self.assertEqual(exit_code, 0)
        self.assertIn("Book ingestion complete:", output)
        self.assertIn("Book title: Book A", output)

        exit_code, output = self.run_cli([
            "book-ask",
            "What does Book A say about context windows?",
            "--project",
            "BookTest",
            "--title",
            "Book A"
        ])

        self.assertEqual(exit_code, 0)
        self.assertIn("Book answer:", output)
        self.assertIn("Context windows limit", output)
        self.assertIn("Evidence excerpts:", output)
        self.assertIn("Evidence score:", output)

    def test_cli_book_ingest_accepts_pdf_and_docx(self):
        original_prepare = usmos_cli.prepare_document_for_ingestion
        pdf_text = self.temp_path / "pdf_extracted.txt"
        docx_text = self.temp_path / "docx_extracted.txt"
        pdf_original = self.temp_path / "sample.pdf"
        docx_original = self.temp_path / "sample.docx"
        pdf_text.write_text("PDF CLI book is about local PDF memory.", encoding="utf-8")
        docx_text.write_text("DOCX CLI book is about local Word memory.", encoding="utf-8")
        pdf_original.write_bytes(b"%PDF fake")
        docx_original.write_bytes(b"docx fake")

        def fake_prepare(path):
            suffix = Path(path).suffix.lower()

            if suffix == ".pdf":
                return {
                    "success": True,
                    "ingest_file_path": str(pdf_text),
                    "original_source_file": str(pdf_original),
                    "extracted_text_file": str(pdf_text),
                    "original_format": "pdf",
                    "extraction_method": "pypdf",
                    "extraction": {
                        "format": "pdf",
                        "page_count": 1,
                        "paragraph_count": None,
                        "word_count": 8
                    },
                    "error": None
                }

            return {
                "success": True,
                "ingest_file_path": str(docx_text),
                "original_source_file": str(docx_original),
                "extracted_text_file": str(docx_text),
                "original_format": "docx",
                "extraction_method": "python-docx",
                "extraction": {
                    "format": "docx",
                    "page_count": None,
                    "paragraph_count": 1,
                    "word_count": 8
                },
                "error": None
            }

        usmos_cli.prepare_document_for_ingestion = fake_prepare

        try:
            pdf_exit, pdf_output = self.run_cli([
                "book-ingest",
                str(pdf_original),
                "--project",
                "CliDocTest",
                "--title",
                "PDF CLI Book"
            ])
            docx_exit, docx_output = self.run_cli([
                "book-ingest",
                str(docx_original),
                "--project",
                "CliDocTest",
                "--title",
                "DOCX CLI Book"
            ])
        finally:
            usmos_cli.prepare_document_for_ingestion = original_prepare

        self.assertEqual(pdf_exit, 0)
        self.assertEqual(docx_exit, 0)
        self.assertIn("Format: pdf", pdf_output)
        self.assertIn("Format: docx", docx_output)

    def test_book_benchmark_writes_report(self):
        ingest_book_file(
            file_path=FIXTURE_DIR / "book_a.md",
            project_name="BookTest",
            book_title="Book A"
        )

        result = run_book_benchmark(
            project_name="BookTest",
            questions=[
                "What does Book A say about context windows?",
                "Do these books mention Kubernetes?"
            ]
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["questions_asked"], 2)
        self.assertTrue(Path(result["report_file"]).exists())

    def test_dashboard_book_tab_import_does_not_break(self):
        self.assertTrue(callable(dashboard.render_book_knowledge))
        self.assertTrue(callable(dashboard.render_knowledge_library))
