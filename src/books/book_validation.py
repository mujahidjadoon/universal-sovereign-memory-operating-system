import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from src.books.book_library import get_book_titles
from src.books.book_qa import ask_book


BOOK_VALIDATION_SET_DIR = Path("sandbox/book_validation_sets")
BOOK_VALIDATION_REPORT_DIR = Path("sandbox/book_validation_reports")

SAMPLE_VALIDATION_QUESTIONS = [
    {
        "question": "Structure of Nephron?",
        "expected_book_title": "",
        "expected_keywords": [
            "glomerulus",
            "Bowman's capsule",
            "Loop of Henle"
        ],
        "should_have_evidence": True
    },
    {
        "question": "What is dialysis?",
        "expected_book_title": "",
        "expected_keywords": [
            "dialysis"
        ],
        "should_have_evidence": True
    },
    {
        "question": "What does this book say about kidney function?",
        "expected_book_title": "",
        "expected_keywords": [
            "kidney",
            "function"
        ],
        "should_have_evidence": True
    },
    {
        "question": "Does this biology book mention Kubernetes?",
        "expected_book_title": "",
        "expected_keywords": [],
        "should_have_evidence": False
    },
    {
        "question": "Which book discusses SQLite indexes?",
        "expected_book_title": "SQLite Book",
        "expected_keywords": [
            "SQLite",
            "indexes"
        ],
        "should_have_evidence": True
    },
    {
        "question": "Which book talks about user-controlled local data?",
        "expected_book_title": "Local First Book",
        "expected_keywords": [
            "user-controlled",
            "local data"
        ],
        "should_have_evidence": True
    }
]


def normalize_text(text):

    normalized = unicodedata.normalize("NFKC", str(text or ""))
    normalized = normalized.replace("’", "'")
    normalized = normalized.replace("‘", "'")
    normalized = normalized.replace("`", "'")
    normalized = normalized.replace("ʼ", "'")
    normalized = normalized.replace("“", '"')
    normalized = normalized.replace("”", '"')
    normalized = normalized.replace("ﬁ", "fi")
    normalized = normalized.replace("ﬂ", "fl")
    normalized = normalized.lower()

    return " ".join(normalized.split())


def normalize_keyword_match_text(text):

    normalized = normalize_text(text)
    normalized = normalized.replace("'", "")

    return normalized


def normalize_title(title):

    return normalize_text(title)


def safe_name(value):

    clean_value = re.sub(r"[^A-Za-z0-9._-]+", "_", value or "").strip("._-")

    if not clean_value:
        return "untitled"

    return clean_value


def parse_expected_keywords(keywords):

    if keywords is None:
        return []

    if isinstance(keywords, str):
        parts = keywords.split(",")
    else:
        parts = keywords

    clean_keywords = []

    for keyword in parts:
        clean_keyword = str(keyword).strip()

        if clean_keyword:
            clean_keywords.append(clean_keyword)

    return clean_keywords


def build_validation_set_path(project_name, dataset_name):

    filename = f"{safe_name(project_name)}_{safe_name(dataset_name)}.json"
    return BOOK_VALIDATION_SET_DIR / filename


def validation_timestamp():

    return datetime.now().isoformat()


def create_validation_set(project_name, dataset_name, book_titles=None):

    BOOK_VALIDATION_SET_DIR.mkdir(parents=True, exist_ok=True)
    path = build_validation_set_path(project_name, dataset_name)

    if path.exists():
        dataset = load_validation_set(project_name, dataset_name)
        dataset["created"] = False
        dataset["path"] = str(path)
        return dataset

    selected_book_titles = book_titles

    if selected_book_titles is None:
        selected_book_titles = get_book_titles(project_name)

    now = validation_timestamp()
    dataset = {
        "success": True,
        "created": True,
        "project_name": project_name,
        "dataset_name": dataset_name,
        "book_titles": list(selected_book_titles),
        "questions": [],
        "created_at": now,
        "updated_at": now,
        "path": str(path)
    }
    save_validation_set(dataset)

    return dataset


def save_validation_set(dataset):

    BOOK_VALIDATION_SET_DIR.mkdir(parents=True, exist_ok=True)
    path = build_validation_set_path(
        dataset["project_name"],
        dataset["dataset_name"]
    )
    dataset["path"] = str(path)
    path.write_text(
        json.dumps(dataset, indent=2),
        encoding="utf-8"
    )

    return dataset


def load_validation_set(project_name, dataset_name):

    path = build_validation_set_path(project_name, dataset_name)

    if not path.exists():
        raise FileNotFoundError(
            f"Validation set not found: {project_name}/{dataset_name}"
        )

    dataset = json.loads(path.read_text(encoding="utf-8"))
    dataset["path"] = str(path)

    return dataset


def next_question_id(dataset):

    highest_id = 0

    for item in dataset.get("questions", []):
        highest_id = max(highest_id, int(item.get("question_id", 0)))

    return highest_id + 1


def add_validation_question(
    project_name,
    dataset_name,
    question,
    expected_book_title=None,
    expected_keywords=None,
    should_have_evidence=True
):

    dataset = load_validation_set(project_name, dataset_name)
    question_item = {
        "question_id": next_question_id(dataset),
        "question": question,
        "expected_book_title": expected_book_title or "",
        "expected_keywords": parse_expected_keywords(expected_keywords),
        "should_have_evidence": bool(should_have_evidence),
        "created_at": validation_timestamp()
    }
    dataset.setdefault("questions", []).append(question_item)
    dataset["updated_at"] = validation_timestamp()
    save_validation_set(dataset)

    return {
        "success": True,
        "dataset": dataset,
        "question": question_item
    }


def create_sample_validation_set(project_name, dataset_name="SampleValidation"):

    dataset = create_validation_set(
        project_name=project_name,
        dataset_name=dataset_name
    )
    dataset["questions"] = []

    for item in SAMPLE_VALIDATION_QUESTIONS:
        dataset["questions"].append({
            "question_id": next_question_id(dataset),
            "question": item["question"],
            "expected_book_title": item["expected_book_title"],
            "expected_keywords": item["expected_keywords"],
            "should_have_evidence": item["should_have_evidence"],
            "created_at": validation_timestamp()
        })

    dataset["updated_at"] = validation_timestamp()
    save_validation_set(dataset)

    return dataset


def collect_answer_text(result):

    parts = [
        result.get("answer", "")
    ]

    for evidence in result.get("evidence", []):
        parts.append(evidence.get("excerpt", ""))
        parts.append(evidence.get("full_content", ""))
        parts.append(evidence.get("content", ""))
        parts.append(evidence.get("book_title", ""))
        parts.append(evidence.get("chapter", ""))
        parts.append(evidence.get("section", ""))

    return normalize_text(" ".join(parts))


def count_keyword_matches(result, expected_keywords):

    combined_text = collect_answer_text(result)
    apostropheless_text = normalize_keyword_match_text(combined_text)
    matched_keywords = []
    missing_keywords = []

    for keyword in expected_keywords:
        normalized_keyword = normalize_text(keyword)
        apostropheless_keyword = normalize_keyword_match_text(keyword)

        if (
            normalized_keyword in combined_text
            or apostropheless_keyword in apostropheless_text
        ):
            matched_keywords.append(keyword)
        else:
            missing_keywords.append(keyword)

    return matched_keywords, missing_keywords


def expected_book_matches(result, expected_book_title):

    if not expected_book_title:
        return None

    evidence = result.get("evidence", [])

    if not evidence:
        return False

    top_book_title = evidence[0].get("book_title", "")

    return normalize_title(top_book_title) == normalize_title(expected_book_title)


def evaluate_validation_question(project_name, question_item):

    result = ask_book(
        question=question_item["question"],
        project_name=project_name
    )
    evidence = result.get("evidence", [])
    should_have_evidence = question_item.get("should_have_evidence", True)
    answer_found = bool(result.get("success"))
    memory_ids = result.get("memory_ids", [])
    evidence_count = len(evidence)
    top_memory_id = None

    if memory_ids:
        top_memory_id = memory_ids[0]

    if not should_have_evidence:
        no_evidence_returned = (
            not answer_found
            or not memory_ids
            or evidence_count == 0
        )

        return {
            "question_id": question_item.get("question_id"),
            "question": question_item["question"],
            "answer": result.get("answer", ""),
            "answer_found": answer_found,
            "should_have_evidence": should_have_evidence,
            "expected_book_title": question_item.get("expected_book_title", ""),
            "expected_book_matched": None,
            "expected_keywords": question_item.get("expected_keywords", []),
            "matched_keywords": [],
            "missing_keywords": [],
            "keyword_match_count": 0,
            "evidence_count": evidence_count,
            "top_memory_id": top_memory_id,
            "memory_ids": memory_ids,
            "evidence_scores": [
                item.get("relevance_score")
                for item in evidence
            ],
            "passed": no_evidence_returned,
            "reason": "no evidence correctly returned"
            if no_evidence_returned
            else "expected no evidence but evidence was found",
            "retrieval_duration_seconds": result.get(
                "retrieval_duration_seconds",
                0
            ),
            "answer_duration_seconds": result.get(
                "answer_duration_seconds",
                0
            )
        }

    expected_keywords = question_item.get("expected_keywords", [])
    matched_keywords, missing_keywords = count_keyword_matches(
        result=result,
        expected_keywords=expected_keywords
    )
    expected_book_matched = expected_book_matches(
        result=result,
        expected_book_title=question_item.get("expected_book_title", "")
    )
    passed = True
    reasons = []

    if should_have_evidence and not answer_found:
        passed = False
        reasons.append("expected evidence but no evidence was found")

    if expected_book_matched is False:
        passed = False
        reasons.append("expected book did not match top evidence")

    if expected_keywords and missing_keywords:
        passed = False
        reasons.append("missing expected keywords: " + ", ".join(missing_keywords))

    if not reasons:
        reasons.append("passed")

    return {
        "question_id": question_item.get("question_id"),
        "question": question_item["question"],
        "answer": result.get("answer", ""),
        "answer_found": answer_found,
        "should_have_evidence": should_have_evidence,
        "expected_book_title": question_item.get("expected_book_title", ""),
        "expected_book_matched": expected_book_matched,
        "expected_keywords": expected_keywords,
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "keyword_match_count": len(matched_keywords),
        "evidence_count": evidence_count,
        "top_memory_id": top_memory_id,
        "memory_ids": memory_ids,
        "evidence_scores": [
            item.get("relevance_score")
            for item in evidence
        ],
        "passed": passed,
        "reason": "; ".join(reasons),
        "retrieval_duration_seconds": result.get(
            "retrieval_duration_seconds",
            0
        ),
        "answer_duration_seconds": result.get(
            "answer_duration_seconds",
            0
        )
    }


def calculate_validation_metrics(question_results):

    total_questions = len(question_results)
    passed = sum(1 for item in question_results if item["passed"])
    failed = total_questions - passed
    no_evidence_expected = [
        item for item in question_results
        if not item["should_have_evidence"]
    ]
    no_evidence_correct = [
        item for item in no_evidence_expected
        if item["passed"]
    ]
    evidence_total = sum(item["evidence_count"] for item in question_results)
    retrieval_total = sum(
        item["retrieval_duration_seconds"]
        for item in question_results
    )
    answer_total = sum(
        item["answer_duration_seconds"]
        for item in question_results
    )

    return {
        "total_questions": total_questions,
        "passed": passed,
        "failed": failed,
        "precision_estimate": round(passed / total_questions, 4)
        if total_questions else 0,
        "no_evidence_accuracy": round(
            len(no_evidence_correct) / len(no_evidence_expected),
            4
        ) if no_evidence_expected else None,
        "average_evidence_count": round(evidence_total / total_questions, 4)
        if total_questions else 0,
        "average_retrieval_time": round(retrieval_total / total_questions, 6)
        if total_questions else 0,
        "average_answer_time": round(answer_total / total_questions, 6)
        if total_questions else 0
    }


def save_validation_report(report):

    BOOK_VALIDATION_REPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    report_file = (
        BOOK_VALIDATION_REPORT_DIR
        / (
            f"{safe_name(report['project_name'])}_"
            f"{safe_name(report['dataset_name'])}_{timestamp}.json"
        )
    )
    report_file.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8"
    )
    report["report_file"] = str(report_file)

    return report


def run_validation_set(project_name, dataset_name):

    dataset = load_validation_set(project_name, dataset_name)
    started_at = validation_timestamp()
    results = []

    for question_item in dataset.get("questions", []):
        results.append(
            evaluate_validation_question(
                project_name=project_name,
                question_item=question_item
            )
        )

    metrics = calculate_validation_metrics(results)
    report = {
        "success": True,
        "project_name": project_name,
        "dataset_name": dataset_name,
        "book_titles": dataset.get("book_titles", []),
        "started_at": started_at,
        "ended_at": validation_timestamp(),
        "metrics": metrics,
        "results": results
    }
    save_validation_report(report)

    return report
