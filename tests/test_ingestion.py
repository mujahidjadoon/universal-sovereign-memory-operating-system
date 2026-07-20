import tempfile
import unittest
from pathlib import Path

from src.memory import memory_engine
from src.memory.memory_engine import (
    answer_from_memory,
    compute_memory_hash,
    create_checkpoint,
    create_decision,
    ingested_memory_exists,
    ingest_text_file,
    list_memories_by_project,
    read_memory,
    summarize_ingestion_result,
)
from src.storage import database
from src.storage.schema import initialize_schema


class DocumentIngestionTests(unittest.TestCase):

    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        database.DB_PATH = self.temp_path / "sandbox" / "data" / "usmos.db"

        initialize_schema()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def write_document(self, file_name, content):
        document_path = self.temp_path / file_name
        document_path.write_text(content, encoding="utf-8")
        return document_path

    def test_ingest_txt_file_creates_memories(self):
        document_path = self.write_document(
            "project_notes.txt",
            "We chose SQLite for local memory.\n\n"
            "TODO build the local recovery command.\n\n"
            "Phase complete checkpoint for document ingestion."
        )

        result = ingest_text_file(document_path)

        self.assertTrue(result["success"])
        self.assertEqual(result["created"], 3)
        self.assertEqual(result["duplicates"], 0)
        self.assertEqual(len(result["memories"]), 3)
        self.assertIn("_timings", result)
        self.assertIn("parse_duration", result["_timings"])
        self.assertIn("duplicate_check_duration", result["_timings"])
        self.assertIn("insert_duration", result["_timings"])
        self.assertIn("keyword_index_duration", result["_timings"])

    def test_five_decision_lines_create_five_memories(self):
        document_path = self.write_document(
            "decisions.txt",
            "Decision: A\n"
            "Decision: B\n"
            "Decision: C\n"
            "Decision: D\n"
            "Decision: E"
        )

        result = ingest_text_file(document_path)
        memories = list_memories_by_project("USMOS")
        decision_count = 0

        for memory in memories:
            if memory["memory_type"] == "decision":
                decision_count += 1

        self.assertEqual(result["created"], 5)
        self.assertEqual(decision_count, 5)

    def test_five_task_lines_create_five_memories(self):
        document_path = self.write_document(
            "tasks.txt",
            "Task: A\n"
            "Task: B\n"
            "Task: C\n"
            "Task: D\n"
            "Task: E"
        )

        result = ingest_text_file(document_path)
        memories = list_memories_by_project("USMOS")
        task_count = 0

        for memory in memories:
            if memory["memory_type"] == "task":
                task_count += 1

        self.assertEqual(result["created"], 5)
        self.assertEqual(task_count, 5)

    def test_five_checkpoint_lines_create_five_memories(self):
        document_path = self.write_document(
            "checkpoints.txt",
            "Checkpoint: A\n"
            "Checkpoint: B\n"
            "Checkpoint: C\n"
            "Checkpoint: D\n"
            "Checkpoint: E"
        )

        result = ingest_text_file(document_path)
        memories = list_memories_by_project("USMOS")
        checkpoint_count = 0

        for memory in memories:
            if memory["memory_type"] == "checkpoint":
                checkpoint_count += 1

        self.assertEqual(result["created"], 5)
        self.assertEqual(checkpoint_count, 5)

    def test_decision_extraction(self):
        document_path = self.write_document(
            "decision.md",
            "Decision: USMOS must use local SQLite storage."
        )

        result = ingest_text_file(document_path)
        memories = list_memories_by_project("USMOS")

        self.assertEqual(result["created"], 1)
        self.assertEqual(memories[0]["memory_type"], "decision")
        self.assertEqual(memories[0]["source"], "document_ingestion")
        self.assertEqual(memories[0]["metadata"]["source"], "document_ingestion")

    def test_content_hash_is_generated_for_created_memory(self):
        result = create_decision(
            title="Hash Test Decision",
            content="Decision: USMOS must use local SQLite storage.",
            metadata={
                "project": "USMOS",
                "memory_scope": "real"
            }
        )

        memory = read_memory(result["memory_id"])
        expected_hash = compute_memory_hash(
            project_name="USMOS",
            memory_type="decision",
            content="Decision: USMOS must use local SQLite storage."
        )

        self.assertEqual(memory["content_hash"], expected_hash)

    def test_ingested_duplicate_lookup_does_not_call_list_all_memories(self):
        create_decision(
            title="Indexed Duplicate Decision",
            content="Decision: USMOS must use local SQLite storage.",
            metadata={
                "project": "USMOS",
                "memory_scope": "real"
            }
        )
        original_list_all_memories = memory_engine.list_all_memories

        def fail_if_called(*args, **kwargs):
            raise AssertionError("list_all_memories should not be called")

        memory_engine.list_all_memories = fail_if_called

        try:
            duplicate = ingested_memory_exists(
                project_name="USMOS",
                memory_type="decision",
                content="Decision: USMOS must use local SQLite storage."
            )
        finally:
            memory_engine.list_all_memories = original_list_all_memories

        self.assertIsNotNone(duplicate)
        self.assertEqual(duplicate["title"], "Indexed Duplicate Decision")

    def test_task_extraction(self):
        document_path = self.write_document(
            "task.txt",
            "Next step: implement document ingestion tests."
        )

        result = ingest_text_file(document_path)
        memories = list_memories_by_project("USMOS")

        self.assertEqual(result["created"], 1)
        self.assertEqual(memories[0]["memory_type"], "task")

    def test_checkpoint_extraction(self):
        document_path = self.write_document(
            "checkpoint.md",
            "Milestone: snapshot ingestion checkpoint passed."
        )

        result = ingest_text_file(document_path)
        memories = list_memories_by_project("USMOS")

        self.assertEqual(result["created"], 1)
        self.assertEqual(memories[0]["memory_type"], "checkpoint")

    def test_duplicate_skip_on_second_ingest(self):
        document_path = self.write_document(
            "duplicates.txt",
            "Decision: USMOS must use local SQLite storage."
        )

        first_result = ingest_text_file(document_path)
        second_result = ingest_text_file(document_path)

        self.assertEqual(first_result["created"], 1)
        self.assertEqual(second_result["created"], 0)
        self.assertEqual(second_result["duplicates"], 1)

    def test_reingesting_same_file_skips_all_duplicates(self):
        document_path = self.write_document(
            "five_memories.txt",
            "Decision: TestProject must use local-only memory.\n\n"
            "Task: build the secure local workspace command.\n\n"
            "Event: privacy rule verified for local storage.\n\n"
            "Checkpoint: no cloud milestone passed.\n\n"
            "Project note: sandbox memory stays user-controlled."
        )

        first_result = ingest_text_file(
            document_path,
            project_name="TestProject"
        )
        second_result = ingest_text_file(
            document_path,
            project_name="TestProject"
        )

        self.assertEqual(first_result["created"], 5)
        self.assertEqual(second_result["created"], 0)
        self.assertEqual(second_result["duplicates"], 5)

    def test_local_only_memory_is_tagged_security(self):
        document_path = self.write_document(
            "security.md",
            "Decision: TestProject must use local-only memory."
        )

        ingest_text_file(
            document_path,
            project_name="TestProject"
        )

        memories = list_memories_by_project("TestProject")

        self.assertEqual(memories[0]["metadata"]["topic"], "security")

    def test_security_question_returns_ingested_local_only_memory(self):
        document_path = self.write_document(
            "testproject_security.txt",
            "Decision: TestProject must use local-only memory."
        )

        ingest_text_file(
            document_path,
            project_name="TestProject"
        )

        answer = answer_from_memory("What is TestProject security rule?")

        self.assertIn("local-only memory", answer)
        self.assertNotIn("No relevant memory found", answer)

    def test_duplicate_ingestion_enriches_old_security_metadata(self):
        old_result = create_decision(
            title="Old TestProject Rule",
            content="Decision: TestProject must use local-only memory.",
            metadata={
                "project": "TestProject",
                "memory_scope": "real"
            }
        )
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE memories
        SET content_hash = NULL
        WHERE id = ?
        """, (old_result["memory_id"],))
        conn.commit()
        conn.close()

        document_path = self.write_document(
            "old_security.txt",
            "Decision: TestProject must use local-only memory."
        )

        result = ingest_text_file(
            document_path,
            project_name="TestProject"
        )
        memory = read_memory(old_result["memory_id"])
        answer = answer_from_memory("What is TestProject security rule?")

        self.assertEqual(result["created"], 0)
        self.assertEqual(result["duplicates"], 1)
        self.assertTrue(result["memories"][0]["enriched"])
        self.assertEqual(result["memories"][0]["status"], "duplicate_enriched")
        self.assertEqual(memory["metadata"]["topic"], "security")
        self.assertEqual(memory["metadata"]["source"], "document_ingestion")
        self.assertEqual(memory["metadata"]["ingested_from"], str(document_path))
        self.assertIn("local-only memory", answer)

    def test_cloud_question_recalls_avoid_cloud_decision(self):
        create_decision(
            title="StressProject Cloud Rule",
            content="Decision: StressProject must avoid cloud APIs.",
            metadata={
                "project": "StressProject",
                "memory_scope": "real"
            }
        )

        answer = answer_from_memory("Does StressProject use cloud?")

        self.assertIn("No.", answer)
        self.assertIn("avoid cloud APIs", answer)

    def test_internet_question_recalls_avoid_cloud_decision(self):
        create_decision(
            title="StressProject Cloud Rule",
            content="Decision: StressProject must avoid cloud APIs.",
            metadata={
                "project": "StressProject",
                "memory_scope": "real"
            }
        )

        answer = answer_from_memory("Does StressProject need internet access?")

        self.assertIn("No.", answer)
        self.assertIn("avoid cloud APIs", answer)

    def test_local_memory_question_recalls_local_only_decision(self):
        create_decision(
            title="StressProject Local Memory Rule",
            content="Decision: StressProject must use local-only memory.",
            metadata={
                "project": "StressProject",
                "memory_scope": "real"
            }
        )

        answer = answer_from_memory("Does StressProject use local memory?")

        self.assertIn("local-only memory", answer)
        self.assertNotIn("No relevant memory found", answer)

    def test_completed_phases_question_recalls_checkpoints(self):
        create_checkpoint(
            title="StressProject Phase 1 Complete",
            content="Checkpoint: StressProject Phase 1 completed.",
            metadata={
                "project": "StressProject",
                "memory_scope": "real"
            }
        )

        answer = answer_from_memory("What are StressProject completed phases?")

        self.assertIn("Phase 1 completed", answer)
        self.assertNotIn("No relevant memory found", answer)

    def test_summarize_ingestion_result(self):
        document_path = self.write_document(
            "summary.txt",
            "Task: build a document ingestion command."
        )

        result = ingest_text_file(document_path)
        summary = summarize_ingestion_result(result)

        self.assertIn("Document Ingestion Summary", summary)
        self.assertIn("Created: 1", summary)
        self.assertIn("Duplicates skipped: 0", summary)
