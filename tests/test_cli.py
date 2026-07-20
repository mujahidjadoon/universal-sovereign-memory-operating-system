import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from src.cli import usmos_cli
from src.memory import memory_engine
from src.memory.memory_engine import (
    create_checkpoint,
    create_decision,
    create_event,
    create_task,
    list_memories_by_project,
    mark_metadata_scope,
    mark_metadata_topic,
    read_memory,
)
from src.storage import database
from src.storage.schema import initialize_schema


class UsmosCliTests(unittest.TestCase):

    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.original_snapshot_dir = memory_engine.SNAPSHOT_DIR
        self.original_current_project_file = memory_engine.CURRENT_PROJECT_FILE
        self.original_benchmark_dir = memory_engine.BENCHMARK_DIR
        self.original_benchmark_report_dir = memory_engine.BENCHMARK_REPORT_DIR
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.temp_dir.name) / "sandbox" / "data" / "usmos.db"
        memory_engine.SNAPSHOT_DIR = Path(self.temp_dir.name) / "sandbox" / "snapshots"
        memory_engine.CURRENT_PROJECT_FILE = (
            Path(self.temp_dir.name) / "sandbox" / "current_project.json"
        )
        memory_engine.BENCHMARK_DIR = Path(self.temp_dir.name) / "sandbox" / "benchmarks"
        memory_engine.BENCHMARK_REPORT_DIR = (
            Path(self.temp_dir.name) / "sandbox" / "benchmark_reports"
        )

        initialize_schema()
        self.seed_memories()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        memory_engine.SNAPSHOT_DIR = self.original_snapshot_dir
        memory_engine.CURRENT_PROJECT_FILE = self.original_current_project_file
        memory_engine.BENCHMARK_DIR = self.original_benchmark_dir
        memory_engine.BENCHMARK_REPORT_DIR = self.original_benchmark_report_dir
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

        create_event(
            title="Phase 1 Storage Verified",
            content="USMOS Phase 1 storage works with sandbox SQLite.",
            metadata=mark_metadata_topic(
                mark_metadata_scope({"project": "USMOS"}, scope="real"),
                topic="storage"
            ),
            importance=6
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

    def run_cli(self, argv):
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            exit_code = usmos_cli.main(argv)

        return exit_code, output.getvalue()

    def test_cli_status_shows_project_state(self):
        exit_code, output = self.run_cli(["status"])

        self.assertEqual(exit_code, 0)
        self.assertIn("USMOS Status", output)
        self.assertIn("Latest checkpoint:", output)
        self.assertIn("Current phase:", output)
        self.assertIn("Completed phases:", output)

    def test_cli_db_check_reports_database_health(self):
        exit_code, output = self.run_cli(["db-check"])

        self.assertEqual(exit_code, 0)
        self.assertIn("USMOS DB Check", output)
        self.assertIn("DB path:", output)
        self.assertIn("DB size MB:", output)
        self.assertIn("Journal mode:", output)
        self.assertIn("Busy timeout ms:", output)
        self.assertIn("Memories table exists: True", output)
        self.assertIn("Integrity check:", output)

    def test_cli_recall_uses_existing_recall(self):
        exit_code, output = self.run_cli(["recall", "sqlite"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Memory Recall for 'sqlite'", output)
        self.assertIn("SQLite", output)

    def test_cli_answer_uses_reasoning(self):
        exit_code, output = self.run_cli([
            "answer",
            "Why are we using SQLite?"
        ])

        self.assertEqual(exit_code, 0)
        self.assertIn("Answer:", output)
        self.assertIn("Memory IDs:", output)
        self.assertIn("Evidence Trace:", output)

    def test_cli_memory_show_displays_single_memory(self):
        memory = list_memories_by_project("USMOS")[0]

        exit_code, output = self.run_cli([
            "memory-show",
            str(memory["id"])
        ])

        self.assertEqual(exit_code, 0)
        self.assertIn(f"Memory #{memory['id']}", output)
        self.assertIn("Type:", output)
        self.assertIn("Metadata:", output)
        self.assertIn("Content:", output)

    def test_cli_snapshot_list_and_restore(self):
        exit_code, output = self.run_cli(["snapshot", "Phase6"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Snapshot created:", output)
        self.assertIn("USMOS_Phase6.json", output)

        exit_code, output = self.run_cli(["snapshots"])

        self.assertEqual(exit_code, 0)
        self.assertIn("USMOS_Phase6.json", output)

        exit_code, output = self.run_cli(["restore", "USMOS_Phase6.json"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Snapshot restored:", output)
        self.assertIn("Skipped duplicates:", output)

    def test_cli_timeline_shows_project_timeline(self):
        exit_code, output = self.run_cli(["timeline"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Timeline for project 'USMOS':", output)
        self.assertIn("Critical Security Rule", output)

    def test_cli_ingest_txt_file(self):
        document_path = Path(self.temp_dir.name) / "cli_ingest.txt"
        document_path.write_text(
            "Decision: USMOS must use local SQLite storage.\n\n"
            "Task: build the local ingest command.",
            encoding="utf-8"
        )

        exit_code, output = self.run_cli([
            "ingest",
            str(document_path)
        ])

        self.assertEqual(exit_code, 0)
        self.assertIn("Document Ingestion Summary", output)
        self.assertIn("Created: 2", output)

    def test_cli_save_conversation_memory_yes_saves_candidate(self):
        exit_code, output = self.run_cli([
            "--project",
            "MiniOffice",
            "save-conversation-memory",
            "We decided MiniOffice will use PostgreSQL instead of SQLite.",
            "--yes"
        ])

        memories = list_memories_by_project("MiniOffice")

        self.assertEqual(exit_code, 0)
        self.assertIn("Saved memory #", output)
        self.assertIn("Conversation memories saved: 1", output)
        self.assertTrue(
            any("PostgreSQL" in memory["content"] for memory in memories)
        )

    def test_cli_save_conversation_memory_yes_never_calls_input(self):
        sqlite_result = create_decision(
            title="MiniOffice SQLite Decision",
            content="MiniOffice will use SQLite for local storage.",
            metadata={"project": "MiniOffice"}
        )
        had_input = hasattr(usmos_cli, "input")
        original_input = getattr(usmos_cli, "input", None)

        def fail_if_called(prompt=""):
            raise AssertionError("--yes should not call input()")

        usmos_cli.input = fail_if_called

        try:
            exit_code, output = self.run_cli([
                "--project",
                "MiniOffice",
                "save-conversation-memory",
                "We decided MiniOffice will use PostgreSQL instead of SQLite.",
                "--yes",
                "--supersede"
            ])
        finally:
            if had_input:
                usmos_cli.input = original_input
            else:
                delattr(usmos_cli, "input")

        self.assertEqual(exit_code, 0)
        self.assertNotIn("Save? yes/no/edit", output)
        self.assertIn("Saved memory #", output)
        self.assertIn(f"Superseded memory #{sqlite_result['memory_id']}", output)

    def test_cli_save_conversation_memory_supersedes_sqlite_only(self):
        sqlite_result = create_decision(
            title="MiniOffice SQLite Decision",
            content="MiniOffice will use SQLite for local storage.",
            metadata={"project": "MiniOffice"}
        )
        approval_result = create_decision(
            title="MiniOffice Approval Decision",
            content="MiniOffice requires human approval before deleting files.",
            metadata={"project": "MiniOffice"}
        )
        cloud_result = create_decision(
            title="MiniOffice Cloud Decision",
            content="MiniOffice must run local-only with no cloud access.",
            metadata={"project": "MiniOffice"}
        )

        exit_code, output = self.run_cli([
            "--project",
            "MiniOffice",
            "save-conversation-memory",
            "We decided MiniOffice will use PostgreSQL instead of SQLite.",
            "--yes",
            "--supersede"
        ])

        self.assertEqual(exit_code, 0)
        self.assertIn("Saved memory #", output)
        self.assertIn(f"Superseded memory #{sqlite_result['memory_id']}", output)
        self.assertEqual(
            read_memory(sqlite_result["memory_id"])["status"],
            "superseded"
        )
        self.assertEqual(
            read_memory(approval_result["memory_id"])["status"],
            "active"
        )
        self.assertEqual(
            read_memory(cloud_result["memory_id"])["status"],
            "active"
        )

    def test_cli_duplicate_conversation_memory_supersedes_existing_sqlite(self):
        sqlite_result = create_decision(
            title="MiniOffice SQLite Decision",
            content="MiniOffice will use SQLite for local storage.",
            metadata={"project": "MiniOffice"}
        )
        approval_result = create_decision(
            title="MiniOffice Approval Decision",
            content="MiniOffice requires human approval before deleting files.",
            metadata={"project": "MiniOffice"}
        )
        cloud_result = create_decision(
            title="MiniOffice Cloud Decision",
            content="MiniOffice must run local-only with no cloud access.",
            metadata={"project": "MiniOffice"}
        )

        first_exit_code, first_output = self.run_cli([
            "--project",
            "MiniOffice",
            "save-conversation-memory",
            "We decided MiniOffice will use PostgreSQL instead of SQLite.",
            "--yes"
        ])
        self.assertEqual(first_exit_code, 0)
        self.assertIn("Saved memory #", first_output)

        second_exit_code, second_output = self.run_cli([
            "--project",
            "MiniOffice",
            "save-conversation-memory",
            "We decided MiniOffice will use PostgreSQL instead of SQLite.",
            "--yes",
            "--supersede"
        ])
        postgres_memories = [
            memory
            for memory in list_memories_by_project("MiniOffice")
            if "PostgreSQL" in memory["content"]
        ]

        self.assertEqual(second_exit_code, 0)
        self.assertIn(f"Superseded memory #{sqlite_result['memory_id']}", second_output)
        self.assertEqual(len(postgres_memories), 1)
        self.assertEqual(postgres_memories[0]["source"], "conversation")
        self.assertTrue(postgres_memories[0]["metadata"]["conversation_approved"])
        self.assertEqual(postgres_memories[0]["trust_score"], 145)
        self.assertEqual(
            read_memory(sqlite_result["memory_id"])["status"],
            "superseded"
        )
        self.assertEqual(
            read_memory(approval_result["memory_id"])["status"],
            "active"
        )
        self.assertEqual(
            read_memory(cloud_result["memory_id"])["status"],
            "active"
        )

    def test_cli_pending_queue_commands(self):
        exit_code, output = self.run_cli([
            "--project",
            "MiniOffice",
            "queue-conversation",
            "We decided MiniOffice will keep approvals local."
        ])

        self.assertEqual(exit_code, 0)
        self.assertIn("Conversation analyzed:", output)
        self.assertIn("Queued: 1", output)

        exit_code, output = self.run_cli([
            "--project",
            "MiniOffice",
            "pending"
        ])

        self.assertEqual(exit_code, 0)
        self.assertIn("Pending Memory Queue", output)
        self.assertIn("#1 [pending]", output)

        exit_code, output = self.run_cli([
            "--project",
            "MiniOffice",
            "approve",
            "1"
        ])

        self.assertEqual(exit_code, 0)
        self.assertIn("Approved pending memory #1", output)

        exit_code, output = self.run_cli([
            "--project",
            "MiniOffice",
            "pending",
            "--status",
            "approved"
        ])

        self.assertEqual(exit_code, 0)
        self.assertIn("#1 [approved]", output)

    def test_cli_project_commands(self):
        exit_code, output = self.run_cli([
            "project-create",
            "AI-FDE"
        ])

        self.assertEqual(exit_code, 0)
        self.assertIn("Project created:", output)
        self.assertIn("AI-FDE", output)

        exit_code, output = self.run_cli([
            "project-use",
            "AI-FDE"
        ])

        self.assertEqual(exit_code, 0)
        self.assertIn("Current project:", output)
        self.assertIn("AI-FDE", output)

        exit_code, output = self.run_cli(["project-current"])

        self.assertEqual(exit_code, 0)
        self.assertIn("AI-FDE", output)

        exit_code, output = self.run_cli(["projects"])

        self.assertEqual(exit_code, 0)
        self.assertIn("AI-FDE", output)

        exit_code, output = self.run_cli([
            "project-archive",
            "AI-FDE"
        ])

        self.assertEqual(exit_code, 0)
        self.assertIn("Project archived:", output)

    def test_cli_search_all_groups_projects(self):
        self.run_cli(["project-create", "AI-FDE"])
        self.run_cli(["project-use", "AI-FDE"])

        create_decision(
            title="AI-FDE SQLite Decision",
            content="AI-FDE uses SQLite for local workspace memory."
        )

        exit_code, output = self.run_cli([
            "search-all",
            "SQLite"
        ])

        self.assertEqual(exit_code, 0)
        self.assertIn("Cross-project search", output)
        self.assertIn("Project: USMOS", output)
        self.assertIn("Project: AI-FDE", output)

    def test_cli_benchmark_commands(self):
        exit_code, output = self.run_cli([
            "benchmark-generate",
            "ScaleTest",
            "5"
        ])

        benchmark_file = (
            Path(self.temp_dir.name)
            / "sandbox"
            / "benchmarks"
            / "ScaleTest_5.md"
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(benchmark_file.exists())
        self.assertIn("Benchmark file generated:", output)

        exit_code, output = self.run_cli([
            "benchmark-ingest",
            "ScaleTest",
            str(benchmark_file)
        ])

        self.assertEqual(exit_code, 0)
        self.assertIn("Benchmark ingestion complete:", output)
        self.assertIn("Created: 5", output)

        exit_code, output = self.run_cli([
            "benchmark-suite",
            "SuiteTest",
            "5"
        ])

        self.assertEqual(exit_code, 0)
        self.assertIn("Benchmark suite complete:", output)
        self.assertIn("Report file:", output)

    def test_cli_token_benchmark_commands(self):
        exit_code, output = self.run_cli([
            "token-benchmark-generate",
            "TokenCLITest",
            "1000"
        ])

        benchmark_file = (
            Path(self.temp_dir.name)
            / "sandbox"
            / "benchmarks"
            / "TokenCLITest_1000_tokens.md"
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(benchmark_file.exists())
        self.assertIn("Token benchmark file generated:", output)
        self.assertIn("Estimated tokens generated:", output)

        exit_code, output = self.run_cli([
            "token-benchmark-suite",
            "TokenSuiteCLITest",
            "1000"
        ])

        self.assertEqual(exit_code, 0)
        self.assertIn("Token benchmark suite complete:", output)
        self.assertIn("Report file:", output)

    def test_cli_models_lists_mocked_ollama_models(self):
        original_list_ollama_models = usmos_cli.list_ollama_models
        usmos_cli.list_ollama_models = lambda: ["llama3.2", "mistral"]

        try:
            exit_code, output = self.run_cli(["models"])
        finally:
            usmos_cli.list_ollama_models = original_list_ollama_models

        self.assertEqual(exit_code, 0)
        self.assertIn("Ollama models:", output)
        self.assertIn("llama3.2", output)
        self.assertIn("mistral", output)

    def test_cli_chat_uses_mocked_conversation_bridge(self):
        original_memory_client = usmos_cli.MemoryClient

        class FakeMemoryClient:

            def __init__(self, project_name=None):
                self.project_name = project_name or "USMOS"

            def chat(
                self,
                question,
                model=None,
                mode="compact",
                max_memories=5
            ):
                return {
                    "success": True,
                    "project": self.project_name,
                    "question": question,
                    "model": model or "llama3.2",
                    "mode": mode,
                    "max_memories": max_memories,
                    "answer": "MiniOffice uses local-only sandbox memory.",
                    "memory_ids": [1, 2],
                    "trust_scores": [
                        {
                            "memory_id": 1,
                            "trust_score": 145
                        },
                        {
                            "memory_id": 2,
                            "trust_score": 135
                        }
                    ],
                    "retrieval_duration_seconds": 0.001,
                    "prompt_build_duration_seconds": 0.002,
                    "ollama_duration_seconds": 0.003,
                    "total_duration_seconds": 0.006,
                    "response_time_seconds": 0.006
                }

        usmos_cli.MemoryClient = FakeMemoryClient

        try:
            exit_code, output = self.run_cli([
                "chat",
                "What is MiniOffice?",
                "--model",
                "llama3.2",
                "--max-memories",
                "3",
                "--debug-timing"
            ])
        finally:
            usmos_cli.MemoryClient = original_memory_client

        self.assertEqual(exit_code, 0)
        self.assertIn("Natural answer:", output)
        self.assertIn("MiniOffice uses local-only sandbox memory.", output)
        self.assertIn("#1, #2", output)
        self.assertIn("Memory #1: 145", output)
        self.assertIn("Model: llama3.2", output)
        self.assertIn("Mode: compact", output)
        self.assertIn("Max memories: 3", output)
        self.assertIn("Timings:", output)
        self.assertIn("Retrieval: 0.001", output)
        self.assertIn("Prompt build: 0.002", output)
        self.assertIn("Ollama: 0.003", output)
        self.assertIn("Total: 0.006", output)
