import tempfile
import unittest
from pathlib import Path

from src.llm import context_builder
from src.llm import conversation_bridge
from src.llm import ollama_client
from src.llm.context_builder import build_context_package
from src.llm.context_builder import build_llm_context
from src.llm.context_builder import score_fast_llm_memory
from src.llm.conversation_bridge import build_prompt
from src.llm.conversation_bridge import SYSTEM_PROMPT
from src.memory import memory_engine
from src.memory.memory_engine import (
    create_checkpoint,
    create_decision,
    create_event,
    create_project_note,
    create_task,
)
from src.storage import database
from src.storage.schema import initialize_schema


class LocalLlmBridgeTests(unittest.TestCase):

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
        self.seed_minioffice_memories()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        memory_engine.CURRENT_PROJECT_FILE = self.original_current_project_file
        self.temp_dir.cleanup()

    def seed_minioffice_memories(self):
        metadata = {
            "project": "MiniOffice",
            "memory_scope": "real",
            "topic": "security"
        }

        create_decision(
            title="MiniOffice Security Model",
            content="Decision: MiniOffice uses local-only sandbox memory.",
            metadata=metadata,
            importance=10,
            confidence=95,
            source="user"
        )
        create_decision(
            title="MiniOffice No Cloud Rule",
            content="Decision: MiniOffice must run local-only with no cloud access.",
            metadata=metadata,
            importance=8,
            confidence=100,
            source="user"
        )
        create_decision(
            title="MiniOffice SQLite Storage",
            content="Decision: MiniOffice will use SQLite for local storage.",
            metadata=metadata,
            importance=8,
            confidence=100,
            source="user"
        )
        create_project_note(
            title="MiniOffice Snapshot Path",
            content="Fact: MiniOffice snapshots are stored in sandbox/snapshots.",
            metadata=metadata,
            importance=8,
            confidence=100,
            source="user"
        )
        create_decision(
            title="MiniOffice File Approval",
            content="Decision: MiniOffice will require human approval before deleting files.",
            metadata=metadata,
            importance=8,
            confidence=100,
            source="user"
        )
        create_checkpoint(
            title="MiniOffice Security Checkpoint",
            content="Checkpoint: MiniOffice security model was verified locally.",
            metadata=metadata,
            importance=9,
            confidence=90,
            source="checkpoint"
        )
        create_project_note(
            title="MiniOffice Security Fact",
            content="Fact: MiniOffice does not send memory to cloud services.",
            metadata=metadata,
            importance=8,
            confidence=90,
            source="user"
        )
        create_task(
            title="MiniOffice Security Task",
            content="Task: MiniOffice must document the local security checklist.",
            metadata=metadata,
            importance=7,
            confidence=90,
            source="user"
        )
        create_event(
            title="MiniOffice Security Event",
            content="Event: MiniOffice local security review passed.",
            metadata=metadata,
            importance=6,
            confidence=90,
            source="user"
        )

    def test_context_builder_reuses_memory_selection(self):
        context = build_context_package(
            question="What security model does MiniOffice use?",
            project_name="MiniOffice"
        )

        self.assertTrue(context["success"])
        self.assertEqual(context["project"], "MiniOffice")
        self.assertEqual(
            context["question"],
            "What security model does MiniOffice use?"
        )
        self.assertGreater(len(context["selected_memories"]), 0)
        self.assertGreater(len(context["evidence"]), 0)
        self.assertEqual(len(context["memory_ids"]), len(context["evidence"]))

    def test_compact_context_contains_no_trust_formula(self):
        context = build_llm_context(
            question="What security model does MiniOffice use?",
            project_name="MiniOffice",
            max_memories=5
        )
        context_text = context["context_text"]

        self.assertIn("Project:", context_text)
        self.assertIn("Evidence:", context_text)
        self.assertIn("MiniOffice uses local-only sandbox memory", context_text)
        self.assertIn("trust", context_text)
        self.assertNotIn("trust =", context_text)
        self.assertNotIn("trust_explanation", context_text)
        self.assertNotIn("selection_reason", context_text)

    def test_compact_context_does_not_call_full_context_package(self):
        original_build_context_package = context_builder.build_context_package

        def fail_if_called(*args, **kwargs):
            raise AssertionError("compact context should not use full context package")

        context_builder.build_context_package = fail_if_called

        try:
            context = context_builder.build_llm_context(
                question="What security model does MiniOffice use?",
                project_name="MiniOffice",
                max_memories=3
            )
        finally:
            context_builder.build_context_package = original_build_context_package

        self.assertGreater(len(context["memory_ids"]), 0)

    def test_compact_context_does_not_call_explain_memory_selection(self):
        original_explain_memory_selection = context_builder.explain_memory_selection

        def fail_if_called(*args, **kwargs):
            raise AssertionError("compact context should not explain memory selection")

        context_builder.explain_memory_selection = fail_if_called

        try:
            context = context_builder.build_llm_context(
                question="What security model does MiniOffice use?",
                project_name="MiniOffice",
                max_memories=3
            )
        finally:
            context_builder.explain_memory_selection = original_explain_memory_selection

        self.assertGreater(len(context["memory_ids"]), 0)

    def test_compact_context_limits_memory_count(self):
        context = build_llm_context(
            question="What security model does MiniOffice use?",
            project_name="MiniOffice",
            max_memories=2
        )

        self.assertEqual(len(context["selected_memories"]), 2)
        self.assertEqual(len(context["evidence"]), 2)
        self.assertEqual(len(context["memory_ids"]), 2)

    def test_compact_context_respects_memory_type_intent(self):
        expected_types = {
            "What tasks are stored for MiniOffice?": "task",
            "What checkpoint is stored for MiniOffice?": "checkpoint",
            "What decision is stored for MiniOffice?": "decision",
            "What event is stored for MiniOffice?": "event",
            "What fact is stored for MiniOffice?": "project_note"
        }

        for question, expected_type in expected_types.items():
            with self.subTest(question=question):
                context = build_llm_context(
                    question=question,
                    project_name="MiniOffice",
                    max_memories=3
                )

                self.assertGreater(len(context["selected_memories"]), 0)

                for memory in context["selected_memories"]:
                    self.assertEqual(memory["memory_type"], expected_type)

    def test_compact_ranking_prioritizes_cloud_memory(self):
        context = build_llm_context(
            question="Does MiniOffice use cloud APIs?",
            project_name="MiniOffice",
            max_memories=3
        )

        self.assertGreater(len(context["selected_memories"]), 0)
        self.assertIn(
            "no cloud access",
            context["selected_memories"][0]["content"]
        )

    def test_compact_ranking_prioritizes_sqlite_memory(self):
        context = build_llm_context(
            question="Does MiniOffice use SQLite?",
            project_name="MiniOffice",
            max_memories=3
        )

        self.assertGreater(len(context["selected_memories"]), 0)
        self.assertIn(
            "SQLite for local storage",
            context["selected_memories"][0]["content"]
        )

    def test_compact_ranking_prioritizes_snapshot_path_memory(self):
        context = build_llm_context(
            question="Where are MiniOffice snapshots stored?",
            project_name="MiniOffice",
            max_memories=3
        )

        self.assertGreater(len(context["selected_memories"]), 0)
        self.assertIn(
            "sandbox/snapshots",
            context["selected_memories"][0]["content"]
        )

    def test_compact_ranking_prioritizes_approval_memory(self):
        context = build_llm_context(
            question="Does MiniOffice require human approval before deleting files?",
            project_name="MiniOffice",
            max_memories=3
        )

        self.assertGreater(len(context["selected_memories"]), 0)
        self.assertIn(
            "human approval before deleting files",
            context["selected_memories"][0]["content"]
        )

    def test_conversation_source_boost_improves_fast_score(self):
        user_memory = {
            "id": 1,
            "memory_type": "decision",
            "title": "MiniOffice Database",
            "content": "MiniOffice database uses PostgreSQL.",
            "metadata": {},
            "source": "user",
            "trust_score": 120
        }
        conversation_memory = user_memory.copy()
        conversation_memory["id"] = 2
        conversation_memory["source"] = "conversation"

        user_score = score_fast_llm_memory(
            memory=user_memory,
            question="What database does MiniOffice use?",
            question_keywords=["database", "minioffice"],
            priority_phrases=[],
            requested_memory_type=None
        )
        conversation_score = score_fast_llm_memory(
            memory=conversation_memory,
            question="What database does MiniOffice use?",
            question_keywords=["database", "minioffice"],
            priority_phrases=[],
            requested_memory_type=None
        )

        self.assertGreater(conversation_score[0], user_score[0])

    def test_instead_of_boost_improves_fast_score(self):
        normal_memory = {
            "id": 1,
            "memory_type": "decision",
            "title": "MiniOffice Database",
            "content": "MiniOffice database uses PostgreSQL.",
            "metadata": {},
            "source": "user",
            "trust_score": 120
        }
        supersession_memory = normal_memory.copy()
        supersession_memory["id"] = 2
        supersession_memory["content"] = (
            "MiniOffice database uses PostgreSQL instead of SQLite."
        )

        normal_score = score_fast_llm_memory(
            memory=normal_memory,
            question="What database does MiniOffice use?",
            question_keywords=["database", "minioffice"],
            priority_phrases=[],
            requested_memory_type=None
        )
        supersession_score = score_fast_llm_memory(
            memory=supersession_memory,
            question="What database does MiniOffice use?",
            question_keywords=["database", "minioffice"],
            priority_phrases=[],
            requested_memory_type=None
        )

        self.assertGreater(supersession_score[0], normal_score[0])

    def test_conversation_approved_boost_improves_fast_score(self):
        normal_memory = {
            "id": 1,
            "memory_type": "decision",
            "title": "MiniOffice Database",
            "content": "MiniOffice database uses PostgreSQL.",
            "metadata": {},
            "source": "user",
            "trust_score": 120
        }
        approved_memory = normal_memory.copy()
        approved_memory["id"] = 2
        approved_memory["metadata"] = {
            "conversation_approved": True
        }

        normal_score = score_fast_llm_memory(
            memory=normal_memory,
            question="What database does MiniOffice use?",
            question_keywords=["database", "minioffice"],
            priority_phrases=[],
            requested_memory_type=None
        )
        approved_score = score_fast_llm_memory(
            memory=approved_memory,
            question="What database does MiniOffice use?",
            question_keywords=["database", "minioffice"],
            priority_phrases=[],
            requested_memory_type=None
        )

        self.assertGreater(approved_score[0], normal_score[0])

    def test_compact_ranking_does_not_return_unrelated_kubernetes_evidence(self):
        context = build_llm_context(
            question="Does MiniOffice use Kubernetes?",
            project_name="MiniOffice",
            max_memories=3
        )

        self.assertEqual(context["selected_memories"], [])
        self.assertEqual(context["memory_ids"], [])
        self.assertIn("None.", context["context_text"])

    def test_compact_prompt_is_shorter_than_full_prompt(self):
        compact_context = build_llm_context(
            question="What security model does MiniOffice use?",
            project_name="MiniOffice",
            max_memories=3
        )
        full_context = build_context_package(
            question="What security model does MiniOffice use?",
            project_name="MiniOffice",
            max_results=3
        )
        compact_prompt = build_prompt(compact_context, mode="compact")
        full_prompt = build_prompt(full_context, mode="full")

        self.assertLess(len(compact_prompt), len(full_prompt))
        self.assertIn("USMOS Evidence Context", compact_prompt)
        self.assertIn("Trusted USMOS Context", full_prompt)
        self.assertIn("I do not have evidence for that.", compact_prompt)

    def test_prompt_contains_negative_evidence_rule(self):
        self.assertIn("local-only", SYSTEM_PROMPT)
        self.assertIn("no cloud access", SYSTEM_PROMPT)
        self.assertIn('answer "No"', SYSTEM_PROMPT)
        self.assertIn("negative evidence", SYSTEM_PROMPT)

    def test_cloud_api_question_with_no_cloud_evidence_answers_no(self):
        original_chat = conversation_bridge.ollama_client.chat

        def fail_if_called(model, prompt):
            raise AssertionError("Negative evidence guard should answer first")

        conversation_bridge.ollama_client.chat = fail_if_called

        try:
            result = conversation_bridge.ask(
                question="Does MiniOffice use cloud APIs?",
                model="llama3.2",
                project_name="MiniOffice",
                max_memories=3
            )
        finally:
            conversation_bridge.ollama_client.chat = original_chat

        self.assertTrue(result["answer"].startswith("No."))
        self.assertIn("MiniOffice does not use cloud APIs", result["answer"])
        self.assertIn("no cloud access", result["answer"])
        self.assertIn("Memory #", result["answer"])
        self.assertGreater(len(result["memory_ids"]), 0)
        self.assertEqual(result["ollama_duration_seconds"], 0)

    def test_internet_question_with_no_cloud_evidence_answers_no(self):
        original_chat = conversation_bridge.ollama_client.chat

        def fail_if_called(model, prompt):
            raise AssertionError("Negative evidence guard should answer first")

        conversation_bridge.ollama_client.chat = fail_if_called

        try:
            result = conversation_bridge.ask(
                question="Does MiniOffice need internet access?",
                model="llama3.2",
                project_name="MiniOffice",
                max_memories=3
            )
        finally:
            conversation_bridge.ollama_client.chat = original_chat

        self.assertTrue(result["answer"].startswith("No."))
        self.assertIn("MiniOffice does not use internet access", result["answer"])
        self.assertIn("no cloud access", result["answer"])
        self.assertGreater(len(result["memory_ids"]), 0)
        self.assertEqual(result["ollama_duration_seconds"], 0)

    def test_database_question_with_postgresql_instead_of_sqlite_answers_postgresql(self):
        postgresql_result = create_decision(
            title="MiniOffice PostgreSQL Decision",
            content="Decision: MiniOffice will use PostgreSQL instead of SQLite.",
            metadata={
                "project": "MiniOffice",
                "memory_scope": "real"
            },
            importance=9,
            confidence=100,
            source="conversation"
        )
        original_chat = conversation_bridge.ollama_client.chat

        def fail_if_called(model, prompt):
            raise AssertionError("Database evidence guard should answer first")

        conversation_bridge.ollama_client.chat = fail_if_called

        try:
            result = conversation_bridge.ask(
                question="What database does MiniOffice use?",
                model="llama3.2",
                project_name="MiniOffice",
                max_memories=5
            )
        finally:
            conversation_bridge.ollama_client.chat = original_chat

        self.assertEqual(
            result["answer"],
            "MiniOffice uses PostgreSQL. "
            "Evidence: MiniOffice will use PostgreSQL instead of SQLite. "
            f"(Memory #{postgresql_result['memory_id']})."
        )
        self.assertIn(postgresql_result["memory_id"], result["memory_ids"])
        self.assertEqual(result["ollama_duration_seconds"], 0)

    def test_database_question_with_sqlite_only_answers_sqlite(self):
        original_chat = conversation_bridge.ollama_client.chat

        def fail_if_called(model, prompt):
            raise AssertionError("Database evidence guard should answer first")

        conversation_bridge.ollama_client.chat = fail_if_called

        try:
            result = conversation_bridge.ask(
                question="What database does MiniOffice use?",
                model="llama3.2",
                project_name="MiniOffice",
                max_memories=5
            )
        finally:
            conversation_bridge.ollama_client.chat = original_chat

        self.assertTrue(result["answer"].startswith("MiniOffice uses SQLite."))
        self.assertIn("MiniOffice will use SQLite for local storage", result["answer"])
        self.assertIn("Memory #", result["answer"])
        self.assertEqual(result["ollama_duration_seconds"], 0)

    def test_database_question_prefers_postgresql_when_sqlite_also_exists(self):
        create_decision(
            title="MiniOffice PostgreSQL Supersession",
            content="Decision: MiniOffice will use PostgreSQL instead of SQLite.",
            metadata={
                "project": "MiniOffice",
                "memory_scope": "real"
            },
            importance=9,
            confidence=100,
            source="conversation"
        )
        original_chat = conversation_bridge.ollama_client.chat

        def fail_if_called(model, prompt):
            raise AssertionError("Database evidence guard should answer first")

        conversation_bridge.ollama_client.chat = fail_if_called

        try:
            result = conversation_bridge.ask(
                question="What database does MiniOffice use?",
                model="llama3.2",
                project_name="MiniOffice",
                max_memories=5
            )
        finally:
            conversation_bridge.ollama_client.chat = original_chat

        self.assertTrue(result["answer"].startswith("MiniOffice uses PostgreSQL."))
        self.assertNotIn("MiniOffice uses SQLite.", result["answer"])
        self.assertIn("PostgreSQL instead of SQLite", result["answer"])
        self.assertEqual(result["ollama_duration_seconds"], 0)

    def test_conversation_bridge_preserves_evidence_with_mocked_ollama(self):
        original_chat = conversation_bridge.ollama_client.chat

        def fake_chat(model, prompt):
            self.assertEqual(model, "llama3.2")
            self.assertIn("USMOS Evidence Context", prompt)
            self.assertNotIn("Trusted USMOS Context", prompt)
            self.assertIn("MiniOffice", prompt)
            return "MiniOffice uses local-only sandbox memory."

        conversation_bridge.ollama_client.chat = fake_chat

        try:
            result = conversation_bridge.ask(
                question="What security model does MiniOffice use?",
                model="llama3.2",
                project_name="MiniOffice"
            )
        finally:
            conversation_bridge.ollama_client.chat = original_chat

        self.assertTrue(result["success"])
        self.assertEqual(result["mode"], "compact")
        self.assertIn("local-only sandbox memory", result["answer"])
        self.assertGreater(len(result["memory_ids"]), 0)
        self.assertGreater(len(result["evidence_trace"]), 0)
        self.assertGreater(len(result["trust_scores"]), 0)
        self.assertIn("trust_score", result["trust_scores"][0])

    def test_conversation_bridge_full_mode_is_available(self):
        original_chat = conversation_bridge.ollama_client.chat

        def fake_chat(model, prompt):
            self.assertEqual(model, "llama3.2")
            self.assertIn("Trusted USMOS Context", prompt)
            self.assertIn("trust_explanation", prompt)
            return "MiniOffice uses local-only sandbox memory."

        conversation_bridge.ollama_client.chat = fake_chat

        try:
            result = conversation_bridge.ask(
                question="What security model does MiniOffice use?",
                model="llama3.2",
                project_name="MiniOffice",
                mode="full",
                max_memories=3
            )
        finally:
            conversation_bridge.ollama_client.chat = original_chat

        self.assertTrue(result["success"])
        self.assertEqual(result["mode"], "full")
        self.assertGreater(len(result["memory_ids"]), 0)

    def test_conversation_bridge_full_mode_calls_old_context_package(self):
        original_build_context_package = conversation_bridge.build_context_package
        original_chat = conversation_bridge.ollama_client.chat
        calls = {
            "context_package": 0
        }

        def fake_build_context_package(question, project_name="USMOS", max_results=5):
            calls["context_package"] += 1

            return {
                "success": True,
                "project": project_name,
                "question": question,
                "selected_memories": [],
                "evidence": [
                    {
                        "memory_id": 99,
                        "memory_type": "decision",
                        "title": "Mock Decision",
                        "content": "Decision: Mock full mode evidence.",
                        "trust_score": 140,
                        "trust_explanation": "trust = importance(8) * 5 + confidence(100)"
                    }
                ],
                "reasoning_trace": [
                    "mock reason"
                ],
                "memory_ids": [
                    99
                ],
                "contradiction_warning": None
            }

        def fake_chat(model, prompt):
            return "Mock full mode answer."

        conversation_bridge.build_context_package = fake_build_context_package
        conversation_bridge.ollama_client.chat = fake_chat

        try:
            result = conversation_bridge.ask(
                question="What does full mode use?",
                model="llama3.2",
                project_name="MiniOffice",
                mode="full"
            )
        finally:
            conversation_bridge.build_context_package = original_build_context_package
            conversation_bridge.ollama_client.chat = original_chat

        self.assertEqual(calls["context_package"], 1)
        self.assertEqual(result["memory_ids"], [99])

    def test_conversation_bridge_returns_no_evidence_answer_without_memories(self):
        original_chat = conversation_bridge.ollama_client.chat

        def fail_if_called(model, prompt):
            raise AssertionError("Ollama should not be called without evidence")

        conversation_bridge.ollama_client.chat = fail_if_called

        try:
            result = conversation_bridge.ask(
                question="What is the payroll policy?",
                model="llama3.2",
                project_name="UnknownProject"
            )
        finally:
            conversation_bridge.ollama_client.chat = original_chat

        self.assertTrue(result["success"])
        self.assertEqual(
            result["answer"],
            "I do not have evidence for that."
        )
        self.assertEqual(result["memory_ids"], [])
        self.assertEqual(result["trust_scores"], [])

    def test_kubernetes_unknown_returns_no_evidence_answer(self):
        original_chat = conversation_bridge.ollama_client.chat

        def fail_if_called(model, prompt):
            raise AssertionError("Ollama should not be called without evidence")

        conversation_bridge.ollama_client.chat = fail_if_called

        try:
            result = conversation_bridge.ask(
                question="Does MiniOffice use Kubernetes?",
                model="llama3.2",
                project_name="MiniOffice",
                max_memories=3
            )
        finally:
            conversation_bridge.ollama_client.chat = original_chat

        self.assertEqual(
            result["answer"],
            "I do not have evidence for that."
        )
        self.assertEqual(result["memory_ids"], [])

    def test_conversation_bridge_timing_fields_exist(self):
        original_chat = conversation_bridge.ollama_client.chat

        def fake_chat(model, prompt):
            return "MiniOffice uses local-only sandbox memory."

        conversation_bridge.ollama_client.chat = fake_chat

        try:
            result = conversation_bridge.ask(
                question="What security model does MiniOffice use?",
                model="llama3.2",
                project_name="MiniOffice",
                max_memories=3
            )
        finally:
            conversation_bridge.ollama_client.chat = original_chat

        self.assertIn("retrieval_duration_seconds", result)
        self.assertIn("prompt_build_duration_seconds", result)
        self.assertIn("ollama_duration_seconds", result)
        self.assertIn("total_duration_seconds", result)

    def test_ollama_client_allows_only_localhost_endpoint(self):
        with self.assertRaises(ValueError):
            ollama_client.validate_local_endpoint("https://example.com")

        self.assertEqual(
            ollama_client.validate_local_endpoint("http://localhost:11434"),
            "http://localhost:11434"
        )

    def test_ollama_model_listing_can_be_mocked(self):
        original_read_json_url = ollama_client.read_json_url

        def fake_read_json_url(url, timeout=2):
            return {
                "models": [
                    {
                        "name": "llama3.2"
                    }
                ]
            }

        ollama_client.read_json_url = fake_read_json_url

        try:
            models = ollama_client.list_models()
        finally:
            ollama_client.read_json_url = original_read_json_url

        self.assertEqual(models, ["llama3.2"])
