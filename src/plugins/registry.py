import importlib
import inspect
import json
from pathlib import Path

from src.plugins.base import BasePlugin
from src.usmos import MemoryClient


REQUIRED_MANIFEST_FIELDS = [
    "id",
    "name",
    "version",
    "entrypoint"
]

FORBIDDEN_PLUGIN_IMPORTS = [
    "sqlite3",
    "src.memory",
    "memory_engine",
    "src.storage"
]


class PluginRegistry:
    """Loads local USMOS plugins from manifest files."""

    def __init__(self, plugins_path=None):

        self.plugins_path = Path(plugins_path or Path(__file__).resolve().parent)
        self.loaded_plugins = {}

    def _manifest_files(self):

        manifest_files = []

        for manifest_file in self.plugins_path.glob("*/manifest.json"):
            manifest_files.append(manifest_file)

        return sorted(manifest_files)

    def _read_manifest(self, manifest_file):

        with open(manifest_file, "r", encoding="utf-8") as file:
            manifest = json.load(file)

        manifest["_manifest_file"] = str(manifest_file)
        manifest["_plugin_dir"] = str(manifest_file.parent)

        return manifest

    def validate_manifest(self, manifest):

        missing_fields = []

        for field in REQUIRED_MANIFEST_FIELDS:
            if not manifest.get(field):
                missing_fields.append(field)

        if missing_fields:
            return {
                "success": False,
                "message": (
                    "Invalid plugin manifest. Missing fields: "
                    + ", ".join(missing_fields)
                )
            }

        if ":" not in manifest["entrypoint"]:
            return {
                "success": False,
                "message": "Invalid plugin manifest. Entrypoint must use module:class."
            }

        return {
            "success": True,
            "message": "Manifest is valid."
        }

    def discover(self):

        manifests = []

        for manifest_file in self._manifest_files():
            manifest = self._read_manifest(manifest_file)
            validation = self.validate_manifest(manifest)

            if validation["success"]:
                manifests.append(manifest)

        return manifests

    def list_plugins(self):

        plugins = []

        for manifest in self.discover():
            plugins.append({
                "id": manifest["id"],
                "name": manifest["name"],
                "version": manifest["version"],
                "description": manifest.get("description", ""),
                "project_name": manifest.get("project_name"),
                "loaded": manifest["id"] in self.loaded_plugins
            })

        return plugins

    def find_manifest(self, plugin_id):

        for manifest_file in self._manifest_files():
            manifest = self._read_manifest(manifest_file)

            if manifest.get("id") == plugin_id:
                return manifest

        return None

    def _load_class(self, entrypoint):

        module_name, class_name = entrypoint.split(":", 1)
        module = importlib.import_module(module_name)
        plugin_class = getattr(module, class_name)

        return module, plugin_class

    def _reject_direct_storage_access(self, module):

        try:
            source = inspect.getsource(module)
        except OSError:
            source = ""

        for forbidden_import in FORBIDDEN_PLUGIN_IMPORTS:
            if forbidden_import in source:
                return {
                    "success": False,
                    "message": (
                        "Invalid plugin. Plugins must use MemoryClient only; "
                        f"found direct storage reference: {forbidden_import}"
                    )
                }

        return {
            "success": True,
            "message": "Plugin does not reference forbidden storage modules."
        }

    def load(self, plugin_id, project_name=None):

        manifest = self.find_manifest(plugin_id)

        if not manifest:
            return {
                "success": False,
                "message": f"Plugin not found: {plugin_id}",
                "plugin": None
            }

        validation = self.validate_manifest(manifest)

        if not validation["success"]:
            return {
                "success": False,
                "message": validation["message"],
                "plugin": None
            }

        try:
            module, plugin_class = self._load_class(manifest["entrypoint"])
        except (ImportError, AttributeError) as error:
            return {
                "success": False,
                "message": f"Could not load plugin entrypoint: {error}",
                "plugin": None
            }

        storage_validation = self._reject_direct_storage_access(module)

        if not storage_validation["success"]:
            return {
                "success": False,
                "message": storage_validation["message"],
                "plugin": None
            }

        if not issubclass(plugin_class, BasePlugin):
            return {
                "success": False,
                "message": "Invalid plugin. Plugin class must extend BasePlugin.",
                "plugin": None
            }

        plugin_project = project_name or manifest.get("project_name")
        memory_client = MemoryClient(project_name=plugin_project)
        plugin = plugin_class(
            manifest=manifest,
            memory_client=memory_client
        )
        self.loaded_plugins[plugin_id] = plugin

        return {
            "success": True,
            "message": f"Plugin loaded: {plugin_id}",
            "plugin": plugin,
            "info": plugin.info()
        }

    def info(self, plugin_id):

        plugin = self.loaded_plugins.get(plugin_id)

        if plugin:
            return {
                "success": True,
                "plugin": plugin.info()
            }

        load_result = self.load(plugin_id)

        if not load_result["success"]:
            return {
                "success": False,
                "message": load_result["message"]
            }

        return {
            "success": True,
            "plugin": load_result["plugin"].info()
        }

    def health(self, plugin_id):

        load_result = self.load(plugin_id)

        if not load_result["success"]:
            return load_result

        return load_result["plugin"].health()

    def ask(self, plugin_id, question):

        load_result = self.load(plugin_id)

        if not load_result["success"]:
            return load_result

        return load_result["plugin"].ask(question)
