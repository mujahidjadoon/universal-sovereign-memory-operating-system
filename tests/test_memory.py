import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from src.memory import memory_engine
from src.memory.memory_engine import (
    answer_from_memory,
    answer_with_reasoning,
    auto_recall,
    calculate_trust_score,
    classify_memory_freshness,
    answer_project_state_question,
    create_decision,
    create_checkpoint,
    create_event,
    create_memory,
    create_project_note,
    create_task,
    detect_contradictions,
    explain_memory_selection,
    get_latest_checkpoint,
    get_project_phase_summary,
    list_memories_by_project,
    list_snapshots,
    mark_metadata_scope,
    mark_metadata_topic,
    read_memory,
    recover_project_state,
    restore_snapshot,
    save_snapshot,
    search_memories,
)
from src.storage import database
from src.storage.schema import initialize_schema


class MemoryAnswerTests(unittest.TestCase):

    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.original_snapshot_dir = memory_engine.SNAPSHOT_DIR
        self.temp_dir = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.temp_dir.name) / "sandbox" / "data" / "usmos.db"
        memory_engine.SNAPSHOT_DIR = Path(self.temp_dir.name) / "sandbox" / "snapshots"

        initialize_schema()
        self.seed_memories()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        memory_engine.SNAPSHOT_DIR = self.original_snapshot_dir
        self.temp_dir.cleanup()

    def seed_memories(self):
        base_metadata = {
            "project": "USMOS"
        }

        create_decision(
            title="Critical Security Rule",
            content="USMOS database must stay inside sandbox/data/usmos.db.",
            metadata=mark_metadata_topic(
                mark_metadata_scope(base_metadata.copy(), scope="real"),
                topic="security"
            ),
            importance=10
        )

        create_task(
            title="Build Local SQLite Storage",
            content="Implement SQLite storage inside the local sandbox folder.",
            metadata=mark_metadata_topic(
                mark_metadata_scope(base_metadata.copy(), scope="real"),
                topic="storage"
            ),
            importance=7
        )

        create_event(
            title="Phase 1 Storage Verified",
            content="USMOS Phase 1 storage works with sandbox SQLite.",
            metadata=mark_metadata_topic(
                mark_metadata_scope(base_metadata.copy(), scope="real"),
                topic="storage"
            ),
            importance=6
        )

    def test_default_database_path_stays_in_sandbox(self):
        self.assertEqual(
            self.original_db_path,
            Path("sandbox/data/usmos.db")
        )

    def test_sqlite_question_returns_human_answer(self):
        answer = answer_from_memory("Why are we using SQLite?")

        self.assertIn("USMOS is using SQLite", answer)
        self.assertIn("SQLite storage was implemented", answer)
        self.assertIn("Phase 1 storage was verified successfully", answer)
        self.assertIn("sandbox/data/usmos.db", answer)
        self.assertNotIn("USMOS Context Package", answer)

    def test_question_memory_type_words_filter_recall_results(self):
        create_checkpoint(
            title="Type Filter Checkpoint",
            content="Checkpoint: USMOS type filtering checkpoint was recorded.",
            metadata={
                "project": "USMOS",
                "memory_scope": "real"
            }
        )
        create_project_note(
            title="Type Filter Fact",
            content="Fact: USMOS type filtering fact was recorded.",
            metadata={
                "project": "USMOS",
                "memory_scope": "real"
            }
        )

        expected_types = {
            "What tasks are stored?": "task",
            "What checkpoint is stored?": "checkpoint",
            "What decision is stored?": "decision",
            "What event is stored?": "event",
            "What fact is stored?": "project_note"
        }

        for question, expected_type in expected_types.items():
            with self.subTest(question=question):
                result = auto_recall(question)

                self.assertTrue(result["success"])
                self.assertEqual(result["memory_type"], expected_type)

                for memory in result["memories"]:
                    self.assertEqual(memory["memory_type"], expected_type)

    def test_database_location_question_returns_location_answer(self):
        answer = answer_from_memory("Where is the database stored?")

        self.assertIn("USMOS stores its database inside the local sandbox", answer)
        self.assertIn("sandbox/data/usmos.db", answer)

    def test_snapshot_save_list_and_restore(self):
        snapshot_result = save_snapshot("USMOS", "Phase2")
        snapshot_path = Path(snapshot_result["snapshot_file"])

        self.assertTrue(snapshot_path.exists())
        self.assertEqual(snapshot_result["memory_count"], 3)
        self.assertIn("USMOS_Phase2.json", list_snapshots())

        database.DB_PATH = Path(self.temp_dir.name) / "sandbox" / "data" / "restored.db"
        initialize_schema()

        restore_result = restore_snapshot("USMOS_Phase2.json")

        self.assertTrue(restore_result["success"])
        self.assertEqual(restore_result["restored"], 3)
        self.assertEqual(restore_result["skipped_duplicates"], 0)
        self.assertEqual(len(list_memories_by_project("USMOS")), 3)

        duplicate_restore_result = restore_snapshot("USMOS_Phase2.json")

        self.assertEqual(duplicate_restore_result["restored"], 0)
        self.assertEqual(duplicate_restore_result["skipped_duplicates"], 3)

    def test_memory_confidence_source_and_trust_score(self):
        result = create_memory(
            memory_type="checkpoint",
            title="High Trust Quality Memory",
            content="This quality memory has strong confidence.",
            metadata={
                "project": "USMOS",
                "topic": "project_status"
            },
            importance=10,
            confidence=95,
            source="checkpoint"
        )

        memory = read_memory(result["memory_id"])

        self.assertEqual(memory["confidence"], 95)
        self.assertEqual(memory["source"], "checkpoint")
        self.assertEqual(memory["trust_score"], 145)
        self.assertEqual(calculate_trust_score(memory), 145)

    def test_memory_freshness_classification(self):
        fresh_memory = {
            "created_at": datetime.now().isoformat()
        }
        aging_memory = {
            "created_at": (datetime.now() - timedelta(days=60)).isoformat()
        }
        stale_memory = {
            "created_at": (datetime.now() - timedelta(days=200)).isoformat()
        }

        self.assertEqual(classify_memory_freshness(fresh_memory), "fresh")
        self.assertEqual(classify_memory_freshness(aging_memory), "aging")
        self.assertEqual(classify_memory_freshness(stale_memory), "stale")

    def test_search_results_sort_by_trust_score(self):
        create_memory(
            memory_type="project_note",
            title="Weak Ranking Memory",
            content="ranking-quality-token should appear lower.",
            metadata={
                "project": "USMOS",
                "topic": "storage"
            },
            importance=10,
            confidence=10,
            source="user"
        )

        create_memory(
            memory_type="project_note",
            title="Strong Ranking Memory",
            content="ranking-quality-token should appear higher.",
            metadata={
                "project": "USMOS",
                "topic": "storage"
            },
            importance=8,
            confidence=95,
            source="checkpoint"
        )

        results = search_memories("ranking-quality-token")

        self.assertEqual(results[0]["title"], "Strong Ranking Memory")
        self.assertGreater(
            results[0]["trust_score"],
            results[1]["trust_score"]
        )

    def test_detect_contradictions_finds_database_conflict(self):
        create_decision(
            title="Alternative Database Decision",
            content="Database = PostgreSQL.",
            metadata={
                "project": "USMOS",
                "topic": "storage"
            },
            importance=7,
            confidence=80,
            source="user"
        )

        result = detect_contradictions("USMOS")

        self.assertTrue(result["has_contradictions"])
        self.assertEqual(result["message"], "Potential contradiction detected.")
        self.assertEqual(result["contradictions"][0]["topic"], "database")
        self.assertIn("SQLite", result["contradictions"][0]["values"])
        self.assertIn("PostgreSQL", result["contradictions"][0]["values"])

    def test_explain_memory_selection_returns_evidence_trace(self):
        explanation = explain_memory_selection("Why are we using SQLite?")

        self.assertTrue(explanation["success"])
        self.assertIn("storage", explanation["topic"])
        self.assertGreater(len(explanation["selected_memory_ids"]), 0)
        self.assertGreater(len(explanation["evidence_trace"]), 0)

        first_evidence = explanation["evidence_trace"][0]

        self.assertIn("memory_id", first_evidence)
        self.assertIn("selection_reason", first_evidence)
        self.assertIn("trust_explanation", first_evidence)
        self.assertIn("trust = importance", first_evidence["trust_explanation"])

    def test_answer_with_reasoning_includes_memory_ids_and_trust(self):
        answer = answer_with_reasoning("Why are we using SQLite?")

        self.assertIn("Answer:", answer)
        self.assertIn("Memory IDs:", answer)
        self.assertIn("Evidence Trace:", answer)
        self.assertIn("Memory #", answer)
        self.assertIn("Trust: trust = importance", answer)
        self.assertIn("Selected because:", answer)

    def test_answer_with_reasoning_warns_about_relevant_contradiction(self):
        create_decision(
            title="Alternative Database Decision",
            content="Database = PostgreSQL.",
            metadata={
                "project": "USMOS",
                "topic": "storage"
            },
            importance=7,
            confidence=80,
            source="user"
        )

        answer = answer_with_reasoning("Why are we using SQLite?")

        self.assertIn("Contradiction Warning:", answer)
        self.assertIn("PostgreSQL", answer)
        self.assertIn("SQLite", answer)
        self.assertIn("Related memory IDs:", answer)

    def seed_phase_checkpoints(self):
        phases = [
            (
                "USMOS Phase 1 Memory Foundation Complete",
                "USMOS Phase 1 completed memory storage and SQLite foundations.",
                "Phase 1",
                "Phase 1 Memory Foundation"
            ),
            (
                "USMOS Phase 2 Recall Context Builder Complete",
                "USMOS Phase 2 completed recall and context builder.",
                "Phase 2",
                "Phase 2 Recall + Context Builder"
            ),
            (
                "USMOS Phase 3 Memory Answer Snapshot Restore Complete",
                "USMOS Phase 3 completed memory answers and snapshot restore.",
                "Phase 3",
                "Phase 3 Memory Answer + Snapshot Restore"
            ),
            (
                "USMOS Phase 4 Memory Quality Layer Complete",
                "USMOS Phase 4 completed confidence, source, freshness, trust, and contradiction checks.",
                "Phase 4",
                "Phase 4 Memory Quality Layer"
            ),
            (
                "USMOS Phase 5 Explainable Memory Reasoning Complete",
                "USMOS Phase 5 completed explainable evidence traces and memory IDs.",
                "Phase 5",
                "Phase 5 Explainable Memory Reasoning"
            )
        ]

        for title, content, phase, completed_phase in phases:
            create_checkpoint(
                title=title,
                content=content,
                metadata={
                    "project": "USMOS",
                    "phase": phase,
                    "completed_phase": completed_phase,
                    "memory_scope": "real",
                    "topic": "project_status"
                },
                importance=10
            )

    def test_get_latest_checkpoint_selects_newest_checkpoint(self):
        self.seed_phase_checkpoints()

        latest_checkpoint = get_latest_checkpoint("USMOS")

        self.assertIsNotNone(latest_checkpoint)
        self.assertEqual(
            latest_checkpoint["title"],
            "USMOS Phase 5 Explainable Memory Reasoning Complete"
        )

    def test_project_phase_summary_returns_completed_phases(self):
        self.seed_phase_checkpoints()

        summary = get_project_phase_summary("USMOS")

        self.assertEqual(summary["project"], "USMOS")
        self.assertEqual(
            summary["latest_checkpoint"]["title"],
            "USMOS Phase 5 Explainable Memory Reasoning Complete"
        )
        self.assertIn(
            "Phase 1 Memory Foundation",
            summary["completed_phases"]
        )
        self.assertIn(
            "Phase 5 Explainable Memory Reasoning",
            summary["completed_phases"]
        )
        self.assertEqual(
            summary["current_phase"],
            "Phase 6 Project State Recovery Engine"
        )
        self.assertGreater(summary["memory_count"], 0)
        self.assertGreater(len(summary["highest_trust_memories"]), 0)

    def test_recover_project_state_includes_latest_checkpoint(self):
        self.seed_phase_checkpoints()

        recovery = recover_project_state("USMOS")

        self.assertIn("USMOS Project State Recovery", recovery)
        self.assertIn("Latest checkpoint:", recovery)
        self.assertIn(
            "USMOS Phase 5 Explainable Memory Reasoning Complete",
            recovery
        )
        self.assertIn("Phase 6 Project State Recovery Engine", recovery)

    def test_recover_project_state_includes_completed_phases(self):
        self.seed_phase_checkpoints()

        recovery = recover_project_state("USMOS")

        self.assertIn("- Phase 1 Memory Foundation", recovery)
        self.assertIn("- Phase 2 Recall + Context Builder", recovery)
        self.assertIn("- Phase 3 Memory Answer + Snapshot Restore", recovery)
        self.assertIn("- Phase 4 Memory Quality Layer", recovery)
        self.assertIn("- Phase 5 Explainable Memory Reasoning", recovery)

    def test_state_question_routes_to_recovery_output(self):
        self.seed_phase_checkpoints()

        answer = answer_project_state_question(
            "What phase are we in?"
        )

        self.assertIn("USMOS Project State Recovery", answer)
        self.assertIn("Current focus:", answer)
        self.assertIn("Phase 6 Project State Recovery Engine", answer)
