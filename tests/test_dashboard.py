import sqlite3
import inspect
import tempfile
import unittest
from pathlib import Path

from src.conversation.conversation_queue import queue_conversation_memory_candidates
from src.memory import memory_engine
from src.memory.memory_engine import (
    create_checkpoint,
    create_decision,
    create_project,
    create_task,
    mark_metadata_scope,
    mark_metadata_topic,
)
from src.storage import database
from src.storage.schema import initialize_schema
from src.ui import dashboard
from src.ui import library_app


class FakeStreamlit:

    def __init__(self):
        self.session_state = {}
        self.warnings = []

    def warning(self, message):
        self.warnings.append(message)


class DashboardSmokeTests(unittest.TestCase):

    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.original_snapshot_dir = memory_engine.SNAPSHOT_DIR
        self.original_current_project_file = memory_engine.CURRENT_PROJECT_FILE
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.temp_dir.name) / "sandbox" / "data" / "usmos.db"
        memory_engine.SNAPSHOT_DIR = Path(self.temp_dir.name) / "sandbox" / "snapshots"
        memory_engine.CURRENT_PROJECT_FILE = (
            Path(self.temp_dir.name) / "sandbox" / "current_project.json"
        )

        initialize_schema()
        self.seed_memories()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        memory_engine.SNAPSHOT_DIR = self.original_snapshot_dir
        memory_engine.CURRENT_PROJECT_FILE = self.original_current_project_file
        self.temp_dir.cleanup()

    def seed_memories(self):
        create_decision(
            title="Critical Security Rule",
            content="USMOS database must stay inside sandbox/data/usmos.db.",
            metadata=mark_metadata_topic(
                mark_metadata_scope({"project": "USMOS"}, scope="real"),
                topic="security"
            ),
            importance=10
        )

        create_task(
            title="Build Local SQLite Storage",
            content="Implement SQLite storage inside the local sandbox folder.",
            metadata=mark_metadata_topic(
                mark_metadata_scope({"project": "USMOS"}, scope="real"),
                topic="storage"
            ),
            importance=7
        )

        create_checkpoint(
            title="USMOS Phase 5 Explainable Memory Reasoning Complete",
            content="USMOS Phase 5 completed explainable evidence traces and memory IDs.",
            metadata={
                "project": "USMOS",
                "phase": "Phase 5",
                "completed_phase": "Phase 5 Explainable Memory Reasoning",
                "memory_scope": "real",
                "topic": "project_status"
            },
            importance=10
        )

    def test_dashboard_imports_memory_engine_functions(self):
        self.assertTrue(callable(dashboard.recover_project_state))
        self.assertTrue(callable(dashboard.answer_with_reasoning))
        self.assertTrue(callable(dashboard.summarize_project_graph))
        self.assertTrue(callable(dashboard.detect_contradictions))

    def test_library_app_imports_successfully(self):
        self.assertTrue(callable(library_app.render_library_app))
        self.assertTrue(callable(library_app.render_upload_section))
        self.assertTrue(callable(library_app.render_ask_section))
        self.assertTrue(callable(library_app.render_validation_section))

    def test_library_app_reuses_upload_helper(self):
        source = inspect.getsource(library_app.render_upload_section)

        self.assertIn("save_uploaded_book_file", source)
        self.assertIn("ingest_book_file", source)

    def test_library_app_has_no_url_input(self):
        source = inspect.getsource(library_app)

        self.assertNotIn("http://", source)
        self.assertNotIn("https://", source)
        self.assertNotIn("st.text_input(\"URL", source)

    def test_library_app_accepts_pdf_docx_file_types(self):
        self.assertEqual(
            library_app.SUPPORTED_UPLOAD_TYPES,
            ["txt", "md", "pdf", "docx"]
        )
        self.assertIn("OCR for scanned PDFs: coming soon", library_app.COMING_SOON_TEXT)

    def test_library_app_contains_validation_section(self):
        source = inspect.getsource(library_app.render_validation_section)

        self.assertIn("Validation / Testing", source)
        self.assertIn("add_validation_question", source)
        self.assertIn("run_validation_set", source)

    def test_book_evidence_renderers_show_evidence_score(self):
        dashboard_source = inspect.getsource(dashboard.render_book_evidence)
        library_source = inspect.getsource(library_app.render_evidence)

        self.assertIn("Evidence score", dashboard_source)
        self.assertIn("Evidence score", library_source)

    def test_dashboard_sidebar_navigation_choices_are_visible(self):
        expected_pages = [
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

        self.assertEqual(dashboard.NAVIGATION_PAGES, expected_pages)
        self.assertEqual(dashboard.DEFAULT_DASHBOARD_PAGE, "Knowledge Library")
        self.assertTrue(callable(dashboard.select_dashboard_page))
        self.assertTrue(callable(dashboard.render_dashboard_page))

    def test_knowledge_library_renderer_contains_visible_header_text(self):
        source = inspect.getsource(dashboard.render_knowledge_library)

        self.assertIn("📚 Knowledge Library", source)
        self.assertIn("Upload .txt or .md books here.", source)
        self.assertIn("Knowledge Library loaded successfully", source)
        self.assertIn("Upload Book / Document", source)

    def test_selected_knowledge_library_page_calls_renderer(self):
        calls = []
        original_renderer = dashboard.render_knowledge_library

        def fake_renderer(project_name):
            calls.append(project_name)

        dashboard.render_knowledge_library = fake_renderer

        try:
            dashboard.render_dashboard_page(
                page="Knowledge Library",
                data={},
                project_name="BookTest"
            )
        finally:
            dashboard.render_knowledge_library = original_renderer

        self.assertEqual(calls, ["BookTest"])

    def test_dashboard_does_not_apply_black_on_black_css(self):
        source = inspect.getsource(dashboard.apply_page_style)

        self.assertIn("background: #ffffff", source)
        self.assertIn("color: #172033", source)
        self.assertNotIn("background: #000000", source)
        self.assertNotIn("color: #000000", source)

    def test_dashboard_init_skips_initialize_schema_when_memories_exists(self):
        fake_st = FakeStreamlit()
        original_st = dashboard.st
        original_initialize_schema = dashboard.initialize_schema

        def fail_if_called():
            raise AssertionError("initialize_schema should not run")

        dashboard.st = fake_st
        dashboard.initialize_schema = fail_if_called

        try:
            result = dashboard.initialize_dashboard_schema()
        finally:
            dashboard.st = original_st
            dashboard.initialize_schema = original_initialize_schema

        self.assertTrue(result["success"])
        self.assertTrue(result["skipped"])
        self.assertFalse(result["read_only"])
        self.assertTrue(fake_st.session_state["schema_initialized"])

    def test_dashboard_init_handles_database_locked_without_crashing(self):
        fake_st = FakeStreamlit()
        original_st = dashboard.st
        original_table_exists = dashboard.dashboard_memories_table_exists

        def raise_locked():
            raise sqlite3.OperationalError("database is locked")

        dashboard.st = fake_st
        dashboard.dashboard_memories_table_exists = raise_locked

        try:
            result = dashboard.initialize_dashboard_schema()
        finally:
            dashboard.st = original_st
            dashboard.dashboard_memories_table_exists = original_table_exists

        self.assertFalse(result["success"])
        self.assertTrue(result["read_only"])
        self.assertTrue(fake_st.session_state["dashboard_read_only"])
        self.assertIn(
            "Database is busy. Using read-only dashboard mode.",
            fake_st.warnings
        )

    def test_get_connection_sets_busy_timeout(self):
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA busy_timeout")
        busy_timeout = cursor.fetchone()[0]
        conn.close()

        self.assertEqual(busy_timeout, database.SQLITE_BUSY_TIMEOUT_MS)

    def test_dashboard_data_helper_loads_local_memory_data(self):
        data = dashboard.get_dashboard_data("USMOS")

        self.assertIn("project_state", data)
        self.assertIn("current_project", data)
        self.assertIn("projects", data)
        self.assertIn("phase_summary", data)
        self.assertIn("timeline", data)
        self.assertIn("project_graph", data)
        self.assertIn("top_memories", data)
        self.assertIn("memory_status_counts", data)
        self.assertEqual(data["memory_status_counts"]["active"], 3)
        self.assertGreater(len(data["top_memories"]), 0)

    def test_dashboard_data_helper_loads_project_registry(self):
        create_project("AI-FDE")

        data = dashboard.get_dashboard_data("AI-FDE")
        project_names = []

        for project in data["projects"]:
            project_names.append(project["name"])

        self.assertEqual(data["current_project"], "AI-FDE")
        self.assertIn("USMOS", project_names)
        self.assertIn("AI-FDE", project_names)

    def test_dashboard_data_helper_loads_pending_queue(self):
        queue_conversation_memory_candidates(
            user_message="We decided USMOS will keep queue approval local.",
            project_name="USMOS"
        )

        data = dashboard.get_dashboard_data("USMOS")

        self.assertIn("pending_queue", data)
        self.assertIn("pending_queue_counts", data)
        self.assertEqual(data["pending_queue_counts"]["pending"], 1)
        self.assertEqual(len(data["pending_queue"]), 1)
        self.assertEqual(data["pending_queue"][0]["memory_type"], "decision")

    def test_streamlit_requirement_is_reported_when_missing(self):
        if dashboard.STREAMLIT_AVAILABLE:
            self.assertIsNone(dashboard.require_streamlit())
        else:
            with self.assertRaises(RuntimeError):
                dashboard.require_streamlit()
