"""Unified LLM Service (plan.md section 29).

Research modules call ONLY this service:

    from faculty_radar.services.llm_service import generate, generate_json

They must NOT import groq/ollama providers directly. The service routes via
providers.get_provider(), enforces evidence-grounded system prompts, and
degrades to extractive evidence-only output when the cloud provider is
unavailable — never to fabricated claims.
"""

from __future__ import annotations

import json

from faculty_radar.config import Settings, get_logger, get_settings

logger = get_logger(__name__)

EVIDENCE_GUARDRAIL = (
    "You are a research assistant. Reason ONLY over the provided evidence. "
    "Do not invent papers, authors, citations, results, datasets, or research gaps. "
    "If the evidence is insufficient, say so explicitly. "
    "Cite evidence by title/year/DOI exactly as given."
)


def generate(
    prompt: str,
    *,
    system: str | None = None,
    settings: Settings | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> dict:
    """Generate text via the configured provider. Returns {text, model, provider}."""
    from faculty_radar.providers import get_provider

    resolved = settings or get_settings()
    provider_name = resolved.llm.provider
    if provider_name == "extractive":
        return {
            "text": "",
            "model": resolved.llm.model,
            "provider": "extractive",
            "degraded": True,
            "note": "extractive provider: no free-form generation; evidence only",
        }
    provider = get_provider(resolved)
    full_system = f"{EVIDENCE_GUARDRAIL}\n\n{system}" if system else EVIDENCE_GUARDRAIL
    text = provider.generate(
        prompt,
        system=full_system,
        max_tokens=max_tokens or resolved.groq.max_tokens,
        temperature=resolved.groq.temperature if temperature is None else temperature,
    )
    return {"text": text, "model": provider.model_id(), "provider": provider.name}


def stream(prompt: str, *, system: str | None = None, settings: Settings | None = None):
    """Yield text deltas from the configured provider (for SSE token streaming).

    Extractive provider yields nothing (it has no free-form generation);
    callers must handle the immediate StopIteration as "no streaming".
    """
    from faculty_radar.providers import get_provider

    resolved = settings or get_settings()
    if resolved.llm.provider == "extractive":
        return
        yield  # make this a generator that yields nothing
    provider = get_provider(resolved)
    full_system = f"{EVIDENCE_GUARDRAIL}\n\n{system}" if system else EVIDENCE_GUARDRAIL
    yield from provider.stream(prompt, system=full_system)


def generate_json(
    prompt: str,
    *,
    system: str | None = None,
    settings: Settings | None = None,
) -> dict:
    """Generate + parse JSON. Returns {data, model, provider} or raises."""
    result = generate(prompt, system=system, settings=settings)
    if result.get("degraded"):
        raise RuntimeError("extractive provider cannot produce structured output")
    text = result["text"]
    # Tolerate code fences.
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        # drop leading language tag line
        lines = cleaned.splitlines()
        if lines and lines[0].strip().isalpha():
            lines = lines[1:]
        cleaned = "\n".join(lines)
    try:
        data = json.loads(cleaned)
    except Exception as exc:
        raise RuntimeError(f"LLM did not return valid JSON: {exc}") from exc
    return {"data": data, "model": result["model"], "provider": result["provider"]}
