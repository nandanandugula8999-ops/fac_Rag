"""Ollama local provider stub (NOT implemented yet per spec).

Present so the router, settings, and UI can list Ollama without research
modules needing a rewrite later. Selecting it raises a clear error.
"""

from __future__ import annotations

from faculty_radar.config import Settings, get_settings


class OllamaError(RuntimeError):
    """Ollama is not wired up yet."""


class OllamaProvider:
    name = "ollama"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def model_id(self) -> str:
        return getattr(self.settings, "ollama_model", "llama3.1:8b")

    def available(self) -> bool:
        return False

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 700,
        temperature: float = 0.0,
    ) -> str:
        raise OllamaError(
            "Ollama provider is not implemented yet. "
            "Use provider 'extractive' (offline) or 'groq' (cloud) for now."
        )
