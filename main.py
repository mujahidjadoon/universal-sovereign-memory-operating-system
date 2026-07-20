from src.storage.schema import initialize_schema

from src.memory.memory_engine import (
    create_decision,
    create_task,
    create_event,
    create_checkpoint,
    answer_from_memory,
    answer_with_reasoning,
    answer_project_state_question,
    mark_metadata_scope,
    mark_metadata_topic,
    save_snapshot,
    list_snapshots,
    restore_snapshot
)


def seed_demo_memories():

    create_decision(
        title="Critical Security Rule",
        content="USMOS database must stay inside sandbox/data/usmos.db.",
        metadata=mark_metadata_topic(
            mark_metadata_scope({"project": "USMOS"}, scope="real"),
            topic="security"
        ),
        importance=10
    )

    create_task(
        title="Build Local SQLite Storage",
        content="Implement SQLite storage inside the local sandbox folder.",
        metadata=mark_metadata_topic(
            mark_metadata_scope({"project": "USMOS"}, scope="real"),
            topic="storage"
        ),
        importance=7
    )

    create_event(
        title="Phase 1 Storage Verified",
        content="USMOS Phase 1 storage works with sandbox SQLite.",
        metadata=mark_metadata_topic(
            mark_metadata_scope({"project": "USMOS"}, scope="real"),
            topic="storage"
        ),
        importance=6
    )

    create_checkpoint(
        title="USMOS Phase 2 Context Builder Complete",
        content="USMOS can analyze questions, auto-recall relevant memories, and build AI-ready context packages.",
        metadata=mark_metadata_topic(
            mark_metadata_scope({"project": "USMOS", "phase": "Phase 2"}, scope="real"),
            topic="project_status"
        ),
        importance=9
    )


def run_test(question):

    print("\n" + "=" * 60)
    print("QUESTION:")
    print(question)
    print("\nANSWER:")
    print(answer_from_memory(question))


def create_snapshot_restore_checkpoint():

    checkpoint_result = create_checkpoint(
        title="USMOS Snapshot Restore PoC Passed",
        content="USMOS can save project memories into a local JSON snapshot, list available snapshots, and restore memories safely while skipping duplicates.",
        metadata={
            "project": "USMOS",
            "phase": "Phase 3",
            "memory_scope": "real",
            "topic": "project_status",
            "milestone": "snapshot_restore_poc_passed"
        },
        importance=10
    )

    return checkpoint_result


def create_phase_completion_checkpoints():

    checkpoint_results = []

    checkpoint_results.append(
        create_checkpoint(
            title="USMOS Phase 1 Memory Foundation Complete",
            content="USMOS Phase 1 completed memory storage, SQLite sandbox database, metadata, timeline, search, and recall foundations.",
            metadata={
                "project": "USMOS",
                "phase": "Phase 1",
                "completed_phase": "Phase 1 Memory Foundation",
                "memory_scope": "real",
                "topic": "project_status",
                "milestone": "phase_1_complete"
            },
            importance=10
        )
    )

    checkpoint_results.append(
        create_checkpoint(
            title="USMOS Phase 4 Memory Quality Layer Complete",
            content="USMOS Phase 4 completed confidence, source tracking, freshness classification, trust scoring, and simple contradiction warnings.",
            metadata={
                "project": "USMOS",
                "phase": "Phase 4",
                "completed_phase": "Phase 4 Memory Quality Layer",
                "memory_scope": "real",
                "topic": "project_status",
                "milestone": "phase_4_complete"
            },
            importance=10
        )
    )

    checkpoint_results.append(
        create_checkpoint(
            title="USMOS Phase 5 Explainable Memory Reasoning Complete",
            content="USMOS Phase 5 completed explainable memory selection, evidence traces, memory IDs in answers, trust explanations, and contradiction warnings.",
            metadata={
                "project": "USMOS",
                "phase": "Phase 5",
                "completed_phase": "Phase 5 Explainable Memory Reasoning",
                "memory_scope": "real",
                "topic": "project_status",
                "milestone": "phase_5_complete"
            },
            importance=10
        )
    )

    return checkpoint_results


def main():

    initialize_schema()
    seed_demo_memories()

    run_test("Why are we using SQLite?")
    run_test("What is the security rule of USMOS?")
    run_test("What is the current USMOS status?")
    run_test("Who won the FIFA World Cup?")

    print("\n" + "=" * 60)
    print("EXPLAINABLE REASONING DEMO:")
    print(answer_with_reasoning("Why are we using SQLite?"))

    print("\n" + "=" * 60)
    print("SNAPSHOT DEMO:")

    snapshot_result = save_snapshot("USMOS", "Phase2")

    print("Snapshot file created:")
    print(snapshot_result["snapshot_file"])
    print(f"Memories saved: {snapshot_result['memory_count']}")

    print("\nAvailable snapshots:")
    print(list_snapshots())

    print("\nRestore test:")
    restore_result = restore_snapshot("USMOS_Phase2.json")
    print(restore_result)

    if restore_result["success"]:
        print("\nFinal checkpoint:")
        checkpoint_result = create_snapshot_restore_checkpoint()
        print(checkpoint_result)

        print("\nPhase completion checkpoints:")
        for phase_checkpoint_result in create_phase_completion_checkpoints():
            print(phase_checkpoint_result)

    print("\n" + "=" * 60)
    print("PROJECT STATE RECOVERY:")

    project_state_questions = [
        "What is the current USMOS project state?",
        "What was the latest checkpoint?",
        "What phase are we in?"
    ]

    for question in project_state_questions:
        print("\nQUESTION:")
        print(question)
        print("\nANSWER:")
        print(answer_project_state_question(question))


if __name__ == "__main__":
    main()
