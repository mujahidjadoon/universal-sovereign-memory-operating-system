import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

from src.cli import usmos_cli
from src.memory import memory_engine
from src.plugins import BasePlugin, PluginRegistry
from src.storage import database
from src.storage.schema import initialize_schema
from src.ui import dashboard
from src.usmos import MemoryClient


class PluginArchitectureTests(unittest.TestCase):

    def setUp(self):
        self.original_db_path = database.DB_PATH
        self.original_snapshot_dir = memory_engine.SNAPSHOT_DIR
        self.original_current_project_file = memory_engine.CURRENT_PROJECT_FILE
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

        database.DB_PATH = self.temp_path / "sandbox" / "data" / "usmos.db"
        memory_engine.SNAPSHOT_DIR = self.temp_path / "sandbox" / "snapshots"
        memory_engine.CURRENT_PROJECT_FILE = (
            self.temp_path / "sandbox" / "current_project.json"
        )

        initialize_schema()
        self.seed_minioffice()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        memory_engine.SNAPSHOT_DIR = self.original_snapshot_dir
        memory_engine.CURRENT_PROJECT_FILE = self.original_current_project_file
        self.temp_dir.cleanup()

    def seed_minioffice(self):
        memory = MemoryClient("MiniOffice")
        memory.save_decision(
            title="MiniOffice Database Decision",
            content="Decision: MiniOffice will use PostgreSQL instead of SQLite."
        )
        memory.save_decision(
            title="MiniOffice Cloud Rule",
            content="Decision: MiniOffice must run local-only with no cloud access."
        )

    def run_cli(self, argv):
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            exit_code = usmos_cli.main(argv)

        return exit_code, output.getvalue()

    def test_plugin_registry_lists_minioffice(self):
        plugins = PluginRegistry().list_plugins()
        plugin_ids = []

        for plugin in plugins:
            plugin_ids.append(plugin["id"])

        self.assertIn("minioffice", plugin_ids)

    def test_plugin_registry_loads_minioffice(self):
        result = PluginRegistry().load("minioffice")

        self.assertTrue(result["success"])
        self.assertIsInstance(result["plugin"], BasePlugin)
        self.assertEqual(result["info"]["id"], "minioffice")
        self.assertEqual(result["info"]["project_name"], "MiniOffice")

    def test_invalid_plugin_with_direct_sqlite_access_is_rejected(self):
        plugin_root = self.temp_path / "plugins"
        bad_dir = plugin_root / "badplugin"
        bad_dir.mkdir(parents=True)
        module_path = plugin_root / "bad_plugin.py"
        module_path.write_text(
            "import sqlite3\n\n"
            "from src.plugins import BasePlugin\n\n"
            "class BadPlugin(BasePlugin):\n"
            "    def health(self):\n"
            "        return {'success': True}\n"
            "    def ask(self, question):\n"
            "        return {'success': True, 'answer': question}\n",
            encoding="utf-8"
        )
        (bad_dir / "manifest.json").write_text(
            "{\n"
            '  "id": "badplugin",\n'
            '  "name": "Bad Plugin",\n'
            '  "version": "0.1.0",\n'
            '  "entrypoint": "bad_plugin:BadPlugin"\n'
            "}\n",
            encoding="utf-8"
        )
        sys.path.insert(0, str(plugin_root))

        try:
            result = PluginRegistry(plugin_root).load("badplugin")
        finally:
            sys.path.remove(str(plugin_root))

        self.assertFalse(result["success"])
        self.assertIn("MemoryClient only", result["message"])

    def test_plugin_ask_uses_memory_client_answer(self):
        result = PluginRegistry().ask(
            plugin_id="minioffice",
            question="What database does MiniOffice use?"
        )

        self.assertTrue(result["success"])
        self.assertIn("MiniOffice uses PostgreSQL", result["answer"])
        self.assertTrue(result["memory_ids"])
        self.assertTrue(result["answered_without_llm"])

    def test_plugin_health(self):
        result = PluginRegistry().health("minioffice")

        self.assertTrue(result["success"])
        self.assertEqual(result["plugin_id"], "minioffice")
        self.assertTrue(result["database_connected"])
        self.assertFalse(result["cloud"])

    def test_cli_plugin_commands(self):
        exit_code, output = self.run_cli(["plugin-list"])

        self.assertEqual(exit_code, 0)
        self.assertIn("minioffice", output)

        exit_code, output = self.run_cli(["plugin-load", "minioffice"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Plugin loaded:", output)

        exit_code, output = self.run_cli(["plugin-info", "minioffice"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Plugin info:", output)

        exit_code, output = self.run_cli(["plugin-health", "minioffice"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Plugin health:", output)

        exit_code, output = self.run_cli([
            "plugin-ask",
            "minioffice",
            "What database does MiniOffice use?"
        ])

        self.assertEqual(exit_code, 0)
        self.assertIn("Plugin answer:", output)
        self.assertIn("PostgreSQL", output)

    def test_dashboard_data_loads_plugins(self):
        data = dashboard.get_dashboard_data("MiniOffice")
        plugin_ids = []

        for plugin in data["plugins"]:
            plugin_ids.append(plugin["id"])

        self.assertIn("minioffice", plugin_ids)
