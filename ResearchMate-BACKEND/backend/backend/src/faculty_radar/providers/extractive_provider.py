"""Extractive provider: deterministic offline fallback (existing behavior).

Wraps the historical extractive generator so the router can treat it like
any other provider. Research modules never call this directly.
"""

from __future__ import annotations

from faculty_radar.config import Settings, get_settings


class ExtractiveProvider:
    name = "extractive"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def available(self) -> bool:
        return True

    def model_id(self) -> str:
        return self.settings.llm.model

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 700,
        temperature: float = 0.0,
    ) -> str:
        # Extractive has no prompt-following: callers (rag pipeline) build
        # answers from evidence directly. This path exists so the unified
        # service has a graceful offline degradation.
        raise NotImplementedError(
            "extractive provider does not do free-form generation; "
            "use faculty_radar.llm.generate.generate_answer for RAG answers"
        )
