import tempfile
import unittest
from pathlib import Path

from src.memory import memory_engine
from src.memory.memory_engine import (
    archive_project,
    create_decision,
    create_project,
    get_current_project,
    get_project,
    list_memories_by_project,
    list_projects,
    read_memory,
    search_all_projects,
    set_current_project,
)
from src.storage import database
from src.storage.schema import initialize_schema


class MultiProjectWorkspaceTests(unittest.TestCase):

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

    def test_create_project(self):
        result = create_project("AI-FDE", "AI file development environment")

        self.assertTrue(result["success"])
        self.assertEqual(result["name"], "AI-FDE")
        self.assertEqual(get_project("AI-FDE")["status"], "active")

    def test_list_projects_includes_default_and_created_projects(self):
        create_project("AI-FDE")

        project_names = []

        for project in list_projects():
            project_names.append(project["name"])

        self.assertIn("USMOS", project_names)
        self.assertIn("AI-FDE", project_names)

    def test_set_and_get_current_project(self):
        create_project("AI-FDE")
        result = set_current_project("AI-FDE")

        self.assertTrue(result["success"])
        self.assertEqual(get_current_project(), "AI-FDE")
        self.assertTrue(memory_engine.CURRENT_PROJECT_FILE.exists())

    def test_memory_creation_defaults_to_current_project(self):
        create_project("AI-FDE")
        set_current_project("AI-FDE")

        result = create_decision(
            title="AI-FDE SQLite Rule",
            content="AI-FDE must use SQLite for local workspace memory."
        )

        memory = read_memory(result["memory_id"])

        self.assertEqual(memory["metadata"]["project"], "AI-FDE")
        self.assertEqual(len(list_memories_by_project("AI-FDE")), 1)
        self.assertEqual(len(list_memories_by_project("USMOS")), 0)

    def test_search_all_projects_groups_results_by_project(self):
        create_project("AI-FDE")

        set_current_project("USMOS")
        create_decision(
            title="USMOS SQLite Decision",
            content="USMOS uses SQLite for sovereign memory."
        )

        set_current_project("AI-FDE")
        create_decision(
            title="AI-FDE SQLite Decision",
            content="AI-FDE uses SQLite for local project memory."
        )

        results = search_all_projects("SQLite")

        self.assertIn("USMOS", results)
        self.assertIn("AI-FDE", results)
        self.assertEqual(len(results["USMOS"]), 1)
        self.assertEqual(len(results["AI-FDE"]), 1)

    def test_archive_project(self):
        create_project("OldProject")
        result = archive_project("OldProject")

        self.assertTrue(result["success"])
        self.assertEqual(get_project("OldProject")["status"], "archived")

        active_project_names = []

        for project in list_projects():
            active_project_names.append(project["name"])

        self.assertNotIn("OldProject", active_project_names)

