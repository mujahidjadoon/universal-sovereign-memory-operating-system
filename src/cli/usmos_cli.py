import argparse
import contextlib
import io
import json
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.books.book_benchmark import run_book_benchmark
from src.books.book_ingestion import ingest_book_file
from src.books.book_qa import ask_book
from src.books.book_validation import (
    add_validation_question,
    create_validation_set,
    run_validation_set,
)
from src.books.document_extractors import prepare_document_for_ingestion
from src.conversation.conversation_analyzer import analyze_conversation_for_memory
from src.conversation.conversation_memory import (
    preview_memory_candidates,
    save_approved_memory,
)
from src.conversation.conversation_queue import (
    APPROVED_STATUS,
    PENDING_STATUS,
    REJECTED_STATUS,
)
from src.llm.ollama_client import list_models as list_ollama_models
from src.memory.memory_engine import (
    archive_project,
    benchmark_ingestion,
    benchmark_token_ingestion,
    build_benchmark_file_path,
    build_token_benchmark_file_path,
    create_project,
    generate_benchmark_file,
    generate_token_benchmark_file,
    get_current_project,
    ingest_text_file,
    list_projects,
    list_snapshots,
    recall_memory,
    read_memory,
    run_benchmark_suite as run_memory_benchmark_suite,
    search_all_projects,
    summarize_ingestion_result,
)
from src.plugins import PluginRegistry
from src.storage import database
from src.storage.schema import initialize_schema
from src.usmos import MemoryClient


def initialize_cli_schema():

    with contextlib.redirect_stdout(io.StringIO()):
        initialize_schema()


def print_status(project_name):

    summary = MemoryClient(project_name).status()
    latest_checkpoint = summary["latest_checkpoint"]

    print(f"{project_name} Status")
    print("")
    print("Latest checkpoint:")

    if latest_checkpoint:
        print(latest_checkpoint["title"])
        print(f"Memory ID: #{latest_checkpoint['id']}")
        print(f"Trust Score: {latest_checkpoint['trust_score']}")
    else:
        print("No checkpoint found.")

    print("")
    print("Current phase:")
    print(summary["current_phase"])
    print("")
    print("Completed phases:")

    if summary["completed_phases"]:
        for phase in summary["completed_phases"]:
            print(f"- {phase}")
    else:
        print("- No completed phases found.")


def resolve_project_name(args):

    if getattr(args, "project", None):
        return args.project

    return get_current_project()


def run_status(args):

    print_status(resolve_project_name(args))
    return 0


def run_recall(args):

    print(recall_memory(args.keyword))
    return 0


def run_answer(args):

    question = " ".join(args.question)
    result = MemoryClient(resolve_project_name(args)).answer(question)

    print("Answer:")
    print(result.answer)
    print("")
    print("Memory IDs:")

    if result.memory_ids:
        print(", ".join(f"#{memory_id}" for memory_id in result.memory_ids))
    else:
        print("None")

    print("")
    print("Evidence Trace:")

    evidence_trace = result.raw.get("evidence_trace", []) if result.raw else []

    if evidence_trace:
        for evidence in evidence_trace:
            print(
                f"- Memory #{evidence['memory_id']}: "
                f"{evidence['content']}"
            )
    else:
        print("None")

    return 0


def run_memory_show(args):

    memory = read_memory(args.memory_id)

    if memory is None:
        print(f"Memory #{args.memory_id} not found.")
        return 1

    print(f"Memory #{memory['id']}")
    print(f"Type: {memory['memory_type']}")
    print(f"Title: {memory['title']}")
    print(f"Status: {memory.get('status')}")
    print(f"Importance: {memory.get('importance')}")
    print(f"Confidence: {memory.get('confidence')}")
    print(f"Source: {memory.get('source')}")
    print(f"Trust score: {memory.get('trust_score')}")
    print("Metadata:")
    print(json.dumps(memory.get("metadata") or {}, indent=2, sort_keys=True))
    print("Content:")
    print(memory.get("content", ""))

    return 0


def run_snapshot(args):

    result = MemoryClient(resolve_project_name(args)).snapshot(args.snapshot_name)

    print("Snapshot created:")
    print(result["snapshot_file"])
    print(f"Memories saved: {result['memory_count']}")

    return 0


def run_snapshots(args):

    snapshots = list_snapshots()

    if not snapshots:
        print("No snapshots found.")
        return 0

    for snapshot_file in snapshots:
        print(snapshot_file)

    return 0


def run_restore(args):

    result = MemoryClient().restore(args.snapshot_file)

    if not result["success"]:
        print(result["message"])
        print(result["snapshot_file"])
        return 1

    print("Snapshot restored:")
    print(result["snapshot_file"])
    print(f"Project: {result['project']}")
    print(f"Snapshot: {result['snapshot_name']}")
    print(f"Total memories: {result['total_memories']}")
    print(f"Restored: {result['restored']}")
    print(f"Skipped duplicates: {result['skipped_duplicates']}")

    return 0


def run_timeline(args):

    print(MemoryClient(resolve_project_name(args)).timeline())
    return 0


def run_ingest(args):

    result = ingest_text_file(
        file_path=args.file_path,
        project_name=resolve_project_name(args)
    )

    print(summarize_ingestion_result(result))

    if result["success"]:
        return 0

    return 1


def run_projects(args):

    projects = list_projects()

    if not projects:
        print("No active projects found.")
        return 0

    current_project = get_current_project()

    for project in projects:
        marker = "* " if project["name"] == current_project else "- "
        print(
            f"{marker}{project['name']} "
            f"({project['status']})"
        )

    return 0


def run_project_create(args):

    result = MemoryClient(resolve_project_name(args)).project_create(
        name=args.name,
        description=args.description
    )

    if result["success"]:
        print("Project created:")
        print(result["name"])
        return 0

    print(result["message"])
    return 1


def run_project_use(args):

    result = MemoryClient(resolve_project_name(args)).project_use(args.name)

    if result["success"]:
        print("Current project:")
        print(result["project"])
        return 0

    print(result["message"])
    return 1


def run_project_current(args):

    print(MemoryClient(resolve_project_name(args)).project_current())
    return 0


def run_project_archive(args):

    result = archive_project(args.name)

    if result["success"]:
        print("Project archived:")
        print(result["name"])
        return 0

    print(result["message"])
    return 1


def run_search_all(args):

    grouped_results = search_all_projects(args.keyword)

    if not grouped_results:
        print(f"No memories found for '{args.keyword}'.")
        return 0

    print(f"Cross-project search for '{args.keyword}'")

    for project_name in sorted(grouped_results.keys()):
        print("")
        print(f"Project: {project_name}")

        for memory in grouped_results[project_name]:
            print(
                f"- #{memory['id']} "
                f"{memory['memory_type']}: "
                f"{memory['title']}"
            )

    return 0


def run_benchmark_generate(args):

    output_path = build_benchmark_file_path(
        project_name=args.project_name,
        memory_count=args.memory_count
    )
    result = generate_benchmark_file(
        output_path=output_path,
        project_name=args.project_name,
        memory_count=args.memory_count
    )

    print("Benchmark file generated:")
    print(result["file"])
    print(f"Project: {result['project']}")
    print(f"Memories: {result['memory_count']}")

    return 0


def run_benchmark_ingest(args):

    result = benchmark_ingestion(
        file_path=args.file_path,
        project_name=args.project_name
    )

    if result["success"]:
        print("Benchmark ingestion complete:")
    else:
        print("Benchmark ingestion failed:")

    print(f"File: {result['file']}")
    print(f"Project: {result['project']}")
    print(f"Duration seconds: {result['duration_seconds']}")
    print(f"Created: {result['created']}")
    print(f"Duplicates skipped: {result['duplicates']}")
    print(f"Total memories after: {result['total_memories_after']}")

    return 0 if result["success"] else 1


def run_benchmark_suite_cli(args):

    result = run_memory_benchmark_suite(
        project_name=args.project_name,
        memory_count=args.memory_count
    )

    print("Benchmark suite complete:")
    print(f"Project: {result['project']}")
    print(f"Memories requested: {result['memory_count']}")
    print(f"Generated file: {result['generated_file']['file']}")
    print(f"Ingest created: {result['ingestion']['created']}")
    print(f"Duplicate ingest skipped: {result['duplicate_ingestion']['duplicates']}")
    print(f"Recall questions: {len(result['recall']['results'])}")
    print(f"Snapshot file: {result['snapshot']['snapshot_file']}")
    print(f"Restore skipped duplicates: {result['restore']['skipped_duplicates']}")
    print(f"Report file: {result['report_file']}")

    return 0


def run_token_benchmark_generate(args):

    output_path = build_token_benchmark_file_path(
        project_name=args.project_name,
        target_tokens=args.target_tokens
    )
    result = generate_token_benchmark_file(
        output_path=output_path,
        project_name=args.project_name,
        target_tokens=args.target_tokens
    )

    print("Token benchmark file generated:")
    print(result["file"])
    print(f"Project: {result['project']}")
    print(f"Target tokens: {result['target_tokens']}")
    print(f"Estimated tokens generated: {result['estimated_tokens_generated']}")
    print(f"Structured lines: {result['line_count']}")
    print(f"File size MB: {result['file_size_mb']}")

    return 0


def run_token_benchmark_suite_cli(args):

    result = benchmark_token_ingestion(
        project_name=args.project_name,
        target_tokens=args.target_tokens
    )

    print("Token benchmark suite complete:")
    print(f"Project: {result['project']}")
    print(f"Target tokens: {result['target_tokens']}")
    print(f"Estimated tokens generated: {result['estimated_tokens_generated']}")
    print(f"File size MB: {result['file_size_mb']}")
    print(f"Ingest duration: {result['ingest_duration']}")
    print(f"Duplicate duration: {result['duplicate_duration']}")
    print(f"Recall duration: {result['recall_duration']}")
    print(f"Snapshot size MB: {result['snapshot_size_mb']}")
    print(f"DB size MB: {result['db_size_mb']}")
    print(f"Report file: {result['report_file']}")

    return 0 if result["success"] else 1


def run_models(args):

    models = list_ollama_models()

    if not models:
        print("No Ollama models found on localhost:11434.")
        print("Start Ollama locally, then run this command again.")
        return 0

    print("Ollama models:")

    for model in models:
        print(f"- {model}")

    return 0


def run_chat(args):

    question = " ".join(args.question)
    result = MemoryClient(resolve_project_name(args)).chat(
        question=question,
        model=args.model,
        mode=args.mode,
        max_memories=args.max_memories
    )

    if result["success"]:
        print("Natural answer:")
    else:
        print("Conversation failed:")

    print(result["answer"])
    print("")
    print("Memory IDs:")

    if result["memory_ids"]:
        print(", ".join(f"#{memory_id}" for memory_id in result["memory_ids"]))
    else:
        print("None")

    print("")
    print("Trust scores:")

    if result["trust_scores"]:
        for trust_score in result["trust_scores"]:
            print(
                f"- Memory #{trust_score['memory_id']}: "
                f"{trust_score['trust_score']}"
            )
    else:
        print("None")

    print("")
    print(f"Model: {result['model']}")
    print(f"Mode: {result['mode']}")
    print(f"Max memories: {result['max_memories']}")
    print(f"Response time seconds: {result['response_time_seconds']}")

    if args.debug_timing:
        print("")
        print("Timings:")
        print(f"Retrieval: {result['retrieval_duration_seconds']}")
        print(f"Prompt build: {result['prompt_build_duration_seconds']}")
        print(f"Ollama: {result['ollama_duration_seconds']}")
        print(f"Total: {result['total_duration_seconds']}")

    return 0 if result["success"] else 1


def run_analyze_conversation(args):

    message = " ".join(args.message)
    result = analyze_conversation_for_memory(
        user_message=message,
        project_name=resolve_project_name(args)
    )

    print(preview_memory_candidates(result))
    return 0


def ask_yes_no(prompt):

    answer = input(prompt).strip().lower()

    return answer in {"y", "yes"}


def run_save_conversation_memory(args):

    message = " ".join(args.message)
    analysis = analyze_conversation_for_memory(
        user_message=message,
        project_name=resolve_project_name(args)
    )
    candidates = analysis["candidates"]

    print(
        preview_memory_candidates(
            analysis,
            include_save_prompt=not args.yes
        )
    )

    if not candidates:
        return 0

    saved_count = 0

    for index, candidate in enumerate(candidates, start=1):
        edited_title = None
        edited_content = None
        approved = args.yes

        if not args.yes:
            answer = input(f"Save candidate {index}? [y/N/e] ").strip().lower()
            approved = answer in {"y", "yes", "e", "edit"}

            if answer in {"e", "edit"}:
                edited_title = input("Edited title: ").strip()
                edited_content = input("Edited content: ").strip()

                if not edited_title:
                    edited_title = None

                if not edited_content:
                    edited_content = None

        supersede_memory_id = None
        approve_supersede = False
        possible_supersedes = candidate.get("possible_supersedes") or []

        if approved and possible_supersedes and args.supersede:
            supersede_memory_id = possible_supersedes[0]["memory_id"]
            approve_supersede = True
        elif approved and possible_supersedes and not args.yes:
            old_memory = possible_supersedes[0]
            approve_supersede = ask_yes_no(
                "Supersede old decision "
                f"#{old_memory['memory_id']}? [y/N] "
            )

            if approve_supersede:
                supersede_memory_id = old_memory["memory_id"]

        save_result = save_approved_memory(
            candidate=candidate,
            approved=approved,
            edited_title=edited_title,
            edited_content=edited_content,
            supersede_memory_id=supersede_memory_id,
            approve_supersede=approve_supersede
        )

        if save_result["saved"]:
            saved_count += 1
            print(f"Saved memory #{save_result['memory_id']}")

            if save_result["superseded"]:
                print(f"Superseded memory #{supersede_memory_id}")
        else:
            print(f"Skipped candidate {index}")

    print(f"Conversation memories saved: {saved_count}")
    return 0


def print_pending_item(item):

    print(
        f"#{item['pending_id']} "
        f"[{item['approval_status']}] "
        f"{item['memory_type']} - {item['title']}"
    )
    print(f"Project: {item['project_name']}")
    print(f"Content: {item['content']}")
    print(f"Reason: {item['detected_reason']}")

    proposed_supersession = item.get("proposed_supersession") or []

    if proposed_supersession:
        first_supersession = proposed_supersession[0]
        print(
            "Proposed supersession: "
            f"#{first_supersession['memory_id']} "
            f"{first_supersession['title']}"
        )

    if item.get("approved_memory_id"):
        print(f"Approved memory: #{item['approved_memory_id']}")

    print("")


def run_queue_conversation(args):

    message = " ".join(args.message)
    result = MemoryClient(resolve_project_name(args)).queue(
        user_message=message
    )

    print("Conversation analyzed:")
    print(f"Conversation ID: {result['conversation_id']}")
    print(f"Queued: {result['created']}")
    print(f"Duplicates skipped: {result['duplicates']}")

    for item in result["pending_items"]:
        print_pending_item(item)

    return 0


def run_pending(args):

    status = args.status

    if status == "all":
        status = None

    memory_type = args.memory_type

    if memory_type == "all":
        memory_type = None

    items = MemoryClient(resolve_project_name(args)).pending(
        status=status,
        memory_type=memory_type,
        search=args.search
    )

    if not items:
        print("No pending queue items found.")
        return 0

    print("Pending Memory Queue")
    print("")

    for item in items:
        print_pending_item(item)

    return 0


def run_approve(args):

    result = MemoryClient(resolve_project_name(args)).approve(args.pending_id)

    if not result["success"]:
        print(result["message"])
        return 1

    print(f"Approved pending memory #{args.pending_id}")
    print(f"Memory ID: #{result['memory_id']}")

    if result.get("superseded"):
        print("Supersession applied.")

    return 0


def run_reject(args):

    result = MemoryClient(resolve_project_name(args)).reject(args.pending_id)

    if not result["success"]:
        print(result["message"])
        return 1

    print(f"Rejected pending memory #{args.pending_id}")
    return 0


def run_approve_all(args):

    result = MemoryClient(resolve_project_name(args)).approve_all()

    print(f"Approved pending memories: {result['count']}")
    return 0


def run_reject_all(args):

    result = MemoryClient(resolve_project_name(args)).reject_all()

    print(f"Rejected pending memories: {result['count']}")
    return 0


def run_approve_type(args):

    result = MemoryClient(resolve_project_name(args)).approve_all(
        memory_type=args.memory_type
    )

    print(
        f"Approved {args.memory_type} pending memories: "
        f"{result['count']}"
    )
    return 0


def run_plugin_list(args):

    registry = PluginRegistry()
    plugins = registry.list_plugins()

    if not plugins:
        print("No plugins found.")
        return 0

    print("USMOS Plugins")

    for plugin in plugins:
        print(
            f"- {plugin['id']} "
            f"({plugin['name']} {plugin['version']})"
        )

        if plugin.get("description"):
            print(f"  {plugin['description']}")

        if plugin.get("project_name"):
            print(f"  Project: {plugin['project_name']}")

    return 0


def run_plugin_load(args):

    result = PluginRegistry().load(
        plugin_id=args.plugin_id,
        project_name=getattr(args, "project", None)
    )

    if not result["success"]:
        print(result["message"])
        return 1

    info = result["info"]
    print("Plugin loaded:")
    print(f"ID: {info['id']}")
    print(f"Name: {info['name']}")
    print(f"Version: {info['version']}")
    print(f"Project: {info['project_name']}")

    return 0


def run_plugin_info(args):

    result = PluginRegistry().info(args.plugin_id)

    if not result["success"]:
        print(result["message"])
        return 1

    info = result["plugin"]
    print("Plugin info:")
    print(f"ID: {info['id']}")
    print(f"Name: {info['name']}")
    print(f"Version: {info['version']}")
    print(f"Project: {info['project_name']}")
    print(f"Entrypoint: {info['entrypoint']}")
    print(f"Description: {info['description']}")

    return 0


def run_plugin_health(args):

    result = PluginRegistry().health(args.plugin_id)

    if not result["success"]:
        print(result.get("message", "Plugin health check failed."))
        return 1

    print("Plugin health:")
    print(f"ID: {result['plugin_id']}")
    print(f"Name: {result['name']}")
    print(f"Project: {result['project_name']}")
    print(f"Database connected: {result['database_connected']}")
    print(f"Cloud: {result['cloud']}")
    print(result["message"])

    return 0


def run_plugin_ask(args):

    question = " ".join(args.question)
    result = PluginRegistry().ask(
        plugin_id=args.plugin_id,
        question=question
    )

    if not result["success"]:
        print(result.get("message", "Plugin question failed."))
        return 1

    print("Plugin answer:")
    print(result["answer"])
    print("")
    print("Memory IDs:")

    if result["memory_ids"]:
        print(", ".join(f"#{memory_id}" for memory_id in result["memory_ids"]))
    else:
        print("None")

    print("")
    print("Trust scores:")

    if result["trust_scores"]:
        for memory_id, trust_score in result["trust_scores"].items():
            print(f"- Memory #{memory_id}: {trust_score}")
    else:
        print("None")

    return 0


def run_book_ingest(args):

    prepared_document = prepare_document_for_ingestion(args.file_path)

    if not prepared_document["success"]:
        print("Document extraction failed:")
        print(prepared_document["error"])
        return 1

    result = ingest_book_file(
        file_path=prepared_document["ingest_file_path"],
        project_name=resolve_project_name(args),
        book_title=args.title,
        author=args.author,
        tags=args.tags,
        chunk_words=args.chunk_words,
        overlap_words=args.overlap_words,
        original_source_file=prepared_document["original_source_file"],
        extracted_source_file=prepared_document["extracted_text_file"],
        original_format=prepared_document["original_format"],
        extraction_method=prepared_document["extraction_method"]
    )
    extraction = prepared_document["extraction"]

    print("Book ingestion complete:")
    print(f"Book title: {result['book_title']}")
    print(f"Author: {result['author']}")
    print(f"Project: {result['project']}")
    print(f"Source file: {result['source_file']}")
    print(f"Format: {extraction['format']}")
    print(f"Pages: {extraction['page_count']}")
    print(f"Paragraphs: {extraction['paragraph_count']}")
    print(f"Word count: {extraction['word_count']}")

    if result["extracted_text_file"]:
        print(f"Extracted text file: {result['extracted_text_file']}")

    print(f"Chunks created: {result['chunks_created']}")
    print(f"Duplicates skipped: {result['duplicates_skipped']}")

    return 0 if result["success"] else 1


def print_book_evidence(result):

    print("")
    print("Book title:")
    if result["book_title"]:
        print(result["book_title"])
    elif result["evidence"]:
        books = []

        for evidence in result["evidence"]:
            if evidence["book_title"] not in books:
                books.append(evidence["book_title"])

        print(", ".join(books))
    else:
        print("None")

    print("")
    print("Memory IDs:")

    if result["memory_ids"]:
        print(", ".join(f"#{memory_id}" for memory_id in result["memory_ids"]))
    else:
        print("None")

    print("")
    print("Evidence excerpts:")

    if result["evidence"]:
        for evidence in result["evidence"]:
            evidence_score = evidence.get("relevance_score")
            print(
                f"- {evidence['book_title']} | "
                f"{evidence['chapter']} / {evidence['section']} | "
                f"Memory #{evidence['memory_id']}: "
                f"{evidence['excerpt']} "
                f"(Evidence score: {evidence_score})"
            )
    else:
        print("None")

    print("")
    print("Trust scores:")

    if result["trust_scores"]:
        for memory_id, trust_score in result["trust_scores"].items():
            print(f"- Memory #{memory_id}: {trust_score}")
    else:
        print("None")


def run_book_ask(args):

    question = " ".join(args.question)
    result = ask_book(
        question=question,
        project_name=resolve_project_name(args),
        book_title=args.title,
        model=args.model,
        max_results=args.max_results
    )

    print("Book answer:")
    print(result["answer"])
    print_book_evidence(result)

    return 0


def run_book_benchmark_cli(args):

    result = run_book_benchmark(
        project_name=resolve_project_name(args)
    )

    print("Book benchmark complete:")
    print(f"Project: {result['project']}")
    print(f"Questions asked: {result['questions_asked']}")
    print(f"Answers found: {result['answers_found']}")
    print(f"No-evidence answers: {result['no_evidence_answers']}")
    print(f"Average retrieval time: {result['avg_retrieval_time']}")
    print(f"Average answer time: {result['avg_answer_time']}")
    print(f"Evidence count: {result['evidence_count']}")
    print(f"Report file: {result['report_file']}")

    return 0


def run_book_validation_create(args):

    result = create_validation_set(
        project_name=resolve_project_name(args),
        dataset_name=args.name
    )

    print("Book validation set ready:")
    print(f"Project: {result['project_name']}")
    print(f"Dataset: {result['dataset_name']}")
    print(f"Created: {result['created']}")
    print(f"Questions: {len(result['questions'])}")
    print(f"File: {result['path']}")

    return 0


def run_book_validation_add_question(args):

    result = add_validation_question(
        project_name=resolve_project_name(args),
        dataset_name=args.name,
        question=args.question,
        expected_book_title=args.expected_book,
        expected_keywords=args.keywords,
        should_have_evidence=not args.no_evidence
    )
    question = result["question"]

    print("Validation question added:")
    print(f"Dataset: {result['dataset']['dataset_name']}")
    print(f"Question ID: {question['question_id']}")
    print(f"Question: {question['question']}")
    print(f"Expected book: {question['expected_book_title'] or 'None'}")
    print("Expected keywords: " + ", ".join(question["expected_keywords"]))
    print(f"Should have evidence: {question['should_have_evidence']}")

    return 0


def run_book_validation_run(args):

    report = run_validation_set(
        project_name=resolve_project_name(args),
        dataset_name=args.name
    )
    metrics = report["metrics"]

    print("Book validation complete:")
    print(f"Project: {report['project_name']}")
    print(f"Dataset: {report['dataset_name']}")
    print(f"Total questions: {metrics['total_questions']}")
    print(f"Passed: {metrics['passed']}")
    print(f"Failed: {metrics['failed']}")
    print(f"Precision estimate: {metrics['precision_estimate']}")
    print(f"No-evidence accuracy: {metrics['no_evidence_accuracy']}")
    print(f"Average evidence count: {metrics['average_evidence_count']}")
    print(f"Average retrieval time: {metrics['average_retrieval_time']}")
    print(f"Average answer time: {metrics['average_answer_time']}")
    print(f"Report file: {report['report_file']}")
    print("")
    print("Results:")

    for item in report["results"]:
        status = "PASS" if item["passed"] else "FAIL"
        print(
            f"- {status} | Q{item['question_id']} | "
            f"{item['question']} | {item['reason']}"
        )

    return 0 if metrics["failed"] == 0 else 1


def bytes_to_mb(byte_count):

    return round(byte_count / (1024 * 1024), 3)


def run_db_check(args):

    db_path = database.DB_PATH
    db_size_bytes = db_path.stat().st_size if db_path.exists() else 0

    try:
        conn = database.get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        integrity_result = cursor.fetchone()[0]
        cursor.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        cursor.execute("PRAGMA busy_timeout")
        busy_timeout = cursor.fetchone()[0]
        cursor.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name = 'memories'
        """)
        memories_table_exists = cursor.fetchone() is not None
        conn.close()
    except sqlite3.OperationalError as error:
        print("Database check failed:")
        print(str(error))
        return 1

    print("USMOS DB Check")
    print(f"DB path: {db_path}")
    print(f"DB size bytes: {db_size_bytes}")
    print(f"DB size MB: {bytes_to_mb(db_size_bytes)}")
    print(f"Journal mode: {journal_mode}")
    print(f"Busy timeout ms: {busy_timeout}")
    print(f"Memories table exists: {memories_table_exists}")
    print(f"Integrity check: {integrity_result}")

    return 0


def build_parser():

    parser = argparse.ArgumentParser(
        description="USMOS local command-line interface"
    )
    parser.add_argument(
        "--project",
        default=None,
        help="Project name. Default: current project"
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True
    )

    status_parser = subparsers.add_parser(
        "status",
        help="Show latest checkpoint, current phase, and completed phases"
    )
    status_parser.set_defaults(command_handler=run_status)

    db_check_parser = subparsers.add_parser(
        "db-check",
        help="Check SQLite database health and connection settings"
    )
    db_check_parser.set_defaults(command_handler=run_db_check)

    recall_parser = subparsers.add_parser(
        "recall",
        help="Recall memories by keyword"
    )
    recall_parser.add_argument("keyword")
    recall_parser.set_defaults(command_handler=run_recall)

    answer_parser = subparsers.add_parser(
        "answer",
        help="Answer a question with memory reasoning"
    )
    answer_parser.add_argument("question", nargs="+")
    answer_parser.set_defaults(command_handler=run_answer)

    memory_show_parser = subparsers.add_parser(
        "memory-show",
        help="Show one memory by ID for local debugging"
    )
    memory_show_parser.add_argument("memory_id", type=int)
    memory_show_parser.set_defaults(command_handler=run_memory_show)

    snapshot_parser = subparsers.add_parser(
        "snapshot",
        help="Save a project snapshot"
    )
    snapshot_parser.add_argument("snapshot_name")
    snapshot_parser.set_defaults(command_handler=run_snapshot)

    snapshots_parser = subparsers.add_parser(
        "snapshots",
        help="List available snapshots"
    )
    snapshots_parser.set_defaults(command_handler=run_snapshots)

    restore_parser = subparsers.add_parser(
        "restore",
        help="Restore a snapshot"
    )
    restore_parser.add_argument("snapshot_file")
    restore_parser.set_defaults(command_handler=run_restore)

    timeline_parser = subparsers.add_parser(
        "timeline",
        help="Show project timeline"
    )
    timeline_parser.set_defaults(command_handler=run_timeline)

    ingest_parser = subparsers.add_parser(
        "ingest",
        help="Ingest a local .txt or .md file into USMOS memories"
    )
    ingest_parser.add_argument("file_path")
    ingest_parser.set_defaults(command_handler=run_ingest)

    book_ingest_parser = subparsers.add_parser(
        "book-ingest",
        help="Ingest a local .txt, .md, .pdf, or .docx book/document"
    )
    book_ingest_parser.add_argument("file_path")
    book_ingest_parser.add_argument(
        "--project",
        default=None,
        help="Project name. Default: current project"
    )
    book_ingest_parser.add_argument(
        "--title",
        required=True,
        help="Book or document title"
    )
    book_ingest_parser.add_argument(
        "--author",
        default="",
        help="Optional author name"
    )
    book_ingest_parser.add_argument(
        "--tags",
        nargs="*",
        default=[],
        help="Optional tags"
    )
    book_ingest_parser.add_argument(
        "--chunk-words",
        type=int,
        default=250,
        help="Words per chunk. Default: 250"
    )
    book_ingest_parser.add_argument(
        "--overlap-words",
        type=int,
        default=40,
        help="Word overlap for long chunks. Default: 40"
    )
    book_ingest_parser.set_defaults(command_handler=run_book_ingest)

    book_ask_parser = subparsers.add_parser(
        "book-ask",
        help="Ask a question against ingested book/document memories"
    )
    book_ask_parser.add_argument("question", nargs="+")
    book_ask_parser.add_argument(
        "--project",
        default=None,
        help="Project name. Default: current project"
    )
    book_ask_parser.add_argument(
        "--title",
        default=None,
        help="Optional book title filter"
    )
    book_ask_parser.add_argument(
        "--model",
        default=None,
        help="Optional local Ollama model name for future use"
    )
    book_ask_parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="Maximum evidence memories. Default: 5"
    )
    book_ask_parser.set_defaults(command_handler=run_book_ask)

    book_benchmark_parser = subparsers.add_parser(
        "book-benchmark",
        help="Run the local book/document knowledge validation benchmark"
    )
    book_benchmark_parser.add_argument(
        "--project",
        default=None,
        help="Project name. Default: current project"
    )
    book_benchmark_parser.set_defaults(command_handler=run_book_benchmark_cli)

    book_validation_create_parser = subparsers.add_parser(
        "book-validation-create",
        help="Create a local book validation dataset"
    )
    book_validation_create_parser.add_argument(
        "--project",
        default=None,
        help="Project name. Default: current project"
    )
    book_validation_create_parser.add_argument(
        "--name",
        required=True,
        help="Validation dataset name"
    )
    book_validation_create_parser.set_defaults(
        command_handler=run_book_validation_create
    )

    book_validation_add_parser = subparsers.add_parser(
        "book-validation-add-question",
        help="Add a question to a local book validation dataset"
    )
    book_validation_add_parser.add_argument(
        "--project",
        default=None,
        help="Project name. Default: current project"
    )
    book_validation_add_parser.add_argument(
        "--name",
        required=True,
        help="Validation dataset name"
    )
    book_validation_add_parser.add_argument(
        "--question",
        required=True,
        help="Question to validate"
    )
    book_validation_add_parser.add_argument(
        "--expected-book",
        default="",
        help="Optional expected top evidence book title"
    )
    book_validation_add_parser.add_argument(
        "--keywords",
        default="",
        help="Optional comma-separated expected keywords"
    )
    book_validation_add_parser.add_argument(
        "--no-evidence",
        action="store_true",
        help="Mark this question as expected to return no evidence"
    )
    book_validation_add_parser.set_defaults(
        command_handler=run_book_validation_add_question
    )

    book_validation_run_parser = subparsers.add_parser(
        "book-validation-run",
        help="Run a local book validation dataset"
    )
    book_validation_run_parser.add_argument(
        "--project",
        default=None,
        help="Project name. Default: current project"
    )
    book_validation_run_parser.add_argument(
        "--name",
        required=True,
        help="Validation dataset name"
    )
    book_validation_run_parser.set_defaults(
        command_handler=run_book_validation_run
    )

    projects_parser = subparsers.add_parser(
        "projects",
        help="List active projects"
    )
    projects_parser.set_defaults(command_handler=run_projects)

    project_create_parser = subparsers.add_parser(
        "project-create",
        help="Create a project"
    )
    project_create_parser.add_argument("name")
    project_create_parser.add_argument(
        "--description",
        default="",
        help="Optional project description"
    )
    project_create_parser.set_defaults(command_handler=run_project_create)

    project_use_parser = subparsers.add_parser(
        "project-use",
        help="Switch the current project"
    )
    project_use_parser.add_argument("name")
    project_use_parser.set_defaults(command_handler=run_project_use)

    project_current_parser = subparsers.add_parser(
        "project-current",
        help="Show the current project"
    )
    project_current_parser.set_defaults(command_handler=run_project_current)

    project_archive_parser = subparsers.add_parser(
        "project-archive",
        help="Archive a project"
    )
    project_archive_parser.add_argument("name")
    project_archive_parser.set_defaults(command_handler=run_project_archive)

    search_all_parser = subparsers.add_parser(
        "search-all",
        help="Search memories across all projects"
    )
    search_all_parser.add_argument("keyword")
    search_all_parser.set_defaults(command_handler=run_search_all)

    benchmark_generate_parser = subparsers.add_parser(
        "benchmark-generate",
        help="Generate a structured benchmark .md file"
    )
    benchmark_generate_parser.add_argument("project_name")
    benchmark_generate_parser.add_argument("memory_count", type=int)
    benchmark_generate_parser.set_defaults(command_handler=run_benchmark_generate)

    benchmark_ingest_parser = subparsers.add_parser(
        "benchmark-ingest",
        help="Run a timed benchmark ingestion"
    )
    benchmark_ingest_parser.add_argument("project_name")
    benchmark_ingest_parser.add_argument("file_path")
    benchmark_ingest_parser.set_defaults(command_handler=run_benchmark_ingest)

    benchmark_suite_parser = subparsers.add_parser(
        "benchmark-suite",
        help="Run the local benchmark suite"
    )
    benchmark_suite_parser.add_argument("project_name")
    benchmark_suite_parser.add_argument("memory_count", type=int)
    benchmark_suite_parser.set_defaults(command_handler=run_benchmark_suite_cli)

    token_benchmark_generate_parser = subparsers.add_parser(
        "token-benchmark-generate",
        help="Generate a token-scale structured benchmark .md file"
    )
    token_benchmark_generate_parser.add_argument("project_name")
    token_benchmark_generate_parser.add_argument("target_tokens", type=int)
    token_benchmark_generate_parser.set_defaults(
        command_handler=run_token_benchmark_generate
    )

    token_benchmark_suite_parser = subparsers.add_parser(
        "token-benchmark-suite",
        help="Run the token-scale benchmark suite"
    )
    token_benchmark_suite_parser.add_argument("project_name")
    token_benchmark_suite_parser.add_argument("target_tokens", type=int)
    token_benchmark_suite_parser.set_defaults(
        command_handler=run_token_benchmark_suite_cli
    )

    models_parser = subparsers.add_parser(
        "models",
        help="List local Ollama models"
    )
    models_parser.set_defaults(command_handler=run_models)

    chat_parser = subparsers.add_parser(
        "chat",
        help="Ask through the local Ollama conversation bridge"
    )
    chat_parser.add_argument("question", nargs="+")
    chat_parser.add_argument(
        "--model",
        default=None,
        help="Ollama model name. Default: first local model, then llama3.2"
    )
    chat_parser.add_argument(
        "--mode",
        choices=["compact", "full"],
        default="compact",
        help="Prompt context mode. Default: compact"
    )
    chat_parser.add_argument(
        "--max-memories",
        type=int,
        default=5,
        help="Maximum memories sent to Ollama. Default: 5"
    )
    chat_parser.add_argument(
        "--debug-timing",
        action="store_true",
        help="Show retrieval, prompt, Ollama, and total timing"
    )
    chat_parser.set_defaults(command_handler=run_chat)

    analyze_conversation_parser = subparsers.add_parser(
        "analyze-conversation",
        help="Preview possible memories detected in a conversation message"
    )
    analyze_conversation_parser.add_argument("message", nargs="+")
    analyze_conversation_parser.set_defaults(
        command_handler=run_analyze_conversation
    )

    save_conversation_parser = subparsers.add_parser(
        "save-conversation-memory",
        help="Analyze a conversation message and save approved memories"
    )
    save_conversation_parser.add_argument("message", nargs="+")
    save_conversation_parser.add_argument(
        "--yes",
        action="store_true",
        help="Save detected candidates without an interactive prompt"
    )
    save_conversation_parser.add_argument(
        "--supersede",
        action="store_true",
        help="Supersede the most relevant existing decision if detected"
    )
    save_conversation_parser.set_defaults(
        command_handler=run_save_conversation_memory
    )

    queue_conversation_parser = subparsers.add_parser(
        "queue-conversation",
        help="Analyze a conversation message and add candidates to the pending queue"
    )
    queue_conversation_parser.add_argument("message", nargs="+")
    queue_conversation_parser.set_defaults(
        command_handler=run_queue_conversation
    )

    pending_parser = subparsers.add_parser(
        "pending",
        help="List pending conversation memory candidates"
    )
    pending_parser.add_argument(
        "--status",
        choices=[
            "all",
            PENDING_STATUS,
            APPROVED_STATUS,
            REJECTED_STATUS
        ],
        default=PENDING_STATUS,
        help="Approval status filter. Default: pending"
    )
    pending_parser.add_argument(
        "--type",
        dest="memory_type",
        default="all",
        help="Memory type filter, such as decision or task"
    )
    pending_parser.add_argument(
        "--search",
        default=None,
        help="Search pending item title/content"
    )
    pending_parser.set_defaults(command_handler=run_pending)

    approve_parser = subparsers.add_parser(
        "approve",
        help="Approve one pending memory candidate"
    )
    approve_parser.add_argument("pending_id", type=int)
    approve_parser.set_defaults(command_handler=run_approve)

    reject_parser = subparsers.add_parser(
        "reject",
        help="Reject one pending memory candidate"
    )
    reject_parser.add_argument("pending_id", type=int)
    reject_parser.set_defaults(command_handler=run_reject)

    approve_all_parser = subparsers.add_parser(
        "approve-all",
        help="Approve all pending memory candidates for the current project"
    )
    approve_all_parser.set_defaults(command_handler=run_approve_all)

    reject_all_parser = subparsers.add_parser(
        "reject-all",
        help="Reject all pending memory candidates for the current project"
    )
    reject_all_parser.set_defaults(command_handler=run_reject_all)

    approve_type_parser = subparsers.add_parser(
        "approve-type",
        help="Approve all pending candidates of one memory type"
    )
    approve_type_parser.add_argument("memory_type")
    approve_type_parser.set_defaults(command_handler=run_approve_type)

    plugin_list_parser = subparsers.add_parser(
        "plugin-list",
        help="List available local USMOS plugins"
    )
    plugin_list_parser.set_defaults(command_handler=run_plugin_list)

    plugin_load_parser = subparsers.add_parser(
        "plugin-load",
        help="Validate and load a local USMOS plugin"
    )
    plugin_load_parser.add_argument("plugin_id")
    plugin_load_parser.set_defaults(command_handler=run_plugin_load)

    plugin_info_parser = subparsers.add_parser(
        "plugin-info",
        help="Show plugin manifest information"
    )
    plugin_info_parser.add_argument("plugin_id")
    plugin_info_parser.set_defaults(command_handler=run_plugin_info)

    plugin_health_parser = subparsers.add_parser(
        "plugin-health",
        help="Run a plugin health check"
    )
    plugin_health_parser.add_argument("plugin_id")
    plugin_health_parser.set_defaults(command_handler=run_plugin_health)

    plugin_ask_parser = subparsers.add_parser(
        "plugin-ask",
        help="Ask a question through a loaded plugin"
    )
    plugin_ask_parser.add_argument("plugin_id")
    plugin_ask_parser.add_argument("question", nargs="+")
    plugin_ask_parser.set_defaults(command_handler=run_plugin_ask)

    return parser


def main(argv=None):

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "db-check":
        initialize_cli_schema()

    return args.command_handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
