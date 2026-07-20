import tempfile
import unittest
from pathlib import Path

from src.conversation.conversation_analyzer import analyze_conversation_for_memory
from src.conversation.conversation_memory import (
    preview_memory_candidates,
    save_approved_memory,
)
from src.conversation.conversation_queue import (
    APPROVED_STATUS,
    PENDING_STATUS,
    REJECTED_STATUS,
    approve_pending_memories,
    approve_pending_memory,
    get_conversation_history,
    list_pending_memory_items,
    queue_conversation_memory_candidates,
    reject_pending_memory,
)
from src.llm.context_builder import build_llm_context
from src.memory import memory_engine
from src.memory.memory_engine import (
    create_decision,
    list_memories_by_project,
    read_memory,
)
from src.storage import database
from src.storage.schema import initialize_schema


class ConversationMemoryTests(unittest.TestCase):

    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.original_current_project_file = memory_engine.CURRENT_PROJECT_FILE
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        database.DB_PATH = self.temp_path / "sandbox" / "data" / "usmos.db"
        memory_engine.CURRENT_PROJECT_FILE = (
            self.temp_path / "sandbox" / "current_project.json"
        )

        initialize_schema()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        memory_engine.CURRENT_PROJECT_FILE = self.original_current_project_file
        self.temp_dir.cleanup()

    def test_analyzer_detects_decision_task_and_checkpoint(self):
        decision = analyze_conversation_for_memory(
            "We decided MiniOffice will use PostgreSQL instead of SQLite.",
            project_name="MiniOffice"
        )
        task = analyze_conversation_for_memory(
            "Next step: build the export command.",
            project_name="MiniOffice"
        )
        checkpoint = analyze_conversation_for_memory(
            "Phase 16 passed tests and is stable.",
            project_name="MiniOffice"
        )

        self.assertEqual(decision["candidates"][0]["memory_type"], "decision")
        self.assertEqual(task["candidates"][0]["memory_type"], "task")
        self.assertEqual(
            checkpoint["candidates"][0]["memory_type"],
            "checkpoint"
        )
        self.assertTrue(decision["candidates"][0]["requires_approval"])

    def test_preview_shows_candidates(self):
        analysis = analyze_conversation_for_memory(
            "We decided MiniOffice will use SQLite.",
            project_name="MiniOffice"
        )

        preview = preview_memory_candidates(analysis)

        self.assertIn("Potential memories detected:", preview)
        self.assertIn("Decision", preview)
        self.assertIn("Save? yes/no/edit", preview)

    def test_save_approved_memory_saves_with_conversation_metadata(self):
        analysis = analyze_conversation_for_memory(
            "We decided MiniOffice will use SQLite.",
            project_name="MiniOffice"
        )
        candidate = analysis["candidates"][0]

        result = save_approved_memory(candidate, approved=True)
        memory = read_memory(result["memory_id"])

        self.assertTrue(result["saved"])
        self.assertEqual(memory["source"], "conversation")
        self.assertEqual(memory["metadata"]["source"], "conversation")
        self.assertTrue(memory["metadata"]["conversation_approved"])
        self.assertEqual(memory["metadata"]["created_from"], "conversation")
        self.assertIn("conversation_session_id", memory["metadata"])
        self.assertEqual(memory["importance"], 9)
        self.assertEqual(memory["confidence"], 100)
        self.assertEqual(memory["trust_score"], 145)

    def test_rejected_candidate_is_not_saved(self):
        analysis = analyze_conversation_for_memory(
            "We decided MiniOffice will use SQLite.",
            project_name="MiniOffice"
        )
        before_count = len(list_memories_by_project("MiniOffice"))

        result = save_approved_memory(
            analysis["candidates"][0],
            approved=False
        )
        after_count = len(list_memories_by_project("MiniOffice"))

        self.assertFalse(result["saved"])
        self.assertEqual(before_count, after_count)

    def test_edited_candidate_saves_edited_title_and_content(self):
        analysis = analyze_conversation_for_memory(
            "We decided MiniOffice will use SQLite.",
            project_name="MiniOffice"
        )

        result = save_approved_memory(
            analysis["candidates"][0],
            approved=True,
            edited_title="MiniOffice Final Storage Decision",
            edited_content="MiniOffice will use SQLite for local storage."
        )
        memory = read_memory(result["memory_id"])

        self.assertEqual(memory["title"], "MiniOffice Final Storage Decision")
        self.assertEqual(
            memory["content"],
            "MiniOffice will use SQLite for local storage."
        )

    def test_supersession_candidate_detected_but_not_auto_applied(self):
        old_result = create_decision(
            title="MiniOffice SQLite Decision",
            content="MiniOffice uses SQLite for local storage.",
            metadata={"project": "MiniOffice"}
        )

        analysis = analyze_conversation_for_memory(
            "We decided MiniOffice will use PostgreSQL instead of SQLite.",
            project_name="MiniOffice"
        )
        candidate = analysis["candidates"][0]

        self.assertTrue(candidate["possible_supersedes"])

        save_approved_memory(candidate, approved=True)
        old_memory = read_memory(old_result["memory_id"])

        self.assertEqual(old_memory["status"], "active")

    def test_supersession_ranks_sqlite_above_unrelated_decisions(self):
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

        analysis = analyze_conversation_for_memory(
            "We decided MiniOffice will use PostgreSQL instead of SQLite.",
            project_name="MiniOffice"
        )
        candidate = analysis["candidates"][0]

        self.assertEqual(
            candidate["possible_supersedes"][0]["memory_id"],
            sqlite_result["memory_id"]
        )
        self.assertNotEqual(
            candidate["possible_supersedes"][0]["memory_id"],
            approval_result["memory_id"]
        )
        self.assertNotEqual(
            candidate["possible_supersedes"][0]["memory_id"],
            cloud_result["memory_id"]
        )

    def test_supersession_application_hides_old_sqlite_from_active_recall(self):
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
        analysis = analyze_conversation_for_memory(
            "We decided MiniOffice will use PostgreSQL instead of SQLite.",
            project_name="MiniOffice"
        )
        candidate = analysis["candidates"][0]

        save_result = save_approved_memory(
            candidate,
            approved=True,
            supersede_memory_id=sqlite_result["memory_id"],
            approve_supersede=True
        )
        active_memories = list_memories_by_project("MiniOffice")
        history_memories = list_memories_by_project(
            "MiniOffice",
            include_history=True
        )
        context = build_llm_context(
            question="What database does MiniOffice use?",
            project_name="MiniOffice",
            max_memories=5
        )

        self.assertTrue(save_result["superseded"])
        self.assertEqual(read_memory(sqlite_result["memory_id"])["status"], "superseded")
        self.assertEqual(read_memory(approval_result["memory_id"])["status"], "active")
        self.assertEqual(read_memory(cloud_result["memory_id"])["status"], "active")
        self.assertNotIn(
            sqlite_result["memory_id"],
            [memory["id"] for memory in active_memories]
        )
        self.assertIn(
            sqlite_result["memory_id"],
            [memory["id"] for memory in history_memories]
        )
        self.assertIn("PostgreSQL", context["selected_memories"][0]["content"])
        self.assertNotEqual(
            context["selected_memories"][0]["memory_id"],
            sqlite_result["memory_id"]
        )

    def test_duplicate_conversation_memory_can_apply_supersession(self):
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
        analysis = analyze_conversation_for_memory(
            "We decided MiniOffice will use PostgreSQL instead of SQLite.",
            project_name="MiniOffice"
        )
        candidate = analysis["candidates"][0]
        duplicate_result = create_decision(
            title=candidate["title"],
            content=candidate["content"],
            metadata={"project": "MiniOffice"},
            importance=4,
            confidence=60,
            source="user"
        )

        analysis = analyze_conversation_for_memory(
            "We decided MiniOffice will use PostgreSQL instead of SQLite.",
            project_name="MiniOffice"
        )
        candidate = analysis["candidates"][0]
        self.assertEqual(
            candidate["possible_supersedes"][0]["memory_id"],
            sqlite_result["memory_id"]
        )

        save_result = save_approved_memory(
            candidate,
            approved=True,
            supersede_memory_id=sqlite_result["memory_id"],
            approve_supersede=True
        )
        duplicate_memory = read_memory(duplicate_result["memory_id"])
        context = build_llm_context(
            question="What database does MiniOffice use?",
            project_name="MiniOffice",
            max_memories=5
        )

        self.assertTrue(save_result["duplicate_reused"])
        self.assertEqual(save_result["memory_id"], duplicate_result["memory_id"])
        self.assertTrue(save_result["superseded"])
        self.assertEqual(duplicate_memory["source"], "conversation")
        self.assertTrue(duplicate_memory["metadata"]["conversation_approved"])
        self.assertEqual(duplicate_memory["importance"], 9)
        self.assertEqual(duplicate_memory["confidence"], 100)
        self.assertEqual(duplicate_memory["trust_score"], 145)
        self.assertEqual(read_memory(sqlite_result["memory_id"])["status"], "superseded")
        self.assertEqual(read_memory(approval_result["memory_id"])["status"], "active")
        self.assertEqual(read_memory(cloud_result["memory_id"])["status"], "active")
        self.assertIn("PostgreSQL", context["selected_memories"][0]["content"])

    def test_queue_creation_stores_pending_item_and_history(self):
        result = queue_conversation_memory_candidates(
            user_message="We decided MiniOffice will use SQLite.",
            project_name="MiniOffice"
        )
        pending_items = list_pending_memory_items(
            project_name="MiniOffice",
            status=PENDING_STATUS
        )
        history = get_conversation_history(result["conversation_id"])

        self.assertTrue(result["success"])
        self.assertEqual(result["created"], 1)
        self.assertEqual(len(pending_items), 1)
        self.assertEqual(pending_items[0]["approval_status"], PENDING_STATUS)
        self.assertEqual(history["original_sentence"], "We decided MiniOffice will use SQLite.")
        self.assertEqual(history["approved_memory_ids"], [])

    def test_approve_pending_memory_saves_memory_and_updates_history(self):
        result = queue_conversation_memory_candidates(
            user_message="We decided MiniOffice will use SQLite.",
            project_name="MiniOffice"
        )
        pending_id = result["pending_items"][0]["pending_id"]

        approval = approve_pending_memory(pending_id)
        item = list_pending_memory_items(
            project_name="MiniOffice",
            status=APPROVED_STATUS
        )[0]
        history = get_conversation_history(result["conversation_id"])
        memory = read_memory(approval["memory_id"])

        self.assertTrue(approval["success"])
        self.assertEqual(item["approval_status"], APPROVED_STATUS)
        self.assertEqual(item["approved_memory_id"], approval["memory_id"])
        self.assertIn(approval["memory_id"], history["approved_memory_ids"])
        self.assertEqual(memory["source"], "conversation")

    def test_reject_pending_memory_keeps_audit_history(self):
        result = queue_conversation_memory_candidates(
            user_message="Next step: build the export command.",
            project_name="MiniOffice"
        )
        pending_id = result["pending_items"][0]["pending_id"]

        rejection = reject_pending_memory(pending_id)
        rejected_items = list_pending_memory_items(
            project_name="MiniOffice",
            status=REJECTED_STATUS
        )

        self.assertTrue(rejection["success"])
        self.assertEqual(len(rejected_items), 1)
        self.assertEqual(rejected_items[0]["pending_id"], pending_id)

    def test_queue_duplicate_prevention(self):
        first = queue_conversation_memory_candidates(
            user_message="We decided MiniOffice will use SQLite.",
            project_name="MiniOffice"
        )
        second = queue_conversation_memory_candidates(
            user_message="We decided MiniOffice will use SQLite.",
            project_name="MiniOffice"
        )

        self.assertEqual(first["created"], 1)
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["duplicates"], 1)
        self.assertEqual(
            len(list_pending_memory_items(project_name="MiniOffice")),
            1
        )

    def test_batch_approval_approves_many_pending_memories(self):
        queue_conversation_memory_candidates(
            user_message=(
                "We decided MiniOffice will use SQLite. "
                "Next step: build the export command."
            ),
            project_name="MiniOffice"
        )

        result = approve_pending_memories(project_name="MiniOffice")
        approved_items = list_pending_memory_items(
            project_name="MiniOffice",
            status=APPROVED_STATUS
        )
        active_memories = list_memories_by_project("MiniOffice")

        self.assertEqual(result["count"], 2)
        self.assertEqual(len(approved_items), 2)
        self.assertEqual(len(active_memories), 2)

    def test_approve_pending_type_approves_only_that_memory_type(self):
        queue_conversation_memory_candidates(
            user_message=(
                "We decided MiniOffice will use SQLite. "
                "Next step: build the export command."
            ),
            project_name="MiniOffice"
        )

        result = approve_pending_memories(
            project_name="MiniOffice",
            memory_type="decision"
        )
        approved_items = list_pending_memory_items(
            project_name="MiniOffice",
            status=APPROVED_STATUS
        )
        pending_items = list_pending_memory_items(
            project_name="MiniOffice",
            status=PENDING_STATUS
        )

        self.assertEqual(result["count"], 1)
        self.assertEqual(approved_items[0]["memory_type"], "decision")
        self.assertEqual(pending_items[0]["memory_type"], "task")

    def test_pending_approval_applies_supersession(self):
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
        result = queue_conversation_memory_candidates(
            user_message="We decided MiniOffice will use PostgreSQL instead of SQLite.",
            project_name="MiniOffice"
        )
        pending_item = result["pending_items"][0]

        approval = approve_pending_memory(pending_item["pending_id"])
        context = build_llm_context(
            question="What database does MiniOffice use?",
            project_name="MiniOffice",
            max_memories=5
        )

        self.assertTrue(approval["success"])
        self.assertTrue(approval["superseded"])
        self.assertEqual(read_memory(sqlite_result["memory_id"])["status"], "superseded")
        self.assertEqual(read_memory(approval_result["memory_id"])["status"], "active")
        self.assertEqual(read_memory(cloud_result["memory_id"])["status"], "active")
        self.assertIn("PostgreSQL", context["selected_memories"][0]["content"])


if __name__ == "__main__":
    unittest.main()
