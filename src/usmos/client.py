from time import perf_counter

from src.llm import ollama_client
from src.llm.context_builder import build_llm_context
from src.llm.conversation_bridge import (
    NO_EVIDENCE_ANSWER,
    build_database_evidence_answer,
    build_negative_evidence_answer,
    build_prompt,
    clean_evidence_content,
    collect_trust_scores,
)
from src.memory import memory_engine
from src.storage import database
from src.usmos import conversation
from src.usmos import models
from src.usmos import projects
from src.usmos import queue as queue_api
from src.usmos import search as search_api
from src.usmos import snapshots


SDK_VERSION = "0.18.1"


class MemoryClient:

    def __init__(self, project_name=None):

        self.project_name = project_name or memory_engine.get_current_project()

    def _project(self, project_name=None):

        return project_name or self.project_name or memory_engine.get_current_project()

    def status(self, project_name=None):

        return search_api.status(self._project(project_name))

    def save(
        self,
        memory_type,
        title,
        content,
        metadata=None,
        importance=5,
        confidence=100,
        source="user",
        project_name=None
    ):

        return models.save_memory(
            memory_type=memory_type,
            title=title,
            content=content,
            project_name=self._project(project_name),
            metadata=metadata,
            importance=importance,
            confidence=confidence,
            source=source
        )

    def save_decision(
        self,
        title,
        content,
        metadata=None,
        importance=8,
        confidence=100,
        source="user",
        project_name=None
    ):

        return models.save_decision(
            title=title,
            content=content,
            project_name=self._project(project_name),
            metadata=metadata,
            importance=importance,
            confidence=confidence,
            source=source
        )

    def save_task(
        self,
        title,
        content,
        metadata=None,
        importance=6,
        confidence=100,
        source="user",
        project_name=None
    ):

        return models.save_task(
            title=title,
            content=content,
            project_name=self._project(project_name),
            metadata=metadata,
            importance=importance,
            confidence=confidence,
            source=source
        )

    def save_checkpoint(
        self,
        title,
        content,
        metadata=None,
        importance=9,
        confidence=100,
        source="checkpoint",
        project_name=None
    ):

        return models.save_checkpoint(
            title=title,
            content=content,
            project_name=self._project(project_name),
            metadata=metadata,
            importance=importance,
            confidence=confidence,
            source=source
        )

    def save_event(
        self,
        title,
        content,
        metadata=None,
        importance=5,
        confidence=100,
        source="user",
        project_name=None
    ):

        return models.save_event(
            title=title,
            content=content,
            project_name=self._project(project_name),
            metadata=metadata,
            importance=importance,
            confidence=confidence,
            source=source
        )

    def save_fact(
        self,
        title,
        content,
        metadata=None,
        importance=5,
        confidence=100,
        source="user",
        project_name=None
    ):

        return models.save_fact(
            title=title,
            content=content,
            project_name=self._project(project_name),
            metadata=metadata,
            importance=importance,
            confidence=confidence,
            source=source
        )

    def search(self, keyword, project_name=None):

        return search_api.search(
            keyword=keyword,
            project_name=self._project(project_name)
        )

    def _trust_scores_dict(self, evidence):

        trust_scores = {}

        for item in collect_trust_scores(evidence):
            trust_scores[item["memory_id"]] = item["trust_score"]

        return trust_scores

    def _raw_answer_result(
        self,
        answer,
        context_package,
        prompt,
        retrieval_duration,
        prompt_build_duration,
        total_duration,
        answered_without_llm=True
    ):

        evidence = context_package.get("evidence", [])

        return {
            "success": True,
            "project": context_package["project"],
            "question": context_package["question"],
            "model": None,
            "mode": "compact",
            "max_memories": len(context_package.get("selected_memories", [])),
            "answer": answer,
            "context": context_package,
            "prompt": prompt,
            "evidence_trace": evidence,
            "memory_ids": context_package.get("memory_ids", []),
            "trust_scores": collect_trust_scores(evidence),
            "retrieval_duration_seconds": round(retrieval_duration, 6),
            "prompt_build_duration_seconds": round(prompt_build_duration, 6),
            "ollama_duration_seconds": 0,
            "total_duration_seconds": round(total_duration, 6),
            "response_time_seconds": round(total_duration, 6),
            "answered_without_llm": answered_without_llm
        }

    def _result_from_raw(self, raw_result):

        trust_scores = {}

        for item in raw_result.get("trust_scores", []):
            trust_scores[item["memory_id"]] = item["trust_score"]

        return models.MemoryAnswerResult(
            answer=raw_result["answer"],
            memory_ids=raw_result.get("memory_ids", []),
            trust_scores=trust_scores,
            retrieval_duration_seconds=raw_result.get(
                "retrieval_duration_seconds",
                0
            ),
            prompt_build_duration_seconds=raw_result.get(
                "prompt_build_duration_seconds",
                0
            ),
            ollama_duration_seconds=raw_result.get(
                "ollama_duration_seconds",
                0
            ),
            total_duration_seconds=raw_result.get(
                "total_duration_seconds",
                raw_result.get("response_time_seconds", 0)
            ),
            answered_without_llm=raw_result.get(
                "answered_without_llm",
                raw_result.get("ollama_duration_seconds", 0) == 0
            ),
            raw=raw_result
        )

    def _question_asks_snapshot(self, question):

        return "snapshot" in question.lower()

    def _question_asks_approval(self, question):

        question_lower = question.lower()
        approval_phrases = [
            "approval",
            "approve",
            "human approval",
            "delete files",
            "deleting files"
        ]

        return any(phrase in question_lower for phrase in approval_phrases)

    def _build_snapshot_answer(self, context_package):

        if not self._question_asks_snapshot(context_package["question"]):
            return None

        project_name = context_package["project"]

        for evidence in context_package.get("evidence", []):
            content = evidence.get("content", "")
            content_lower = content.lower()

            if "snapshot" not in content_lower:
                continue

            evidence_content = clean_evidence_content(content)

            if "sandbox/snapshots" in content_lower:
                return (
                    f"{project_name} snapshots are stored in sandbox/snapshots. "
                    f"Evidence: {evidence_content} "
                    f"(Memory #{evidence['memory_id']})."
                )

            return (
                f"{project_name} snapshot evidence: {evidence_content} "
                f"(Memory #{evidence['memory_id']})."
            )

        return None

    def _build_approval_answer(self, context_package):

        if not self._question_asks_approval(context_package["question"]):
            return None

        project_name = context_package["project"]

        for evidence in context_package.get("evidence", []):
            content = evidence.get("content", "")
            content_lower = content.lower()

            if "approval" not in content_lower and "approve" not in content_lower:
                continue

            evidence_content = clean_evidence_content(content)

            if "deleting files" in content_lower or "delete files" in content_lower:
                return (
                    f"Yes. {project_name} requires human approval before "
                    f"deleting files. Evidence: {evidence_content} "
                    f"(Memory #{evidence['memory_id']})."
                )

            return (
                f"Yes. {project_name} requires approval. "
                f"Evidence: {evidence_content} "
                f"(Memory #{evidence['memory_id']})."
            )

        return None

    def _build_fast_memory_answer(self, context_package):

        evidence = context_package.get("evidence", [])

        if not evidence:
            return NO_EVIDENCE_ANSWER

        first_evidence = evidence[0]
        evidence_content = clean_evidence_content(first_evidence["content"])

        return (
            f"Based on USMOS evidence: {evidence_content} "
            f"(Memory #{first_evidence['memory_id']})."
        )

    def _build_direct_answer(self, context_package):

        direct_answer_builders = [
            build_database_evidence_answer,
            build_negative_evidence_answer,
            self._build_snapshot_answer,
            self._build_approval_answer
        ]

        for answer_builder in direct_answer_builders:
            answer = answer_builder(context_package)

            if answer:
                return answer

        return None

    def _answer_internal(
        self,
        question,
        model=None,
        max_memories=5,
        mode="compact",
        project_name=None,
        use_llm=False
    ):

        project = self._project(project_name)

        if use_llm:
            return conversation.chat(
                question=question,
                project_name=project,
                model=model,
                mode=mode,
                max_memories=max_memories
            )

        started_at = perf_counter()
        retrieval_started_at = perf_counter()
        context_package = build_llm_context(
            question=question,
            project_name=project,
            max_memories=max_memories
        )
        retrieval_duration = perf_counter() - retrieval_started_at

        prompt_started_at = perf_counter()
        prompt = build_prompt(
            context_package=context_package,
            mode="compact"
        )
        prompt_build_duration = perf_counter() - prompt_started_at

        direct_answer = None

        if context_package["memory_ids"]:
            direct_answer = self._build_direct_answer(context_package)

        if direct_answer:
            answer = direct_answer
        elif context_package["memory_ids"]:
            answer = self._build_fast_memory_answer(context_package)
        else:
            answer = NO_EVIDENCE_ANSWER

        total_duration = perf_counter() - started_at

        return self._raw_answer_result(
            answer=answer,
            context_package=context_package,
            prompt=prompt,
            retrieval_duration=retrieval_duration,
            prompt_build_duration=prompt_build_duration,
            total_duration=total_duration,
            answered_without_llm=True
        )

    def answer(
        self,
        question,
        max_results=5,
        max_memories=None,
        project_name=None
    ):

        if max_memories is None:
            max_memories = max_results

        raw_result = self._answer_internal(
            question=question,
            max_memories=max_memories,
            mode="compact",
            project_name=project_name,
            use_llm=False
        )

        return self._result_from_raw(raw_result)

    def answer_text(
        self,
        question,
        max_results=5,
        max_memories=None,
        project_name=None
    ):

        return self.answer(
            question=question,
            max_results=max_results,
            max_memories=max_memories,
            project_name=project_name
        ).answer

    def chat(
        self,
        question,
        model=None,
        mode="compact",
        max_memories=5,
        project_name=None
    ):

        return self._answer_internal(
            question=question,
            model=model,
            mode=mode,
            max_memories=max_memories,
            project_name=project_name,
            use_llm=True
        )

    def timeline(self, include_tests=False, project_name=None):

        return search_api.timeline(
            project_name=self._project(project_name),
            include_tests=include_tests
        )

    def snapshot(self, snapshot_name, project_name=None):

        return snapshots.snapshot(
            project_name=self._project(project_name),
            snapshot_name=snapshot_name
        )

    def restore(self, snapshot_file):

        return snapshots.restore(snapshot_file)

    def queue(
        self,
        user_message,
        assistant_message=None,
        source="conversation",
        project_name=None
    ):

        return conversation.queue(
            user_message=user_message,
            assistant_message=assistant_message,
            project_name=self._project(project_name),
            source=source
        )

    def pending(self, status=None, memory_type=None, search=None, project_name=None):

        return queue_api.pending(
            project_name=self._project(project_name),
            status=status,
            memory_type=memory_type,
            search=search
        )

    def approve(self, pending_id):

        return queue_api.approve(pending_id)

    def reject(self, pending_id):

        return queue_api.reject(pending_id)

    def approve_all(self, memory_type=None, project_name=None):

        return queue_api.approve_all(
            project_name=self._project(project_name),
            memory_type=memory_type
        )

    def reject_all(self, memory_type=None, project_name=None):

        return queue_api.reject_all(
            project_name=self._project(project_name),
            memory_type=memory_type
        )

    def project_create(self, name, description=""):

        return projects.project_create(
            name=name,
            description=description
        )

    def project_use(self, name):

        result = projects.project_use(name)

        if result["success"]:
            self.project_name = result["project"]

        return result

    def project_current(self):

        return projects.project_current()

    def graph(self, project_name=None):

        return search_api.graph(self._project(project_name))

    def health(self):

        database_path = database.DB_PATH
        database_connected = False

        try:
            conn = database.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            conn.close()
            database_connected = True
        except Exception:
            database_connected = False

        return {
            "success": True,
            "project": self._project(),
            "current_project": memory_engine.get_current_project(),
            "database_path": str(database_path),
            "database_exists": database_path.exists(),
            "database_connected": database_connected,
            "ollama_available": ollama_client.is_ollama_running(),
            "sdk_version": SDK_VERSION,
            "memory_count": None,
            "storage": "local_sqlite",
            "cloud": False
        }
