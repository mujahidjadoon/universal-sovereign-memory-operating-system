from src.plugins.base import BasePlugin


class MiniOfficePlugin(BasePlugin):
    """Demo plugin for the MiniOffice project."""

    def health(self):

        client_health = self.memory.health()

        return {
            "success": client_health["database_connected"],
            "plugin_id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "project_name": self.project_name,
            "database_connected": client_health["database_connected"],
            "cloud": False,
            "message": "MiniOffice plugin is local and uses MemoryClient."
        }

    def ask(self, question):

        result = self.memory.answer(question)

        return {
            "success": True,
            "plugin_id": self.plugin_id,
            "project_name": self.project_name,
            "question": question,
            "answer": result.answer,
            "memory_ids": result.memory_ids,
            "trust_scores": result.trust_scores,
            "answered_without_llm": result.answered_without_llm,
            "duration_seconds": result.total_duration_seconds
        }
