import json
import tempfile
import unittest
from pathlib import Path

from src.memory import memory_engine
from src.memory.memory_engine import (
    answer_from_memory,
    batch_create_memories,
    batch_index_memory_keywords,
    benchmark_ingestion,
    benchmark_recall,
    benchmark_recall_index,
    benchmark_token_ingestion,
    create_decision,
    estimate_token_count,
    generate_benchmark_file,
    generate_token_benchmark_file,
    list_memories_by_project,
    read_memory,
    run_benchmark_suite,
)
from src.storage import database
from src.storage.schema import initialize_schema


class BenchmarkEngineTests(unittest.TestCase):

    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.original_snapshot_dir = memory_engine.SNAPSHOT_DIR
        self.original_benchmark_dir = memory_engine.BENCHMARK_DIR
        self.original_benchmark_report_dir = memory_engine.BENCHMARK_REPORT_DIR
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

        database.DB_PATH = self.temp_path / "sandbox" / "data" / "usmos.db"
        memory_engine.SNAPSHOT_DIR = self.temp_path / "sandbox" / "snapshots"
        memory_engine.BENCHMARK_DIR = self.temp_path / "sandbox" / "benchmarks"
        memory_engine.BENCHMARK_REPORT_DIR = (
            self.temp_path / "sandbox" / "benchmark_reports"
        )

        initialize_schema()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        memory_engine.SNAPSHOT_DIR = self.original_snapshot_dir
        memory_engine.BENCHMARK_DIR = self.original_benchmark_dir
        memory_engine.BENCHMARK_REPORT_DIR = self.original_benchmark_report_dir
        self.temp_dir.cleanup()

    def test_generate_benchmark_file_creates_requested_lines(self):
        output_path = self.temp_path / "benchmarks" / "ScaleTest_20.md"

        result = generate_benchmark_file(
            output_path=output_path,
            project_name="ScaleTest",
            memory_count=20
        )

        lines = output_path.read_text(encoding="utf-8").splitlines()

        self.assertTrue(result["success"])
        self.assertEqual(result["memory_count"], 20)
        self.assertEqual(len(lines), 20)
        self.assertTrue(lines[0].startswith("Decision:"))
        self.assertTrue(lines[1].startswith("Task:"))
        self.assertTrue(lines[2].startswith("Checkpoint:"))
        self.assertTrue(lines[3].startswith("Event:"))
        self.assertTrue(lines[4].startswith("Fact:"))

    def test_estimate_token_count_uses_word_split(self):
        self.assertEqual(estimate_token_count("one two three"), 3)
        self.assertEqual(estimate_token_count("  one   two  "), 2)
        self.assertEqual(estimate_token_count(""), 0)

    def test_generate_token_benchmark_file_reaches_target_tokens(self):
        output_path = self.temp_path / "benchmarks" / "TokenTest_1000_tokens.md"

        result = generate_token_benchmark_file(
            output_path=output_path,
            project_name="TokenTest",
            target_tokens=1000
        )
        lines = output_path.read_text(encoding="utf-8").splitlines()

        self.assertTrue(result["success"])
        self.assertTrue(output_path.exists())
        self.assertGreaterEqual(result["estimated_tokens_generated"], 1000)
        self.assertEqual(result["line_count"], len(lines))
        self.assertTrue(lines[0].startswith("Decision:"))
        self.assertTrue(lines[1].startswith("Task:"))
        self.assertTrue(lines[2].startswith("Checkpoint:"))
        self.assertGreater(result["file_size_mb"], 0)

    def test_keywords_created_for_memory(self):
        result = create_decision(
            title="ScaleTest Cloud Rule",
            content="Decision: ScaleTest must avoid cloud APIs.",
            metadata={
                "project": "ScaleTest",
                "topic": "security",
                "memory_scope": "real"
            }
        )
        memory = read_memory(result["memory_id"])
        conn = database.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
        SELECT keyword
        FROM memory_keywords
        WHERE memory_id = ?
        """, (memory["id"],))

        keywords = []

        for row in cursor.fetchall():
            keywords.append(row[0])

        conn.close()

        self.assertIn("decision", keywords)
        self.assertIn("cloud", keywords)
        self.assertIn("api", keywords)
        self.assertIn("security", keywords)

    def test_indexed_recall_finds_cloud_question(self):
        create_decision(
            title="ScaleTest Cloud Rule",
            content="Decision: ScaleTest must avoid cloud APIs.",
            metadata={
                "project": "ScaleTest",
                "memory_scope": "real"
            }
        )

        result = benchmark_recall_index(
            project_name="ScaleTest",
            questions=[
                "Does ScaleTest use cloud?"
            ]
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["results"][0]["answer_found"])
        self.assertGreater(result["results"][0]["memory_count"], 0)

    def test_batch_create_memories_creates_multiple_memories(self):
        result = batch_create_memories([
            {
                "memory_type": "decision",
                "title": "Batch Decision",
                "content": "Decision: BatchProject must stay local.",
                "metadata": {
                    "project": "BatchProject",
                    "memory_scope": "real"
                },
                "importance": 8,
                "confidence": 100,
                "source": "document_ingestion"
            },
            {
                "memory_type": "task",
                "title": "Batch Task",
                "content": "Task: build batch keyword indexing.",
                "metadata": {
                    "project": "BatchProject",
                    "memory_scope": "real"
                },
                "importance": 6,
                "confidence": 100,
                "source": "document_ingestion"
            }
        ])

        memories = list_memories_by_project("BatchProject")

        self.assertTrue(result["success"])
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["duplicates"], 0)
        self.assertEqual(len(result["created_ids"]), 2)
        self.assertEqual(len(memories), 2)

    def test_batch_create_memories_skips_duplicate_content_hashes(self):
        first_result = batch_create_memories([
            {
                "memory_type": "decision",
                "title": "Batch Duplicate Decision",
                "content": "Decision: BatchProject must avoid cloud APIs.",
                "metadata": {
                    "project": "BatchProject",
                    "memory_scope": "real"
                },
                "importance": 8,
                "confidence": 100,
                "source": "document_ingestion"
            }
        ])
        second_result = batch_create_memories([
            {
                "memory_type": "decision",
                "title": "Same Content With New Title",
                "content": "Decision: BatchProject must avoid cloud APIs.",
                "metadata": {
                    "project": "BatchProject",
                    "memory_scope": "real"
                },
                "importance": 8,
                "confidence": 100,
                "source": "document_ingestion"
            }
        ])

        self.assertEqual(first_result["created"], 1)
        self.assertEqual(second_result["created"], 0)
        self.assertEqual(second_result["duplicates"], 1)
        self.assertEqual(len(list_memories_by_project("BatchProject")), 1)

    def test_batch_keyword_index_creates_keywords(self):
        result = batch_create_memories([
            {
                "memory_type": "decision",
                "title": "Batch Cloud Rule",
                "content": "Decision: BatchProject must avoid cloud APIs.",
                "metadata": {
                    "project": "BatchProject",
                    "topic": "security",
                    "memory_scope": "real"
                },
                "importance": 8,
                "confidence": 100,
                "source": "document_ingestion"
            }
        ])
        memory_id = result["created_ids"][0]
        conn = database.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
        DELETE FROM memory_keywords
        WHERE memory_id = ?
        """, (memory_id,))
        conn.commit()
        conn.close()

        index_result = batch_index_memory_keywords([memory_id])
        conn = database.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
        SELECT keyword
        FROM memory_keywords
        WHERE memory_id = ?
        """, (memory_id,))

        keywords = []

        for row in cursor.fetchall():
            keywords.append(row[0])

        conn.close()

        self.assertTrue(index_result["success"])
        self.assertEqual(index_result["memory_count"], 1)
        self.assertIn("cloud", keywords)
        self.assertIn("api", keywords)
        self.assertIn("security", keywords)

    def test_recall_fallback_still_works_without_keywords(self):
        memory_result = create_decision(
            title="FallbackProject Cloud Rule",
            content="Decision: FallbackProject must avoid cloud APIs.",
            metadata={
                "project": "FallbackProject",
                "memory_scope": "real"
            }
        )
        conn = database.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
        DELETE FROM memory_keywords
        WHERE memory_id = ?
        """, (memory_result["memory_id"],))

        conn.commit()
        conn.close()

        answer = answer_from_memory(
            "Does FallbackProject use cloud?",
            project_name="FallbackProject"
        )

        self.assertIn("avoid cloud APIs", answer)

    def test_benchmark_ingestion_returns_duration(self):
        output_path = self.temp_path / "benchmarks" / "ScaleTest_10.md"
        generate_benchmark_file(
            output_path=output_path,
            project_name="ScaleTest",
            memory_count=10
        )

        result = benchmark_ingestion(
            file_path=output_path,
            project_name="ScaleTest"
        )

        self.assertTrue(result["success"])
        self.assertIn("duration_seconds", result)
        self.assertIn("parse_duration", result)
        self.assertIn("duplicate_check_duration", result)
        self.assertIn("insert_duration", result)
        self.assertIn("keyword_index_duration", result)
        self.assertIn("total_duration", result)
        self.assertEqual(result["created"], 10)
        self.assertEqual(result["duplicates"], 0)
        self.assertEqual(result["total_memories_after"], 10)

    def test_benchmark_ingestion_1000_still_passes(self):
        output_path = self.temp_path / "benchmarks" / "ScaleTest_1000.md"
        generate_benchmark_file(
            output_path=output_path,
            project_name="ScaleTest",
            memory_count=1000
        )

        first_result = benchmark_ingestion(
            file_path=output_path,
            project_name="ScaleTest"
        )
        second_result = benchmark_ingestion(
            file_path=output_path,
            project_name="ScaleTest"
        )

        self.assertTrue(first_result["success"])
        self.assertEqual(first_result["created"], 1000)
        self.assertEqual(first_result["duplicates"], 0)
        self.assertIn("keyword_index_duration", first_result)
        self.assertTrue(second_result["success"])
        self.assertEqual(second_result["created"], 0)
        self.assertEqual(second_result["duplicates"], 1000)
        self.assertEqual(second_result["total_memories_after"], 1000)

    def test_benchmark_recall_returns_results(self):
        output_path = self.temp_path / "benchmarks" / "ScaleTest_20.md"
        generate_benchmark_file(
            output_path=output_path,
            project_name="ScaleTest",
            memory_count=20
        )
        benchmark_ingestion(
            file_path=output_path,
            project_name="ScaleTest"
        )

        result = benchmark_recall(
            project_name="ScaleTest",
            questions=[
                "Does ScaleTest use cloud?",
                "What checkpoints are completed for ScaleTest?"
            ]
        )

        self.assertTrue(result["success"])
        self.assertEqual(len(result["results"]), 2)
        self.assertTrue(result["results"][0]["answer_found"])
        self.assertIn("duration_seconds", result["results"][0])
        self.assertIn("avoid cloud APIs", result["results"][0]["answer"])

    def test_run_benchmark_suite_small_count(self):
        result = run_benchmark_suite(
            project_name="ScaleTest",
            memory_count=20
        )
        report_path = Path(result["report_file"])

        self.assertTrue(result["success"])
        self.assertTrue(Path(result["generated_file"]["file"]).exists())
        self.assertTrue(report_path.exists())
        self.assertEqual(result["ingestion"]["created"], 20)
        self.assertEqual(result["duplicate_ingestion"]["created"], 0)
        self.assertEqual(result["duplicate_ingestion"]["duplicates"], 20)
        self.assertTrue(result["recall"]["success"])
        self.assertTrue(result["recall_index"]["success"])
        self.assertTrue(result["snapshot"]["success"])
        self.assertTrue(result["restore"]["success"])

        report_data = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(report_data["project"], "ScaleTest")
        self.assertEqual(report_data["memory_count"], 20)
        self.assertIn("report_file", report_data)
        self.assertEqual(len(list_memories_by_project("ScaleTest")), 20)

    def test_token_benchmark_suite_small_token_count(self):
        result = benchmark_token_ingestion(
            project_name="TokenTest",
            target_tokens=1000
        )
        report_path = Path(result["report_file"])

        self.assertTrue(result["success"])
        self.assertTrue(report_path.exists())
        self.assertEqual(result["target_tokens"], 1000)
        self.assertGreaterEqual(result["estimated_tokens_generated"], 1000)
        self.assertGreater(result["file_size_mb"], 0)
        self.assertIn("ingest_duration", result)
        self.assertIn("duplicate_duration", result)
        self.assertIn("recall_duration", result)
        self.assertIn("snapshot_size_mb", result)
        self.assertIn("db_size_mb", result)
        self.assertEqual(result["duplicate_ingestion"]["created"], 0)

        report_data = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(report_data["project"], "TokenTest")
        self.assertEqual(report_data["target_tokens"], 1000)
