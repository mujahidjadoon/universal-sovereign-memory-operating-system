import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import streamlit as st
except ModuleNotFoundError:
    st = None

from src.books.book_ingestion import ingest_book_file
from src.books.book_library import (
    get_book_titles,
    list_books,
    save_uploaded_book_file,
)
from src.books.book_qa import ask_book
from src.books.book_validation import (
    add_validation_question,
    create_sample_validation_set,
    create_validation_set,
    run_validation_set,
)
from src.books.document_extractors import prepare_document_for_ingestion
from src.memory.memory_engine import get_current_project
from src.storage.schema import initialize_schema


SUPPORTED_UPLOAD_TYPES = [
    "txt",
    "md",
    "pdf",
    "docx"
]
COMING_SOON_TEXT = "Online links and OCR for scanned PDFs: coming soon"
NO_EVIDENCE_LIBRARY_MESSAGE = (
    "I do not have evidence for that in the selected book/library."
)


def require_streamlit():

    if st is not None:
        return

    raise RuntimeError(
        "Streamlit is not installed. Install dependencies with: "
        "python3 -m pip install -r requirements.txt"
    )


def apply_light_theme():

    st.set_page_config(
        page_title="USMOS Knowledge Library",
        page_icon="USMOS",
        layout="wide"
    )
    st.markdown(
        """
        <style>
        html,
        body,
        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stMainBlockContainer"] {
            background: #ffffff !important;
            color: #172033 !important;
        }
        .stMarkdown,
        .stMarkdown p,
        label,
        h1,
        h2,
        h3 {
            color: #172033 !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )


def parse_tags(tags_text):

    tags = []

    for tag in tags_text.split(","):
        clean_tag = tag.strip()

        if clean_tag:
            tags.append(clean_tag)

    return tags


def render_evidence(result):

    st.subheader("Evidence")

    if not result["evidence"]:
        st.info(NO_EVIDENCE_LIBRARY_MESSAGE)
        return

    st.write("Memory IDs:")

    if result["memory_ids"]:
        st.write(", ".join(f"#{memory_id}" for memory_id in result["memory_ids"]))
    else:
        st.write("None")

    st.write("Trust scores:")

    if result["trust_scores"]:
        for memory_id, trust_score in result["trust_scores"].items():
            st.write(f"Memory #{memory_id}: {trust_score}")
    else:
        st.write("None")

    for evidence in result["evidence"]:
        with st.expander(
            f"{evidence['book_title']} - Memory #{evidence['memory_id']}",
            expanded=False
        ):
            st.write(evidence["excerpt"])
            st.write(f"Book title: {evidence['book_title']}")
            st.write(f"Chapter: {evidence['chapter']}")
            st.write(f"Section: {evidence['section']}")
            st.write(f"Evidence score: {evidence.get('relevance_score')}")
            st.write(f"Trust score: {evidence['trust_score']}")


def render_answer(result):

    st.subheader("Answer")
    st.write(result["answer"])
    render_evidence(result)


def render_upload_section():

    st.header("Upload Book / Document")
    st.write("Supported: .txt, .md, .pdf, .docx")
    st.caption(COMING_SOON_TEXT)

    uploaded_file = st.file_uploader(
        "Choose .txt, .md, .pdf, or .docx file",
        type=SUPPORTED_UPLOAD_TYPES
    )
    default_title = ""

    if uploaded_file is not None:
        default_title = Path(uploaded_file.name).stem

    project_name = st.text_input(
        "Project name",
        value=get_current_project()
    )
    book_title = st.text_input(
        "Book title",
        value=default_title
    )
    author = st.text_input(
        "Author",
        value=""
    )
    tags_text = st.text_input(
        "Tags",
        value=""
    )

    if st.button("Ingest Book", type="primary"):
        if uploaded_file is None:
            st.warning("Choose a .txt or .md file first.")
            return project_name

        if not project_name.strip() or not book_title.strip():
            st.warning("Project name and book title are required.")
            return project_name

        try:
            saved_file = save_uploaded_book_file(uploaded_file)
            prepared_document = prepare_document_for_ingestion(saved_file["file_path"])

            if not prepared_document["success"]:
                st.warning(prepared_document["error"])
                return project_name

            extraction = prepared_document["extraction"]
            st.info(
                "Extraction complete: "
                f"format={extraction['format']}, "
                f"pages={extraction['page_count']}, "
                f"paragraphs={extraction['paragraph_count']}, "
                f"words={extraction['word_count']}"
            )

            if prepared_document["extracted_text_file"]:
                st.caption(
                    "Extracted text file: "
                    + prepared_document["extracted_text_file"]
                )

            result = ingest_book_file(
                file_path=prepared_document["ingest_file_path"],
                project_name=project_name.strip(),
                book_title=book_title.strip(),
                author=author.strip(),
                tags=parse_tags(tags_text),
                original_source_file=prepared_document["original_source_file"],
                extracted_source_file=prepared_document["extracted_text_file"],
                original_format=prepared_document["original_format"],
                extraction_method=prepared_document["extraction_method"]
            )
        except (OSError, ValueError) as error:
            st.error(str(error))
            return project_name

        st.success("Book ingestion complete.")
        st.write(f"Chunks created: {result['chunks_created']}")
        st.write(f"Duplicates skipped: {result['duplicates_skipped']}")
        st.write(f"Project: {result['project']}")
        st.write(f"Title: {result['book_title']}")
        st.write(f"Source path: {result['source_file']}")

    return project_name


def render_library(project_name):

    st.header("Library")
    books = list_books(project_name)

    if not books:
        st.info("No ingested books found for this project yet.")
        return []

    table_rows = []

    for book in books:
        table_rows.append({
            "title": book["title"],
            "author": book["author"],
            "source_file": book["source_file"],
            "memory_count": book["memory_count"]
        })

    st.dataframe(
        table_rows,
        hide_index=True,
        use_container_width=True
    )

    return books


def render_ask_section(project_name):

    st.header("Ask")
    titles = get_book_titles(project_name)

    if titles:
        selected_title = st.selectbox(
            "Select book",
            titles
        )
    else:
        selected_title = None
        st.info("Ingest a book before asking a selected-book question.")

    selected_question = st.text_input(
        "Question for selected book",
        value="What does this book say about context windows?"
    )

    if st.button("Ask Selected Book"):
        if not selected_title:
            st.warning("Select an ingested book first.")
        else:
            result = ask_book(
                question=selected_question,
                project_name=project_name,
                book_title=selected_title
            )
            render_answer(result)

    all_books_question = st.text_input(
        "Question across all books",
        value="Which book discusses local-first architecture?"
    )

    if st.button("Ask All Books"):
        result = ask_book(
            question=all_books_question,
            project_name=project_name
        )
        render_answer(result)


def render_validation_section(project_name):

    st.header("Validation / Testing")
    st.write("Create a local question set and test book answers against evidence.")

    dataset_name = st.text_input(
        "Validation dataset name",
        value="BookValidation"
    )

    col_create, col_sample = st.columns(2)

    with col_create:
        if st.button("Create Validation Set"):
            result = create_validation_set(
                project_name=project_name,
                dataset_name=dataset_name
            )
            st.success("Validation set ready.")
            st.write(f"File: {result['path']}")

    with col_sample:
        if st.button("Create Sample Questions"):
            result = create_sample_validation_set(
                project_name=project_name,
                dataset_name=dataset_name
            )
            st.success("Sample validation questions created.")
            st.write(f"Questions: {len(result['questions'])}")

    st.subheader("Add Test Question")
    validation_question = st.text_input(
        "Validation question",
        value="Structure of Nephron?"
    )
    expected_book = st.text_input(
        "Expected book title",
        value=""
    )
    expected_keywords = st.text_input(
        "Expected keywords",
        value="",
        help="Comma-separated keywords expected in answer/evidence"
    )
    should_have_evidence = st.checkbox(
        "Should have evidence",
        value=True
    )

    if st.button("Add Validation Question"):
        try:
            result = add_validation_question(
                project_name=project_name,
                dataset_name=dataset_name,
                question=validation_question,
                expected_book_title=expected_book,
                expected_keywords=expected_keywords,
                should_have_evidence=should_have_evidence
            )
        except FileNotFoundError:
            st.warning("Create the validation set first.")
            return

        st.success("Validation question added.")
        st.write(f"Question ID: {result['question']['question_id']}")

    st.subheader("Run Validation")

    if st.button("Run Validation"):
        try:
            report = run_validation_set(
                project_name=project_name,
                dataset_name=dataset_name
            )
        except FileNotFoundError:
            st.warning("Create the validation set first.")
            return

        metrics = report["metrics"]
        st.success("Validation complete.")
        st.write(f"Report path: {report['report_file']}")
        st.write(f"Passed: {metrics['passed']}")
        st.write(f"Failed: {metrics['failed']}")
        st.write(f"Precision estimate: {metrics['precision_estimate']}")

        table_rows = []

        for item in report["results"]:
            table_rows.append({
                "status": "PASS" if item["passed"] else "FAIL",
                "question": item["question"],
                "answer_found": item["answer_found"],
                "expected_book_matched": item["expected_book_matched"],
                "keyword_match_count": item["keyword_match_count"],
                "evidence_count": item["evidence_count"],
                "top_memory_id": item["top_memory_id"],
                "reason": item["reason"]
            })

        st.dataframe(
            table_rows,
            hide_index=True,
            use_container_width=True
        )


def render_library_app():

    require_streamlit()
    initialize_schema()
    apply_light_theme()

    st.title("USMOS Knowledge Library")
    project_name = render_upload_section()
    render_library(project_name)
    render_ask_section(project_name)
    render_validation_section(project_name)


if __name__ == "__main__":
    render_library_app()
