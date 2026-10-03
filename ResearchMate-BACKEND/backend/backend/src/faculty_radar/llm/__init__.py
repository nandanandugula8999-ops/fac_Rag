"""LLM access layer.

Stage 15a of the pipeline. A thin, swappable boundary around the model
provider: provider selection, prompt construction, deterministic settings, and
a disk cache for repeated runs.

The default `extractive` provider is not a language model at all. It is a
deterministic summarizer that can only restate supplied evidence, so the RAG
path is testable without an API key and the system degrades to evidence-only
output rather than invention. Every answer it produces still passes
verification before being returned. Selecting a network provider without its
dependency configured raises an explicit error instead of silently degrading.
"""

from faculty_radar.llm.cache import LlmCache, cached_answer_key
from faculty_radar.llm.generate import LlmError, generate_answer

__all__ = [
    "LlmCache",
    "LlmError",
    "cached_answer_key",
    "generate_answer",
    # Unified service lives in services.llm_service; providers/ holds the
    # router + groq/ollama/extractive implementations. Research modules must
    # import services.llm_service, never a concrete provider.
]
