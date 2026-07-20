import json
from datetime import datetime
from pathlib import Path

from src.books.book_qa import ask_book


BOOK_BENCHMARK_REPORT_DIR = Path("sandbox/book_benchmark_reports")

DEFAULT_BOOK_BENCHMARK_QUESTIONS = [
    "What does the selected book say about context windows?",
    "Which chapter discusses the main concept?",
    "Which book discusses local-first architecture?",
    "Which book discusses SQLite indexes?",
    "Do these books mention Kubernetes?"
]


def run_book_benchmark(project_name, questions=None):

    selected_questions = questions or DEFAULT_BOOK_BENCHMARK_QUESTIONS
    results = []
    found_count = 0
    no_evidence_count = 0
    retrieval_total = 0
    answer_total = 0
    evidence_total = 0

    for question in selected_questions:
        result = ask_book(
            question=question,
            project_name=project_name
        )
        evidence_count = len(result["evidence"])

        if result["success"]:
            found_count += 1
        else:
            no_evidence_count += 1

        retrieval_total += result["retrieval_duration_seconds"]
        answer_total += result["answer_duration_seconds"]
        evidence_total += evidence_count
        results.append({
            "question": question,
            "answer": result["answer"],
            "success": result["success"],
            "evidence_count": evidence_count,
            "memory_ids": result["memory_ids"],
            "retrieval_duration_seconds": result["retrieval_duration_seconds"],
            "answer_duration_seconds": result["answer_duration_seconds"]
        })

    question_count = len(selected_questions)
    report = {
        "success": True,
        "project": project_name,
        "created_at": datetime.now().isoformat(),
        "questions_asked": question_count,
        "answers_found": found_count,
        "no_evidence_answers": no_evidence_count,
        "avg_retrieval_time": round(retrieval_total / question_count, 6)
        if question_count else 0,
        "avg_answer_time": round(answer_total / question_count, 6)
        if question_count else 0,
        "evidence_count": evidence_total,
        "results": results
    }

    BOOK_BENCHMARK_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_file = (
        BOOK_BENCHMARK_REPORT_DIR
        / f"{project_name}_book_benchmark_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    )
    report_file.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8"
    )
    report["report_file"] = str(report_file)

    return report
