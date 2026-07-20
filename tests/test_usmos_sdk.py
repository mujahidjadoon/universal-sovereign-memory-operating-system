import tempfile
import unittest
from pathlib import Path

from src.memory import memory_engine
from src.memory.memory_engine import list_memories_by_project
from src.storage import database
from src.storage.schema import initialize_schema
from src.usmos import MemoryClient
from src.usmos.models import MemoryAnswerResult


class MemoryClientSdkTests(unittest.TestCase):

    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.original_snapshot_dir = memory_engine.SNAPSHOT_DIR
        self.original_current_project_file = memory_engine.CURRENT_PROJECT_FILE
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

        database.DB_PATH = self.temp_path / "sandbox" / "data" / "usmos.db"
        memory_engine.SNAPSHOT_DIR = self.temp_path / "sandbox" / "snapshots"
        memory_engine.CURRENT_PROJECT_FILE = (
            self.temp_path / "sandbox" / "current_project.json"
        )

        initialize_schema()
        self.client = MemoryClient("SDKProject")

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        memory_engine.SNAPSHOT_DIR = self.original_snapshot_dir
        memory_engine.CURRENT_PROJECT_FILE = self.original_current_project_file
        self.temp_dir.cleanup()

    def test_project_methods_and_health(self):
        create_result = self.client.project_create(
            "SDKProject",
            description="SDK test project"
        )
        use_result = self.client.project_use("SDKProject")
        current_project = self.client.project_current()
        health = self.client.health()

        self.assertTrue(create_result["success"])
        self.assertTrue(use_result["success"])
        self.assertEqual(current_project, "SDKProject")
        self.assertTrue(health["success"])
        self.assertEqual(health["project"], "SDKProject")
        self.assertIn("database_connected", health)
        self.assertIn("current_project", health)
        self.assertIn("ollama_available", health)
        self.assertIn("sdk_version", health)
        self.assertIn("memory_count", health)
        self.assertFalse(health["cloud"])

    def test_save_status_search_answer_timeline_and_graph_methods(self):
        self.client.save(
            memory_type="project_note",
            title="SDK Generic Note",
            content="Fact: SDKProject stores reusable client examples."
        )
        self.client.save_decision(
            title="SDK SQLite Decision",
            content="Decision: SDKProject will use SQLite for local storage."
        )
        self.client.save_task(
            title="SDK CLI Task",
            content="Task: build SDK command wrappers."
        )
        self.client.save_checkpoint(
            title="SDK Phase Complete",
            content="Checkpoint: SDK Phase completed.",
            metadata={
                "completed_phase": "Phase 18 SDK"
            }
        )
        self.client.save_event(
            title="SDK Test Event",
            content="Event: SDK tests ran locally."
        )
        self.client.save_fact(
            title="SDK Fact",
            content="Fact: SDKProject exposes MemoryClient."
        )

        status = self.client.status()
        search_results = self.client.search("SQLite")
        answer = self.client.answer("Why are we using SQLite?")
        timeline = self.client.timeline()
        graph = self.client.graph()

        self.assertEqual(status["project"], "SDKProject")
        self.assertGreaterEqual(status["memory_count"], 6)
        self.assertTrue(any("SQLite" in memory["content"] for memory in search_results))
        self.assertIsInstance(answer, MemoryAnswerResult)
        self.assertIn("SQLite", answer.answer)
        self.assertIn("Timeline for project 'SDKProject':", timeline)
        self.assertGreaterEqual(len(graph["nodes"]), 6)

    def test_chat_method_uses_compact_direct_answer(self):
        self.client.save_decision(
            title="SDK Database Decision",
            content="Decision: SDKProject will use SQLite for local storage."
        )

        result = self.client.chat(
            "What database does SDKProject use?",
            model="llama3.2",
            max_memories=3
        )

        self.assertTrue(result["success"])
        self.assertIn("SDKProject uses SQLite", result["answer"])
        self.assertEqual(result["ollama_duration_seconds"], 0)

    def test_answer_uses_fast_path_and_returns_result(self):
        self.client.save_decision(
            title="SDK Database Decision",
            content="Decision: SDKProject will use SQLite for local storage."
        )

        result = self.client.answer("What database does SDKProject use?")

        self.assertIsInstance(result, MemoryAnswerResult)
        self.assertIn("SDKProject uses SQLite", result.answer)
        self.assertGreater(len(result.memory_ids), 0)
        self.assertTrue(result.trust_scores)
        self.assertEqual(result.ollama_duration_seconds, 0)
        self.assertTrue(result.answered_without_llm)

    def test_answer_text_returns_string(self):
        self.client.save_decision(
            title="SDK Database Decision",
            content="Decision: SDKProject will use SQLite for local storage."
        )

        answer_text = self.client.answer_text(
            "What database does SDKProject use?"
        )

        self.assertIsInstance(answer_text, str)
        self.assertIn("SDKProject uses SQLite", answer_text)

    def test_database_question_bypasses_ollama(self):
        self.client.save_decision(
            title="SDK PostgreSQL Decision",
            content="Decision: SDKProject will use PostgreSQL instead of SQLite."
        )

        result = self.client.answer("What database does SDKProject use?")

        self.assertIn("SDKProject uses PostgreSQL", result.answer)
        self.assertEqual(result.ollama_duration_seconds, 0)
        self.assertTrue(result.answered_without_llm)

    def test_cloud_question_bypasses_ollama(self):
        self.client.save_decision(
            title="SDK Cloud Rule",
            content="Decision: SDKProject must run local-only with no cloud access."
        )

        result = self.client.answer("Does SDKProject use cloud APIs?")

        self.assertTrue(result.answer.startswith("No."))
        self.assertIn("no cloud access", result.answer)
        self.assertEqual(result.ollama_duration_seconds, 0)
        self.assertTrue(result.answered_without_llm)

    def test_snapshot_question_bypasses_ollama(self):
        self.client.save_fact(
            title="SDK Snapshot Path",
            content="Fact: SDKProject snapshots are stored in sandbox/snapshots."
        )

        result = self.client.answer("Where are SDKProject snapshots stored?")

        self.assertIn("sandbox/snapshots", result.answer)
        self.assertEqual(result.ollama_duration_seconds, 0)
        self.assertTrue(result.answered_without_llm)

    def test_approval_question_bypasses_ollama(self):
        self.client.save_decision(
            title="SDK Approval Rule",
            content="Decision: SDKProject will require human approval before deleting files."
        )

        result = self.client.answer(
            "Does SDKProject require human approval before deleting files?"
        )

        self.assertTrue(result.answer.startswith("Yes."))
        self.assertIn("human approval before deleting files", result.answer)
        self.assertEqual(result.ollama_duration_seconds, 0)
        self.assertTrue(result.answered_without_llm)

    def test_unknown_question_returns_no_evidence_without_ollama(self):
        result = self.client.answer("Does SDKProject use Kubernetes?")

        self.assertEqual(result.answer, "I do not have evidence for that.")
        self.assertEqual(result.memory_ids, [])
        self.assertEqual(result.ollama_duration_seconds, 0)
        self.assertTrue(result.answered_without_llm)

    def test_snapshot_and_restore_methods(self):
        self.client.save_decision(
            title="SDK Snapshot Decision",
            content="Decision: SDKProject snapshots stay local."
        )

        snapshot_result = self.client.snapshot("Phase18")
        restore_result = self.client.restore("SDKProject_Phase18.json")

        self.assertTrue(Path(snapshot_result["snapshot_file"]).exists())
        self.assertTrue(restore_result["success"])
        self.assertEqual(restore_result["project"], "SDKProject")

    def test_queue_pending_approve_and_reject_methods(self):
        queue_result = self.client.queue(
            "We decided SDKProject will keep approval local."
        )
        pending_items = self.client.pending()
        pending_id = pending_items[0]["pending_id"]

        approval = self.client.approve(pending_id)

        second_queue = self.client.queue(
            "Next step: build SDK documentation."
        )
        second_pending_id = second_queue["pending_items"][0]["pending_id"]
        rejection = self.client.reject(second_pending_id)
        approved_items = self.client.pending(status="approved")
        rejected_items = self.client.pending(status="rejected")

        self.assertEqual(queue_result["created"], 1)
        self.assertTrue(approval["success"])
        self.assertTrue(rejection["success"])
        self.assertEqual(len(approved_items), 1)
        self.assertEqual(len(rejected_items), 1)

    def test_approve_all_and_reject_all_methods(self):
        self.client.queue(
            "We decided SDKProject will use local memory. "
            "Next step: build SDK examples."
        )

        approve_all_result = self.client.approve_all(memory_type="decision")
        pending_tasks = self.client.pending(status="pending", memory_type="task")
        reject_all_result = self.client.reject_all()
        rejected_items = self.client.pending(status="rejected")
        active_memories = list_memories_by_project("SDKProject")

        self.assertEqual(approve_all_result["count"], 1)
        self.assertEqual(len(pending_tasks), 1)
        self.assertEqual(reject_all_result["count"], 1)
        self.assertEqual(len(rejected_items), 1)
        self.assertEqual(len(active_memories), 1)


if __name__ == "__main__":
    unittest.main()
