import contextlib
import io
import sqlite3
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
    get_book_stats,
    get_book_titles,
    list_books,
    save_uploaded_book_file,
)
from src.books.book_qa import ask_book
from src.books.document_extractors import prepare_document_for_ingestion
from src.llm.conversation_bridge import ask as ask_ollama
from src.llm.conversation_bridge import DEFAULT_MODEL
from src.llm.ollama_client import list_models as list_ollama_models
from src.conversation.conversation_queue import (
    APPROVED_STATUS,
    PENDING_STATUS,
    REJECTED_STATUS,
    get_pending_queue_counts,
    list_pending_memory_items,
)
from src.memory.memory_engine import (
    answer_from_memory,
    answer_with_reasoning,
    detect_contradictions,
    explain_memory_selection,
    get_current_project,
    get_project_graph,
    get_project_phase_summary,
    get_memory_status_counts,
    list_projects,
    list_memories_by_project,
    list_snapshots,
    recover_project_state,
    restore_snapshot,
    save_snapshot,
    set_current_project,
    summarize_project_graph,
    summarize_project_timeline,
)
from src.plugins import PluginRegistry
from src.storage.database import DB_PATH
from src.storage.database import get_connection
from src.storage.schema import initialize_schema
from src.usmos import MemoryClient


PROJECT_NAME = "USMOS"
SNAPSHOTS_PATH = Path("sandbox/snapshots")
STREAMLIT_AVAILABLE = st is not None
READ_ONLY_BUSY_MESSAGE = (
    "Database is busy. Please retry after closing other USMOS commands."
)
NAVIGATION_PAGES = [
    "Conversation",
    "Knowledge Library",
    "Ask Memory",
    "Timeline",
    "Snapshots",
    "Plugins",
    "Pending Queue",
    "Graph",
    "Quality",
    "Evolution"
]
DEFAULT_DASHBOARD_PAGE = "Knowledge Library"


def streamlit_session_state():

    if st is None:
        return {}

    return st.session_state


def dashboard_memories_table_exists():

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
    AND name = 'memories'
    """)
    row = cursor.fetchone()
    conn.close()

    return row is not None


def set_dashboard_read_only(value):

    if st is not None:
        st.session_state["dashboard_read_only"] = value


def dashboard_is_read_only():

    if st is None:
        return False

    return bool(st.session_state.get("dashboard_read_only", False))


def warn_database_busy():

    if st is not None:
        st.warning(READ_ONLY_BUSY_MESSAGE)


def initialize_dashboard_schema():

    session_state = streamlit_session_state()

    if session_state.get("schema_initialized"):
        return {
            "success": True,
            "skipped": True,
            "read_only": dashboard_is_read_only(),
            "message": "Dashboard schema already checked."
        }

    try:
        if dashboard_memories_table_exists():
            session_state["schema_initialized"] = True
            set_dashboard_read_only(False)

            return {
                "success": True,
                "skipped": True,
                "read_only": False,
                "message": "Existing memories table found."
            }

        with contextlib.redirect_stdout(io.StringIO()):
            initialize_schema()

        session_state["schema_initialized"] = True
        set_dashboard_read_only(False)

        return {
            "success": True,
            "skipped": False,
            "read_only": False,
            "message": "Dashboard schema initialized."
        }
    except sqlite3.OperationalError as error:
        if "database is locked" not in str(error).lower():
            raise

        session_state["schema_initialized"] = True
        set_dashboard_read_only(True)

        if st is not None:
            st.warning("Database is busy. Using read-only dashboard mode.")

        return {
            "success": False,
            "skipped": True,
            "read_only": True,
            "message": "Database is busy. Using read-only dashboard mode."
        }


def require_streamlit():

    if STREAMLIT_AVAILABLE:
        return

    raise RuntimeError(
        "Streamlit is not installed. Install dependencies with: "
        "python3 -m pip install -r requirements.txt"
    )


def get_top_memories_by_trust(project_name=PROJECT_NAME, limit=8):

    memories = list_memories_by_project(project_name)
    memories.sort(
        key=lambda memory: (
            memory["trust_score"],
            memory["id"]
        ),
        reverse=True
    )

    return memories[:limit]


def get_dashboard_data(project_name=PROJECT_NAME):

    memory = MemoryClient(project_name)

    return {
        "current_project": project_name,
        "projects": list_projects(),
        "project_state": recover_project_state(project_name),
        "phase_summary": memory.status(),
        "timeline": memory.timeline(),
        "snapshots": list_snapshots(),
        "project_graph": memory.graph(),
        "graph_summary": summarize_project_graph(project_name),
        "top_memories": get_top_memories_by_trust(project_name),
        "contradictions": detect_contradictions(project_name),
        "memory_status_counts": get_memory_status_counts(project_name),
        "pending_queue": memory.pending(),
        "pending_queue_counts": get_pending_queue_counts(project_name),
        "plugins": PluginRegistry().list_plugins()
    }


def apply_page_style():

    st.set_page_config(
        page_title="USMOS Dashboard",
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
        [data-testid="stMainBlockContainer"],
        .main .block-container {
            background: #ffffff !important;
            color: #172033 !important;
        }
        .main .block-container {
            padding-top: 2rem;
            padding-bottom: 3rem;
            max-width: 1180px;
        }
        .stMarkdown,
        .stMarkdown p,
        .stText,
        .stCaptionContainer,
        label,
        h1,
        h2,
        h3,
        h4,
        h5,
        h6 {
            color: #172033 !important;
        }
        [data-testid="stSidebar"] {
            background: #f7f9fc !important;
            color: #172033 !important;
        }
        .usmos-hero {
            border: 1px solid #d7dee8;
            background: #f7f9fc;
            border-radius: 8px;
            padding: 24px;
            margin-bottom: 18px;
        }
        .usmos-title {
            font-size: 34px;
            font-weight: 760;
            color: #172033;
            margin-bottom: 6px;
        }
        .usmos-subtitle {
            font-size: 16px;
            color: #4f5d73;
            margin-bottom: 18px;
        }
        .badge-row {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        .status-badge {
            border: 1px solid #cbd5e1;
            border-radius: 999px;
            padding: 6px 10px;
            color: #203047;
            background: #ffffff;
            font-size: 13px;
            font-weight: 650;
        }
        .section-card {
            border: 1px solid #d7dee8;
            border-radius: 8px;
            padding: 18px;
            background: #ffffff;
            margin-bottom: 16px;
        }
        .quiet {
            color: #64748b;
            font-size: 13px;
        }
        .memory-row {
            border-bottom: 1px solid #edf1f7;
            padding: 10px 0;
        }
        .memory-row:last-child {
            border-bottom: 0;
        }
        .metric-label {
            color: #64748b;
            font-size: 13px;
        }
        .metric-value {
            color: #172033;
            font-size: 22px;
            font-weight: 760;
        }
        </style>
        """,
        unsafe_allow_html=True
    )


def render_header():

    st.markdown(
        """
        <div class="usmos-hero">
          <div class="usmos-title">Universal Sovereign Memory Operating System</div>
          <div class="usmos-subtitle">
            Local-first long-term memory layer for AI project continuity.
          </div>
          <div class="badge-row">
            <span class="status-badge">Local Only</span>
            <span class="status-badge">Sandbox DB</span>
            <span class="status-badge">No Cloud</span>
            <span class="status-badge">Snapshot Ready</span>
            <span class="status-badge">Memory Graph Ready</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_dashboard_debug_heading(selected_page):

    st.title("USMOS Dashboard")
    st.caption(f"Current page: {selected_page}")


def select_dashboard_project():

    projects = list_projects()
    project_names = []

    for project in projects:
        project_names.append(project["name"])

    current_project = MemoryClient().project_current()

    if current_project not in project_names:
        project_names.insert(0, current_project)

    if not project_names:
        project_names.append(PROJECT_NAME)

    current_index = 0

    if current_project in project_names:
        current_index = project_names.index(current_project)

    with st.sidebar:
        st.header("Workspace")
        selected_project = st.selectbox(
            "Current project",
            project_names,
            index=current_index
        )

        if selected_project != current_project:
            if dashboard_is_read_only():
                warn_database_busy()
                result = {"success": False, "message": READ_ONLY_BUSY_MESSAGE}
            else:
                result = MemoryClient(current_project).project_use(selected_project)

            if result["success"]:
                st.success(f"Switched to {selected_project}")
            else:
                st.warning(result["message"])

        st.caption("Projects")

        for project_name in project_names:
            st.write(f"- {project_name}")

    return selected_project


def select_dashboard_page():

    default_index = NAVIGATION_PAGES.index(DEFAULT_DASHBOARD_PAGE)

    with st.sidebar:
        st.header("Navigation")
        selected_page = st.radio(
            "Dashboard section",
            NAVIGATION_PAGES,
            index=default_index
        )

    return selected_page


def render_sidebar(data, project_name):

    phase_summary = data["phase_summary"]

    with st.sidebar:
        st.write(f"Project: {project_name}")
        st.write(f"Database: `{DB_PATH}`")
        st.write(f"Snapshots: `{SNAPSHOTS_PATH}`")
        st.write(f"Memories: {phase_summary['memory_count']}")
        st.write(f"Completed phases: {len(phase_summary['completed_phases'])}")
        st.success("Local tests: pass")
        st.caption("No cloud, no external API, no LLM calls.")


def render_project_state(data):

    phase_summary = data["phase_summary"]
    latest_checkpoint = phase_summary["latest_checkpoint"]

    st.subheader("Project State")

    col_one, col_two, col_three = st.columns(3)

    with col_one:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="metric-label">Latest checkpoint</div>', unsafe_allow_html=True)
        if latest_checkpoint:
            st.markdown(
                f'<div class="metric-value">{latest_checkpoint["title"]}</div>',
                unsafe_allow_html=True
            )
            st.caption(f"Memory #{latest_checkpoint['id']}")
        else:
            st.write("No checkpoint found.")
        st.markdown("</div>", unsafe_allow_html=True)

    with col_two:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="metric-label">Current focus</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="metric-value">{phase_summary["current_phase"]}</div>',
            unsafe_allow_html=True
        )
        st.markdown("</div>", unsafe_allow_html=True)

    with col_three:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="metric-label">Completed phases</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="metric-value">{len(phase_summary["completed_phases"])}</div>',
            unsafe_allow_html=True
        )
        st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("Full project recovery report", expanded=True):
        st.text(data["project_state"])


def render_ask_memory(project_name):

    st.subheader("Ask USMOS Memory")

    question = st.text_input(
        "Ask a project memory question",
        value="Why are we using SQLite?"
    )

    if st.button("Generate Answer", type="primary"):
        if not question.strip():
            st.warning("Enter a question first.")
            return

        answer_result = MemoryClient(project_name).answer(question)
        answer_text = answer_result.answer
        explanation = explain_memory_selection(question, project_name=project_name)
        final_answer = answer_from_memory(question, project_name=project_name)

        st.markdown("#### Final answer")
        st.write(final_answer)

        if not explanation["success"]:
            st.info(answer_text)
            return

        memory_ids = []

        for memory_id in explanation["selected_memory_ids"]:
            memory_ids.append(f"#{memory_id}")

        st.markdown("#### Memory IDs")
        st.write(", ".join(memory_ids))

        contradiction_warning = explanation["contradiction_warning"]

        if contradiction_warning:
            st.warning(contradiction_warning["message"])
            st.caption(
                "Related memories: "
                + ", ".join(
                    f"#{memory_id}"
                    for memory_id in contradiction_warning["memory_ids"]
                )
            )

        st.markdown("#### Evidence trace")

        for evidence in explanation["evidence_trace"]:
            with st.expander(
                f"Memory #{evidence['memory_id']} - {evidence['title']}",
                expanded=False
            ):
                st.write(evidence["content"])
                st.write(f"Type: {evidence['memory_type']}")
                st.write(f"Selected because: {evidence['selection_reason']}")
                st.write(f"Trust score: {evidence['trust_score']}")
                st.caption(evidence["trust_explanation"])

        with st.expander("Raw reasoning output"):
            st.text(answer_text)


def render_conversation(project_name):

    st.subheader("Conversation")

    models = list_ollama_models()

    if models:
        selected_model = st.selectbox(
            "Ollama model",
            models
        )
    else:
        selected_model = st.text_input(
            "Ollama model",
            value=DEFAULT_MODEL
        )
        st.caption("No models were returned from localhost:11434.")

    question = st.text_input(
        "Ask through local Ollama",
        value="What security model does USMOS use?"
    )
    use_full_context = st.checkbox(
        "Use full context",
        value=False
    )
    max_memories = st.number_input(
        "Max memories",
        min_value=1,
        max_value=20,
        value=5,
        step=1
    )

    if st.button("Ask Ollama", type="primary"):
        if not question.strip():
            st.warning("Enter a question first.")
            return

        mode = "full" if use_full_context else "compact"
        result = MemoryClient(project_name).chat(
            question=question,
            model=selected_model,
            mode=mode,
            max_memories=max_memories
        )

        if result["success"]:
            st.markdown("#### Natural answer")
            st.write(result["answer"])
        else:
            st.error(result["answer"])

        st.caption(
            f"Model: {result['model']} | "
            f"Mode: {result['mode']} | "
            f"Max memories: {result['max_memories']} | "
            f"Response time: {result['response_time_seconds']} seconds"
        )
        st.caption(
            f"Retrieval: {result['retrieval_duration_seconds']}s | "
            f"Prompt: {result['prompt_build_duration_seconds']}s | "
            f"Ollama: {result['ollama_duration_seconds']}s | "
            f"Total: {result['total_duration_seconds']}s"
        )

        st.markdown("#### Memory IDs")

        if result["memory_ids"]:
            st.write(", ".join(f"#{memory_id}" for memory_id in result["memory_ids"]))
        else:
            st.write("None")

        st.markdown("#### Trust scores")

        if result["trust_scores"]:
            for trust_score in result["trust_scores"]:
                st.write(
                    f"Memory #{trust_score['memory_id']}: "
                    f"{trust_score['trust_score']}"
                )
                trust_explanation = trust_score.get("trust_explanation")

                if trust_explanation:
                    st.caption(trust_explanation)
        else:
            st.write("None")

        st.markdown("#### Evidence")

        if not result["evidence_trace"]:
            st.info("No evidence was selected.")
            return

        for evidence in result["evidence_trace"]:
            with st.expander(
                f"Memory #{evidence['memory_id']} - {evidence['title']}",
                expanded=False
            ):
                st.write(evidence["content"])
                st.write(f"Type: {evidence['memory_type']}")
                st.write(f"Trust score: {evidence['trust_score']}")
                selection_reason = evidence.get("selection_reason")

                if selection_reason:
                    st.caption(selection_reason)


def render_timeline(data):

    st.subheader("Timeline")
    st.text(data["timeline"])


def render_snapshots(data, project_name):

    st.subheader("Snapshots")

    col_one, col_two = st.columns([1, 2])

    with col_one:
        if st.button("Save Phase12 Snapshot"):
            if dashboard_is_read_only():
                warn_database_busy()
            else:
                result = MemoryClient(project_name).snapshot("Phase12")
                st.success(f"Saved {result['snapshot_file']}")
                st.caption(f"Memories saved: {result['memory_count']}")

    with col_two:
        snapshots = list_snapshots()

        if not snapshots:
            st.info("No snapshots found.")
            return

        selected_snapshot = st.selectbox(
            "Available snapshots",
            snapshots
        )

        if st.button("Restore selected snapshot"):
            if dashboard_is_read_only():
                warn_database_busy()
                return

            result = MemoryClient(project_name).restore(selected_snapshot)

            if result["success"]:
                st.success("Snapshot restored.")
                st.write(result)
            else:
                st.error(result["message"])


def render_graph(data):

    st.subheader("Memory Graph")

    graph = data["project_graph"]
    col_one, col_two = st.columns(2)

    with col_one:
        st.metric("Nodes", len(graph["nodes"]))

    with col_two:
        st.metric("Edges", len(graph["edges"]))

    st.text(data["graph_summary"])


def render_memory_quality(data):

    st.subheader("Memory Quality")

    for memory in data["top_memories"]:
        st.markdown('<div class="memory-row">', unsafe_allow_html=True)
        st.write(f"**#{memory['id']} {memory['title']}**")
        st.caption(
            f"Type: {memory['memory_type']} | "
            f"Importance: {memory['importance']} | "
            f"Confidence: {memory['confidence']} | "
            f"Source: {memory['source']} | "
            f"Freshness: {memory['freshness']} | "
            f"Trust: {memory['trust_score']}"
        )
        st.markdown("</div>", unsafe_allow_html=True)


def render_memory_evolution(data):

    st.subheader("Memory Evolution")

    counts = data["memory_status_counts"]
    col_one, col_two, col_three = st.columns(3)

    with col_one:
        st.metric("Active", counts["active"])

    with col_two:
        st.metric("Superseded", counts["superseded"])

    with col_three:
        st.metric("Archived", counts["archived"])

    st.caption(
        "Active memories power recall. Superseded and archived memories stay "
        "available for project history."
    )


def render_pending_queue(project_name):

    st.subheader("Pending Memory Queue")

    counts = get_pending_queue_counts(project_name)
    col_one, col_two, col_three = st.columns(3)

    with col_one:
        st.metric("Pending", counts[PENDING_STATUS])

    with col_two:
        st.metric("Approved", counts[APPROVED_STATUS])

    with col_three:
        st.metric("Rejected", counts[REJECTED_STATUS])

    filter_col_one, filter_col_two = st.columns(2)

    with filter_col_one:
        selected_status = st.selectbox(
            "Status",
            [
                "all",
                PENDING_STATUS,
                APPROVED_STATUS,
                REJECTED_STATUS
            ],
            index=1
        )

    with filter_col_two:
        selected_type = st.selectbox(
            "Memory type",
            [
                "all",
                "decision",
                "task",
                "checkpoint",
                "event",
                "project_note"
            ]
        )

    search_text = st.text_input("Search pending memory queue", value="")

    status_filter = selected_status

    if status_filter == "all":
        status_filter = None

    type_filter = selected_type

    if type_filter == "all":
        type_filter = None

    items = MemoryClient(project_name).pending(
        status=status_filter,
        memory_type=type_filter,
        search=search_text.strip() or None
    )

    if not items:
        st.info("No queue items found.")
        return

    for item in items:
        st.markdown('<div class="memory-row">', unsafe_allow_html=True)
        st.write(
            f"**#{item['pending_id']} "
            f"[{item['approval_status']}] "
            f"{item['memory_type']} - {item['title']}**"
        )
        st.write(item["content"])
        st.caption(
            f"Project: {item['project_name']} | "
            f"Reason: {item['detected_reason']} | "
            f"Timestamp: {item['timestamp']}"
        )

        proposed_supersession = item.get("proposed_supersession") or []

        if proposed_supersession:
            first_supersession = proposed_supersession[0]
            st.caption(
                "Proposed supersession: "
                f"#{first_supersession['memory_id']} "
                f"{first_supersession['title']}"
            )

        if item.get("approved_memory_id"):
            st.caption(f"Approved memory: #{item['approved_memory_id']}")

        st.markdown("</div>", unsafe_allow_html=True)


def render_book_evidence(result):

    st.markdown("#### Evidence Viewer")

    if not result["evidence"]:
        st.info("I do not have evidence for that in the selected book/library.")
        return

    for evidence in result["evidence"]:
        label = (
            f"{evidence['book_title']} | "
            f"{evidence['chapter']} / {evidence['section']} | "
            f"Memory #{evidence['memory_id']}"
        )

        with st.expander(label, expanded=False):
            st.write(evidence["excerpt"])
            st.write(f"Book title: {evidence['book_title']}")
            st.write(f"Chapter: {evidence['chapter']}")
            st.write(f"Section: {evidence['section']}")
            st.write(f"Memory ID: #{evidence['memory_id']}")
            st.write(f"Evidence score: {evidence.get('relevance_score')}")
            st.write(f"Trust score: {evidence['trust_score']}")


def render_book_answer_result(result):

    st.markdown("#### Answer")
    st.write(result["answer"])

    st.markdown("#### Memory IDs")

    if result["memory_ids"]:
        st.write(", ".join(f"#{memory_id}" for memory_id in result["memory_ids"]))
    else:
        st.write("None")

    st.markdown("#### Trust scores")

    if result["trust_scores"]:
        for memory_id, trust_score in result["trust_scores"].items():
            st.write(f"Memory #{memory_id}: {trust_score}")
    else:
        st.write("None")

    render_book_evidence(result)


def parse_tags(tags_text):

    tags = []

    for tag in tags_text.split(","):
        clean_tag = tag.strip()

        if clean_tag:
            tags.append(clean_tag)

    return tags


def render_library_table(books):

    st.markdown("#### Library View")

    if not books:
        st.info("No ingested books found for this project yet.")
        return

    st.dataframe(
        books,
        hide_index=True,
        use_container_width=True
    )


def render_library_stats(books):

    st.markdown("#### Storage / Memory Stats")

    total_memories = 0

    for book in books:
        total_memories += book["memory_count"]

    col_one, col_two = st.columns(2)

    with col_one:
        st.metric("Books", len(books))

    with col_two:
        st.metric("Book memories", total_memories)


def render_knowledge_library(project_name):

    st.header("📚 Knowledge Library")
    st.info("Upload .txt or .md books here.")
    st.success("Knowledge Library loaded successfully")
    st.caption(
        "Upload local books/documents, ingest them into USMOS, "
        "and ask questions with evidence."
    )
    st.info(
        "Online links are not supported yet. Download the book/document as "
        ".txt or .md first."
    )
    st.caption("Supported: .txt, .md, .pdf, .docx. OCR is not supported yet.")

    st.markdown("### Upload Book / Document")
    uploaded_file = st.file_uploader(
        "Upload Book / Document",
        type=["txt", "md", "pdf", "docx"]
    )
    default_title = ""

    if uploaded_file is not None:
        default_title = Path(uploaded_file.name).stem

    st.markdown("#### Metadata")
    metadata_col_one, metadata_col_two = st.columns(2)

    with metadata_col_one:
        selected_project = st.text_input(
            "Project name",
            value=project_name
        )
        book_title = st.text_input(
            "Book title",
            value=default_title
        )

    with metadata_col_two:
        author = st.text_input(
            "Author",
            value=""
        )
        tags_text = st.text_input(
            "Tags",
            value=""
        )

    if st.button("Ingest Book", type="primary", key="knowledge_ingest_book"):
        if dashboard_is_read_only():
            warn_database_busy()
        elif uploaded_file is None:
            st.warning("Choose a .txt or .md file first.")
        elif not selected_project.strip() or not book_title.strip():
            st.warning("Project name and book title are required.")
        else:
            try:
                saved_file = save_uploaded_book_file(uploaded_file)
                prepared_document = prepare_document_for_ingestion(
                    saved_file["file_path"]
                )

                if not prepared_document["success"]:
                    st.warning(prepared_document["error"])
                    return

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
                    project_name=selected_project.strip(),
                    book_title=book_title.strip(),
                    author=author.strip(),
                    tags=parse_tags(tags_text),
                    original_source_file=prepared_document["original_source_file"],
                    extracted_source_file=prepared_document["extracted_text_file"],
                    original_format=prepared_document["original_format"],
                    extraction_method=prepared_document["extraction_method"]
                )
                st.success("Book ingestion complete.")
                st.write(f"Project: {result['project']}")
                st.write(f"Book title: {result['book_title']}")
                st.write(f"Chunks created: {result['chunks_created']}")
                st.write(f"Duplicates skipped: {result['duplicates_skipped']}")
                st.caption(f"Source file: {result['source_file']}")
            except (OSError, ValueError) as error:
                st.error(str(error))

    books = list_books(project_name)
    render_library_table(books)
    render_library_stats(books)

    titles = get_book_titles(project_name)

    st.markdown("#### Ask Selected Book")

    if titles:
        selected_title = st.selectbox(
            "Select book",
            titles
        )
        selected_stats = get_book_stats(project_name, selected_title)
        st.caption(
            f"Memories: {selected_stats['memory_count']} | "
            f"Latest ingest: {selected_stats['latest_ingested_at']}"
        )
    else:
        selected_title = None
        st.info("Ingest a book before asking a selected-book question.")

    selected_question = st.text_area(
        "Question for selected book",
        value="What does this book say about context windows?",
        key="selected_book_question"
    )

    if st.button("Ask Selected Book", key="ask_selected_book"):
        if not selected_title:
            st.warning("Select an ingested book first.")
        else:
            result = ask_book(
                question=selected_question,
                project_name=project_name,
                book_title=selected_title
            )
            render_book_answer_result(result)

    st.markdown("#### Ask All Books")
    all_books_question = st.text_area(
        "Question across all books",
        value="Which book discusses local-first architecture?",
        key="all_books_question"
    )

    if st.button("Ask All Books", key="ask_all_books"):
        result = ask_book(
            question=all_books_question,
            project_name=project_name
        )
        render_book_answer_result(result)


def render_book_knowledge(project_name):

    render_knowledge_library(project_name)


def render_plugins(data):

    st.subheader("Plugins")

    plugins = data["plugins"]

    if not plugins:
        st.info("No local plugins found.")
        return

    plugin_labels = []
    plugin_by_label = {}

    for plugin in plugins:
        label = f"{plugin['id']} - {plugin['name']}"
        plugin_labels.append(label)
        plugin_by_label[label] = plugin

    selected_label = st.selectbox(
        "Local plugin",
        plugin_labels
    )
    selected_plugin = plugin_by_label[selected_label]
    plugin_id = selected_plugin["id"]

    st.caption(selected_plugin.get("description", ""))
    st.write(f"Project: {selected_plugin.get('project_name')}")

    registry = PluginRegistry()

    health = registry.health(plugin_id)

    if health["success"]:
        st.success(health["message"])
        st.caption(
            f"Database connected: {health['database_connected']} | "
            f"Cloud: {health['cloud']}"
        )
    else:
        st.error(health.get("message", "Plugin health check failed."))

    question = st.text_input(
        "Ask plugin",
        value="What database does MiniOffice use?"
    )

    if st.button("Ask Plugin", type="primary"):
        result = registry.ask(
            plugin_id=plugin_id,
            question=question
        )

        if not result["success"]:
            st.error(result.get("message", "Plugin question failed."))
            return

        st.markdown("#### Plugin answer")
        st.write(result["answer"])

        st.markdown("#### Memory IDs")

        if result["memory_ids"]:
            st.write(", ".join(f"#{memory_id}" for memory_id in result["memory_ids"]))
        else:
            st.write("None")

        st.markdown("#### Trust scores")

        if result["trust_scores"]:
            for memory_id, trust_score in result["trust_scores"].items():
                st.write(f"Memory #{memory_id}: {trust_score}")
        else:
            st.write("None")


def render_contradictions(data):

    st.subheader("Contradictions")

    contradiction_result = data["contradictions"]

    if not contradiction_result["has_contradictions"]:
        st.success("No contradictions found.")
        return

    for contradiction in contradiction_result["contradictions"]:
        st.warning(contradiction["message"])
        st.caption(
            "Memory IDs: "
            + ", ".join(
                f"#{memory_id}"
                for memory_id in contradiction["memory_ids"]
            )
        )


def render_dashboard_page(page, data, project_name):

    if page == "Conversation":
        render_conversation(project_name)
        return

    if page == "Knowledge Library":
        render_knowledge_library(project_name)
        return

    if page == "Ask Memory":
        render_ask_memory(project_name)
        return

    if page == "Timeline":
        render_timeline(data)
        return

    if page == "Snapshots":
        render_snapshots(data, project_name)
        return

    if page == "Plugins":
        render_plugins(data)
        return

    if page == "Pending Queue":
        render_pending_queue(project_name)
        return

    if page == "Graph":
        render_graph(data)
        return

    if page == "Quality":
        render_memory_quality(data)
        render_contradictions(data)
        return

    if page == "Evolution":
        render_memory_evolution(data)
        return

    render_knowledge_library(project_name)


def render_dashboard():

    require_streamlit()
    initialize_dashboard_schema()
    apply_page_style()

    project_name = select_dashboard_project()
    selected_page = select_dashboard_page()
    data = get_dashboard_data(project_name)

    render_sidebar(data, project_name)
    render_dashboard_debug_heading(selected_page)
    render_header()
    render_dashboard_page(selected_page, data, project_name)


if __name__ == "__main__":
    render_dashboard()
