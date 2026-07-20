from src.memory import memory_engine


def snapshot(project_name, snapshot_name):

    return memory_engine.save_snapshot(
        project_name=project_name,
        snapshot_name=snapshot_name
    )


def restore(snapshot_file):

    return memory_engine.restore_snapshot(snapshot_file)
