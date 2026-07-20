from abc import ABC, abstractmethod

from src.usmos import MemoryClient


class BasePlugin(ABC):
    """Base class for local USMOS plugins.

    Plugins receive a MemoryClient and should use that client for all USMOS
    memory operations.
    """

    def __init__(self, manifest, memory_client):

        if not isinstance(memory_client, MemoryClient):
            raise TypeError("Plugins must receive a MemoryClient instance.")

        self.manifest = manifest
        self.memory = memory_client

    @property
    def plugin_id(self):

        return self.manifest["id"]

    @property
    def name(self):

        return self.manifest["name"]

    @property
    def version(self):

        return self.manifest["version"]

    @property
    def project_name(self):

        return self.manifest.get("project_name") or self.memory.project_name

    def info(self):

        return {
            "id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "description": self.manifest.get("description", ""),
            "project_name": self.project_name,
            "entrypoint": self.manifest["entrypoint"]
        }

    @abstractmethod
    def health(self):
        """Return plugin health details."""

    @abstractmethod
    def ask(self, question):
        """Answer a project question through USMOS memory."""
