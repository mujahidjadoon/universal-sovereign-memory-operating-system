import tempfile
import unittest
from pathlib import Path

from src.memory.memory_engine import (
    archive_memory,
    create_decision,
    create_task,
    get_active_memories,
    get_memory_history,
    get_memory_neighbors,
    list_memories_by_project,
    mark_metadata_scope,
    mark_metadata_topic,
    read_memory,
    recover_project_state,
    supersede_memory,
)
from src.storage import database
from src.storage.schema import initialize_schema


class MemoryEvolutionTests(unittest.TestCase):

    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.temp_dir.name) / "sandbox" / "data" / "usmos.db"

        initialize_schema()

        metadata = mark_metadata_topic(
            mark_metadata_scope({"project": "USMOS"}, scope="real"),
            topic="storage"
        )

        old_result = create_decision(
            title="Use SQLite Initial Decision",
            content="Database = SQLite for local storage.",
            metadata=metadata.copy(),
            importance=8
        )
        new_result = create_decision(
            title="Use SQLite Final Decision",
            content="Database = SQLite remains the final local storage choice.",
            metadata=metadata.copy(),
            importance=10
        )
        task_result = create_task(
            title="Temporary Storage Task",
            content="Archive this task after testing memory evolution.",
            metadata=metadata.copy(),
            importance=5
        )

        self.old_memory_id = old_result["memory_id"]
        self.new_memory_id = new_result["memory_id"]
        self.task_id = task_result["memory_id"]

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_supersede_memory_updates_status_and_relationship(self):
        result = supersede_memory(self.old_memory_id, self.new_memory_id)

        self.assertTrue(result["success"])
        self.assertEqual(read_memory(self.old_memory_id)["status"], "superseded")

        neighbors = get_memory_neighbors(self.old_memory_id)
        relationships = []

        for neighbor in neighbors:
            relationships.append(neighbor["relationship_type"])

        self.assertIn("superseded_by", relationships)

    def test_archive_memory_updates_status(self):
        result = archive_memory(self.task_id)

        self.assertTrue(result["success"])
        self.assertEqual(read_memory(self.task_id)["status"], "archived")

    def test_get_memory_history_shows_chain(self):
        supersede_memory(self.old_memory_id, self.new_memory_id)

        history = get_memory_history(self.old_memory_id)

        self.assertIn("Original Memory", history)
        self.assertIn("Superseded By", history)
        self.assertIn("Current Memory", history)
        self.assertIn("Use SQLite Initial Decision", history)
        self.assertIn("Use SQLite Final Decision", history)

    def test_get_active_memories_filters_history_statuses(self):
        supersede_memory(self.old_memory_id, self.new_memory_id)
        archive_memory(self.task_id)

        active_ids = []

        for memory in get_active_memories():
            active_ids.append(memory["id"])

        self.assertIn(self.new_memory_id, active_ids)
        self.assertNotIn(self.old_memory_id, active_ids)
        self.assertNotIn(self.task_id, active_ids)

    def test_project_recovery_includes_memory_evolution_sections(self):
        supersede_memory(self.old_memory_id, self.new_memory_id)

        recovery = recover_project_state("USMOS")

        self.assertIn("Active decisions:", recovery)
        self.assertIn("Historical decisions:", recovery)
        self.assertIn("Superseded memories:", recovery)
        self.assertIn("Use SQLite Initial Decision", recovery)

    def test_history_aware_project_listing_includes_superseded_memory(self):
        supersede_memory(self.old_memory_id, self.new_memory_id)

        active_memories = list_memories_by_project("USMOS")
        history_memories = list_memories_by_project("USMOS", include_history=True)

        active_ids = [memory["id"] for memory in active_memories]
        history_ids = [memory["id"] for memory in history_memories]

        self.assertNotIn(self.old_memory_id, active_ids)
        self.assertIn(self.old_memory_id, history_ids)

