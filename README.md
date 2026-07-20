# Universal Sovereign Memory Operating System (USMOS)

USMOS is a local-first AI memory operating system for storing structured long-term memory, retrieving evidence-backed information, and preserving project continuity without cloud storage.

It is not a general chatbot and it is not a RAG/vector-search framework. USMOS is the local memory layer: it stores memories, recalls relevant evidence, builds context, and exposes that memory through a CLI, SDK, dashboard, plugin interface, and book/document knowledge tools.

## 1. Project Vision

AI systems often lose important project context because their working context is limited to the current prompt or session. USMOS explores a local memory architecture where decisions, tasks, checkpoints, facts, documents, and validation evidence can persist beyond a single conversation.

The project focuses on four practical ideas:

- Long-term memory matters because real projects depend on decisions, history, and evidence that should survive across sessions.
- Local-first architecture keeps the database, snapshots, documents, and reports on the user's machine.
- Evidence-based retrieval makes answers traceable to memory IDs, trust scores, book excerpts, and validation results.
- Sovereign AI requires that memory storage and recall remain under user control instead of depending on cloud services.

USMOS is currently an advanced local prototype and SDK foundation. It is not yet a production release.

## 2. Key Features

### Completed

- SQLite memory store at `sandbox/data/usmos.db`.
- Structured memory types: decisions, tasks, events, checkpoints, project notes, and book facts stored as project-note memories.
- Metadata, importance, confidence, source tracking, freshness classification, and dynamic trust scores.
- Memory CRUD, soft delete, active/superseded/archived lifecycle, memory history, and supersession relationships.
- Duplicate protection with content hashes and indexed duplicate lookup.
- Keyword search, topic recall, semantic keyword groups, intent-aware recall, and indexed recall through `memory_keywords`.
- Rule-based memory answers and explainable reasoning with evidence traces, memory IDs, trust scores, and contradiction warnings.
- Project state recovery: latest checkpoint, completed phases, current focus, and project summary.
- Snapshot save/list/restore using local JSON files under `sandbox/snapshots/`.
- Multi-project workspace registry and current-project helper stored in `sandbox/current_project.json`.
- Memory graph relationships using the existing `memory_links` table.
- Local CLI in `src/cli/usmos_cli.py`.
- Public SDK wrapper through `MemoryClient` in `src/usmos/client.py`.
- Local plugin system with a bundled MiniOffice demo plugin.
- Local Ollama conversation bridge on `http://localhost:11434`, with compact and full prompt modes.
- Pending conversation memory queue with approve/reject workflows.
- TXT/MD document ingestion into structured memories.
- PDF/DOCX/TXT/MD book/document upload support through local extraction.
- Book Knowledge Layer with chapter/section metadata, evidence excerpts, memory IDs, trust scores, and no-evidence answers.
- Book QA precision filtering, including hard filtering of exercise/question prompt chunks.
- Book validation datasets and JSON validation reports under `sandbox/book_validation_reports/`.
- Streamlit dashboard and standalone Knowledge Library UI.
- Benchmark tooling for structured memory-count and token-count scale tests.

### In Progress

- Expanding real-book validation datasets beyond the current small Biology PDF validation set.
- README and documentation hardening for GitHub/open-source presentation.
- Continued tuning of book QA scoring based on real documents.
- Operational hardening for very large local SQLite databases.

### Planned

- Broader large-scale benchmark reporting and reproducible benchmark artifacts.
- Knowledge synthesis across multiple retrieved evidence chunks.
- Multi-book reasoning that compares and reconciles evidence across documents.
- More advanced temporal reasoning over project history.
- Enterprise document memory workflows and import/export policies.
- AI-FDE integration.
- Larger validation suites across different document types and domains.
- Packaging/release workflow for easier SDK installation.

## 3. Architecture Overview

USMOS is organized as a local memory system with layered access:

- Memory Engine: Core memory creation, update, recall, trust scoring, lifecycle, snapshots, graph links, project recovery, ingestion, and benchmark functions live in `src/memory/memory_engine.py`.
- SQLite Storage: `src/storage/database.py` and `src/storage/schema.py` manage the local SQLite database. The default database path is `sandbox/data/usmos.db`.
- MemoryClient SDK: `src/usmos/client.py` wraps internal functions behind a public API so external projects do not need to call the memory engine directly.
- Plugin System: `src/plugins/` provides a local plugin interface. Plugins are expected to use `MemoryClient`, not direct SQLite access.
- Book Knowledge Layer: `src/books/` handles local book/document extraction, ingestion, book QA, book library listing, benchmarking, and validation.
- Validation Engine: `src/books/book_validation.py` stores validation sets and runs evidence-based checks against book QA results.
- Conversation Bridge: `src/llm/` builds compact/full USMOS context packages and optionally sends them to local Ollama.
- Conversation Queue: `src/conversation/` detects candidate memories, queues them for approval, and records approval/rejection history.
- CLI: `src/cli/usmos_cli.py` exposes project, memory, ingestion, book QA, validation, benchmark, plugin, and conversation commands.
- Dashboard: `src/ui/dashboard.py` provides the broader Streamlit dashboard; `src/ui/library_app.py` provides a simpler Knowledge Library app.

## 4. Project Structure

```text
.
+-- README.md
+-- main.py
+-- requirements.txt
+-- docs/
+-- sandbox/
|   +-- data/
|   |   +-- usmos.db
|   +-- snapshots/
|   +-- benchmarks/
|   +-- benchmark_reports/
|   +-- book_validation_sets/
|   +-- book_validation_reports/
|   +-- uploads/
|       +-- books/
|       +-- extracted_text/
+-- src/
|   +-- books/
|   |   +-- book_benchmark.py
|   |   +-- book_ingestion.py
|   |   +-- book_library.py
|   |   +-- book_models.py
|   |   +-- book_qa.py
|   |   +-- book_validation.py
|   |   +-- document_extractors.py
|   +-- cli/
|   |   +-- usmos_cli.py
|   +-- conversation/
|   |   +-- conversation_analyzer.py
|   |   +-- conversation_memory.py
|   |   +-- conversation_queue.py
|   +-- core/
|   +-- llm/
|   |   +-- context_builder.py
|   |   +-- conversation_bridge.py
|   |   +-- ollama_client.py
|   +-- memory/
|   |   +-- memory_engine.py
|   |   +-- modules/
|   +-- plugins/
|   |   +-- base.py
|   |   +-- registry.py
|   |   +-- minioffice/
|   |       +-- manifest.json
|   |       +-- plugin.py
|   +-- storage/
|   |   +-- database.py
|   |   +-- schema.py
|   +-- ui/
|   |   +-- dashboard.py
|   |   +-- library_app.py
|   +-- usmos/
|       +-- __init__.py
|       +-- client.py
|       +-- conversation.py
|       +-- exceptions.py
|       +-- models.py
|       +-- projects.py
|       +-- queue.py
|       +-- search.py
|       +-- snapshots.py
+-- tests/
    +-- fixtures/books/
    +-- test_benchmark.py
    +-- test_books.py
    +-- test_cli.py
    +-- test_conversation.py
    +-- test_dashboard.py
    +-- test_evolution.py
    +-- test_graph.py
    +-- test_ingestion.py
    +-- test_llm_bridge.py
    +-- test_memory.py
    +-- test_plugins.py
    +-- test_usmos_sdk.py
    +-- test_workspace.py
```

## 5. Technical Stack

- Language: Python
- Database: SQLite
- Local storage: JSON files for snapshots, validation datasets, validation reports, benchmark reports, and current project state
- UI: Streamlit
- Document extraction: plain text, Markdown, `pypdf` for text-based PDFs, `python-docx` for DOCX
- Local LLM bridge: Ollama on localhost only
- Testing: Python `unittest`
- Architecture: local-first, modular, SDK-wrapped, CLI-accessible, evidence-based retrieval
- Listed dependencies: `streamlit`, `pypdf`, `python-docx`, `cryptography>=3.1`

## 6. Current Validation

Current verified engineering signals:

- Automated test suite: 212 tests passing with `python3 -m unittest discover -s tests`.
- Local SQLite database exists at `sandbox/data/usmos.db`.
- Current local database size: approximately 19 GB.
- Snapshot directory size: approximately 121 MB.
- Upload directory size: approximately 116 MB.
- Token-scale benchmark tooling is implemented; the project history records completion of a 30M-token benchmark.

Current real-book validation:

- Dataset: `BiologyPDFTest`
- Project: `MiniOffice`
- Books in dataset:
  - `2nd Year Biology PECTAA (Freebooks.pk) (1)`
  - `Chemistry 11 2025-26 (Freebooks.pk)`
- Latest report: `sandbox/book_validation_reports/MiniOffice_BiologyPDFTest_20260702144039.json`
- Questions: 2
- Passed: 2
- Failed: 0
- Precision estimate: 1.0
- No-evidence accuracy: 1.0
- Average evidence count: 2.5
- Top evidence for `Structure of Nephron?`: memory `#5603494`
- Kubernetes no-evidence control: passed with no memory IDs returned

Measured Biology PDF ingestion details from the local sandbox:

- PDF pages: 252
- Extracted words: 71,932
- Book-memory chunks for `2nd Year Biology PECTAA (Freebooks.pk) (1)`: 509

These numbers describe the current local development sandbox, not a general performance guarantee.

## 7. Current Limitations

- USMOS is not production-ready.
- OCR is not implemented; scanned/image-based PDFs may not extract usable text.
- Book QA is evidence-based and rule-ranked, but it is not full semantic understanding.
- Multi-book synthesis is not implemented; cross-book search exists, but deep synthesis across books is planned.
- Contradiction detection is simple and keyword-based.
- The local Ollama bridge is optional and can be slow depending on the model and machine.
- No cloud sync, distributed storage, or hosted backend.
- No vector database, embeddings, or RAG framework by design.
- No enterprise connectors.
- No packaged PyPI release or installer yet.
- Very large SQLite databases need continued operational hardening for backup, cleanup, and maintenance workflows.

## 8. Development Roadmap

Chronological milestone status:

- Phase 1: Memory Foundation - completed
- Phase 2: Recall and Context Builder - completed
- Phase 3: Memory Answer and Snapshot Restore - completed
- Phase 4: Memory Quality Layer - completed
- Phase 5: Explainable Memory Reasoning - completed
- Phase 6: Project State Recovery Engine - completed
- Phase 7: Local CLI Interface - completed
- Phase 8: Memory Graph Engine - completed
- Phase 9: Local UI Dashboard - completed
- Phase 10: Local Document Ingestion Layer - completed
- Phase 11: Memory Evolution Engine - completed
- Phase 12: Multi-Project Workspace Engine - completed
- Phase 13: Large-Scale Sovereign Memory Benchmark Engine - completed
- Phase 13.1: Fast Duplicate Index - completed
- Phase 13.2: Recall Index Optimization - completed
- Phase 13.3: Batch Ingestion and Batch Keyword Indexing - completed
- Phase 14: Token-Accurate Benchmark Engine - completed
- Phase 15: Local LLM Conversation Bridge Foundation - completed
- Phase 15.1: Context Compression for Ollama - completed
- Phase 15.2: Fast Conversation Path - completed
- Phase 15.3: Query-Specific Ranking for Fast Conversation Path - completed
- Phase 15.4: Negative Evidence and Direct Answer Rules - completed
- Phase 16: Persistent Conversation Memory Engine - completed
- Phase 16.1-16.4: Conversation supersession and direct database answer fixes - completed
- Phase 17: Continuous Conversation Memory Engine - completed
- Phase 18: SDK Abstraction Layer - completed
- Phase 18.1: SDK Fast Answer API - completed
- Phase 19: Plugin Architecture - completed
- Phase 20: Book / Document Knowledge Test Layer - completed
- Phase 20.1: Book QA Precision Filter - completed
- Phase 21: Knowledge Library UI - completed
- Phase 21.1-21.7: Knowledge Library UI, PDF/DOCX support, evidence scoring, and exercise prompt filtering - completed
- Phase 22: Real Knowledge Library Validation - completed
- Phase 22.1: Book Validation Scoring Fix - completed

Upcoming roadmap:

- Phase 23: Reproducible large-scale benchmark reporting
- Phase 24: Knowledge synthesis over multiple evidence chunks
- Phase 25: Multi-book reasoning and comparison
- Phase 26: Enterprise document memory workflows
- Phase 27: Temporal reasoning over evolving project memory
- Phase 28: AI-FDE integration
- Phase 29: Larger enterprise-grade validation suites
- Phase 30: Production release preparation

## 9. Project Status

Current engineering status:

- Local prototype maturity: approximately 75 percent
- SDK/API foundation: approximately 70 percent
- Knowledge Library foundation: approximately 65 percent
- Production readiness: approximately 35 percent

These percentages are estimates, not guarantees. They reflect the amount of implemented local functionality versus the remaining work required for packaging, operational hardening, broader validation, documentation, migration safety, and production support.

## 10. Example Screenshots

Screenshots are intentionally left as placeholders until stable images are captured from the current UI.

### Dashboard

Placeholder: project state, memory quality, graph, snapshots, queue, and conversation dashboard.

### CLI

Placeholder: examples of `status`, `book-ask`, `book-validation-run`, and `chat`.

### Validation

Placeholder: pass/fail table from the Book Validation system.

### Knowledge Library

Placeholder: upload, ingestion summary, library table, ask selected book, ask all books, and evidence viewer.

## 11. Future Vision

USMOS is intended to evolve into a memory foundation for sovereign AI systems: local software that can preserve project knowledge, document evidence, decisions, checkpoints, and conversation-approved memories over long periods of work.

The long-term direction is to make AI applications less dependent on short context windows by giving them a local, auditable memory layer. Future versions should improve synthesis, multi-document reasoning, temporal awareness, validation coverage, and integration with external local-first tools.

USMOS does not yet fully deliver that future vision. The current project is a working local foundation with measurable tests and validation, and the remaining work is being developed incrementally.

## 12. License

License: TBD.

Add a license before public release.

## 13. Contributing

USMOS welcomes careful, evidence-driven contributions.

Contribution guidelines:

- Keep the project local-first.
- Do not add cloud services, external APIs, embeddings, vector databases, or RAG frameworks unless the project direction explicitly changes.
- Prefer small, testable changes over large rewrites.
- Reuse `MemoryClient` for public-facing integrations.
- Do not bypass the SDK from plugins.
- Add or update tests for every behavior change.
- Keep README claims aligned with implemented behavior and validation results.
- Preserve backward compatibility for CLI commands and local sandbox paths when possible.

Recommended local workflow:

```bash
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests
python3 src/cli/usmos_cli.py db-check
```

SDK example:

```bash
PYTHONPATH=src python3 - <<'PY'
from usmos import MemoryClient

memory = MemoryClient(project_name="MiniOffice")

memory.save_decision(
    title="MiniOffice Database Decision",
    content="MiniOffice will use PostgreSQL instead of SQLite."
)

answer = memory.answer("What database does MiniOffice use?")
print(answer.answer)
print(answer.memory_ids)

chat = memory.chat(
    "What security model does MiniOffice use?",
    model="llama3:8b",
    max_memories=3
)
print(chat["answer"])

snapshot = memory.snapshot("Phase22")
print(snapshot)
PY
```

Useful CLI examples:

```bash
python3 src/cli/usmos_cli.py status
python3 src/cli/usmos_cli.py recall sqlite
python3 src/cli/usmos_cli.py answer "Why are we using SQLite?"
python3 src/cli/usmos_cli.py memory-show 5603494
python3 src/cli/usmos_cli.py book-ingest path/to/book.pdf --project MiniOffice --title "My Book"
python3 src/cli/usmos_cli.py book-ask "Structure of Nephron?" --project MiniOffice --title "2nd Year Biology PECTAA (Freebooks.pk) (1)"
python3 src/cli/usmos_cli.py book-validation-create --project MiniOffice --name BiologyTest
python3 src/cli/usmos_cli.py book-validation-add-question --project MiniOffice --name BiologyTest --question "Structure of Nephron?" --expected-book "2nd Year Biology PECTAA (Freebooks.pk) (1)" --keywords "glomerulus,Bowman's capsule,Loop of Henle"
python3 src/cli/usmos_cli.py book-validation-run --project MiniOffice --name BiologyTest
python3 -m streamlit run src/ui/library_app.py
python3 -m streamlit run src/ui/dashboard.py
```

## 14. Disclaimer

Implemented:

- Local SQLite memory storage, recall, snapshots, project recovery, graph links, lifecycle, SDK, CLI, dashboard, plugins, book ingestion, book QA, validation reports, and benchmark tooling.

Experimental:

- Large local database operation at benchmark scale.
- Local Ollama answer generation.
- Book QA ranking and validation scoring.
- Conversation memory analysis and approval workflow.
- Plugin architecture.

Planned:

- Production packaging.
- Broader validation suites.
- Multi-book synthesis.
- Enterprise document workflows.
- Temporal reasoning improvements.
- AI-FDE integration.

USMOS is a idea prototype and not a finished project yet.
