import tempfile
import unittest
from pathlib import Path

from src.memory.memory_engine import (
    create_decision,
    create_project_note,
    create_relationship,
    create_task,
    create_checkpoint,
    get_memory_neighbors,
    get_project_graph,
    graph_recovery_trace,
    list_memories_by_project,
    mark_metadata_scope,
    mark_metadata_topic,
    summarize_project_graph,
)
from src.storage import database
from src.storage.schema import initialize_schema


class MemoryGraphTests(unittest.TestCase):

    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.temp_dir.name) / "sandbox" / "data" / "usmos.db"

        initialize_schema()
        self.seed_graph_memories()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def seed_graph_memories(self):
        metadata = mark_metadata_topic(
            mark_metadata_scope({"project": "USMOS"}, scope="real"),
            topic="graph"
        )

        self.decision = create_decision(
            title="Use SQLite For Local Memory",
            content="Database = SQLite for the local sandbox memory store.",
            metadata=metadata.copy(),
            importance=10
        )

        self.task = create_task(
            title="Build SQLite Storage Task",
            content="Implement the SQLite storage task.",
            metadata=metadata.copy(),
            importance=8
        )

        self.checkpoint = create_checkpoint(
            title="SQLite Storage Checkpoint",
            content="SQLite storage was completed and verified.",
            metadata=metadata.copy(),
            importance=9
        )

        self.snapshot = create_project_note(
            title="Snapshot Phase6",
            content="Snapshot file records the verified project state.",
            metadata=metadata.copy(),
            importance=7
        )

        self.decision_id = self.decision["memory_id"]
        self.task_id = self.task["memory_id"]
        self.checkpoint_id = self.checkpoint["memory_id"]
        self.snapshot_id = self.snapshot["memory_id"]

    def create_graph_relationships(self):
        create_relationship(
            self.decision_id,
            self.task_id,
            "created"
        )
        create_relationship(
            self.task_id,
            self.checkpoint_id,
            "completed_by"
        )
        create_relationship(
            self.checkpoint_id,
            self.snapshot_id,
            "snapshot_of"
        )

    def test_create_relationship(self):
        result = create_relationship(
            self.decision_id,
            self.task_id,
            "created"
        )

        self.assertTrue(result["success"])
        self.assertIsNotNone(result["link_id"])

    def test_get_memory_neighbors_returns_connected_memories(self):
        self.create_graph_relationships()

        neighbors = get_memory_neighbors(self.task_id)
        neighbor_titles = []

        for neighbor in neighbors:
            neighbor_titles.append(neighbor["memory"]["title"])

        self.assertIn("Use SQLite For Local Memory", neighbor_titles)
        self.assertIn("SQLite Storage Checkpoint", neighbor_titles)

    def test_get_project_graph_returns_nodes_and_edges(self):
        self.create_graph_relationships()

        graph = get_project_graph("USMOS")

        self.assertEqual(graph["project"], "USMOS")
        self.assertEqual(len(graph["nodes"]), 4)
        self.assertEqual(len(graph["edges"]), 3)
        self.assertEqual(graph["edges"][0]["relationship_type"], "created")

    def test_summarize_project_graph_includes_key_relationships(self):
        self.create_graph_relationships()

        summary = summarize_project_graph("USMOS")

        self.assertIn("Project Graph Summary", summary)
        self.assertIn("Nodes: 4", summary)
        self.assertIn("Edges: 3", summary)
        self.assertIn("Decision #", summary)
        self.assertIn("-> created", summary)
        self.assertIn("Task #", summary)

    def test_graph_recovery_trace_follows_relationship_chain(self):
        self.create_graph_relationships()

        trace = graph_recovery_trace(self.decision_id)

        self.assertIn("Decision #", trace)
        self.assertIn("Use SQLite For Local Memory", trace)
        self.assertIn("v created", trace)
        self.assertIn("Task #", trace)
        self.assertIn("v completed_by", trace)
        self.assertIn("Checkpoint #", trace)
        self.assertIn("v snapshot_of", trace)
        self.assertIn("Snapshot Phase6", trace)
