"""LLM provider abstraction.

Architecture (plan.md section 29):

    Research Module
        -> Unified LLM Service (services/llm_service.py)
        -> Model Router (here, via get_provider)
        -> Selected Provider (groq / ollama / extractive)
        -> API

Rules:
- GROQ_API_KEY stays server-side (settings.groq.api_key, never frontend).
- Research modules never import a concrete provider; they call the service.
- Ollama is stubbed for later: selecting it raises a clear error instead of
  silently falling back, so adding it later needs no rewrite.
- The default remains `extractive` so existing Faculty Discovery / RAG keeps
  working offline with zero key configured.
"""

from __future__ import annotations

from typing import Protocol

from faculty_radar.config import Settings


class LLMProvider(Protocol):
    """Minimal contract every provider implements."""

    name: str

    def available(self) -> bool:
        """True when the provider is configured and usable."""
        ...

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 700,
        temperature: float = 0.0,
    ) -> str:
        """Generate one completion. Must not fabricate citations."""
        ...

    def model_id(self) -> str:
        """Configured model identifier for transparency / responses."""
        ...


def get_provider(settings: Settings | None = None):
    """Model Router: return the configured provider instance.

    Only this function (and the unified service) may import concrete
    providers, keeping research modules decoupled.
    """
    from faculty_radar.config import get_settings

    resolved = settings or get_settings()
    provider_name = resolved.llm.provider

    if provider_name == "extractive":
        from faculty_radar.providers.extractive_provider import ExtractiveProvider

        return ExtractiveProvider(resolved)
    if provider_name == "groq":
        from faculty_radar.providers.groq_provider import GroqProvider

        return GroqProvider(resolved)
    if provider_name == "ollama":
        from faculty_radar.providers.ollama_provider import OllamaProvider

        return OllamaProvider(resolved)
    raise ValueError(f"unknown LLM provider {provider_name!r}")


def available_providers(settings: Settings | None = None) -> list[dict]:
    """Provider/model inventory for GET /api/ai/providers (no secrets)."""
    from faculty_radar.config import get_settings

    resolved = settings or get_settings()
    out: list[dict] = []
    for name in ("extractive", "groq", "ollama"):
        try:
            if name == "extractive":
                from faculty_radar.providers.extractive_provider import ExtractiveProvider

                p = ExtractiveProvider(resolved)
            elif name == "groq":
                from faculty_radar.providers.groq_provider import GroqProvider

                p = GroqProvider(resolved)
            else:
                from faculty_radar.providers.ollama_provider import OllamaProvider

                p = OllamaProvider(resolved)
            out.append(
                {
                    "name": name,
                    "model": p.model_id(),
                    "available": p.available(),
                    "configured": resolved.llm.provider == name,
                }
            )
        except Exception:
            out.append({"name": name, "model": None, "available": False, "configured": False})
    return out
