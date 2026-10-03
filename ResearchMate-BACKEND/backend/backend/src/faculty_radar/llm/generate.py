"""Answer generation behind the provider boundary.

`generate_answer` is the only function the RAG pipeline calls. It dispatches
on the configured provider and always returns a draft `Answer` whose claims
cite the supplied evidence. Verification runs afterwards and independently -
nothing generated here is trusted on arrival.
"""

from __future__ import annotations

from faculty_radar.config import Settings, get_logger, get_settings
from faculty_radar.llm.cache import LlmCache, cached_answer_key
from faculty_radar.models import (
    Answer,
    AnswerCitation,
    AnswerClaim,
    EvidenceItem,
    ExpertiseType,
    Status,
)
from faculty_radar.paths import DataPaths, build_paths

logger = get_logger(__name__)


class LlmError(RuntimeError):
    """The configured LLM provider cannot be used."""


def generate_answer(
    query: str,
    evidence: list[EvidenceItem],
    faculty_names: dict[str, str],
    settings: Settings | None = None,
    paths: DataPaths | None = None,
) -> Answer:
    """Generate a draft answer strictly from the supplied evidence.

    This is the Faculty Discovery path and is ALWAYS extractive by design:
    the Research-AI provider setting (groq/ollama) never changes faculty
    generation. Unknown provider names still raise instead of silently
    degrading.
    """
    settings = settings or get_settings()
    paths = paths or build_paths(settings)
    provider = settings.llm.provider
    if provider not in ("extractive", "groq", "ollama", "openai"):
        raise LlmError(
            f"LLM provider {provider!r} is unknown; "
            "expected 'extractive', 'groq', 'ollama', or 'openai'"
        )
    if not evidence:
        return Answer(
            query=query,
            answer_text="insufficient_evidence: no citable passages support an answer.",
            claims=[],
            citations=[],
            status=Status.INSUFFICIENT_EVIDENCE,
            warnings=["generator received no evidence"],
            llm_model=settings.llm.model,
        )

    cache = LlmCache(paths)
    key = cached_answer_key(settings.llm.model, query, evidence)
    if settings.llm.cache_enabled:
        cached = cache.get(key)
        if cached is not None:
            logger.debug("LLM cache hit", extra={"key": key[:16]})
            return cached

    answer = _extractive_answer(query, evidence, faculty_names, settings)
    if settings.llm.cache_enabled:
        cache.set(key, answer)
    return answer


def _extractive_answer(
    query: str,
    evidence: list[EvidenceItem],
    faculty_names: dict[str, str],
    settings: Settings,
) -> Answer:
    """One claim per faculty, each claim a restatement of its own passages.

    No sentence here originates outside the evidence list: claim text is
    composed of verbatim quotes plus fixed scaffolding, and every citation is
    copied field-for-field from an evidence item. The claim's expertise label
    is the strongest label among its own citations, so verification can check
    the label against the evidence instead of trusting it.
    """
    by_faculty: dict[str, list[EvidenceItem]] = {}
    for item in evidence:
        by_faculty.setdefault(item.faculty_id or "", []).append(item)

    claims: list[AnswerClaim] = []
    citations: list[AnswerCitation] = []
    for faculty_id in sorted(by_faculty):
        items = by_faculty[faculty_id]
        name = faculty_names.get(faculty_id, faculty_id or "Unknown researcher")
        quoted = " ".join(item.quote for item in items)
        label = _strongest_label(items)
        claim_citations = [
            AnswerCitation(
                evidence_id=item.evidence_id,
                work_id=item.work_id,
                faculty_id=item.faculty_id,
                title=item.title,
                year=item.year,
                doi=item.doi,
                source_url=item.source_url,
                quote=item.quote,
            )
            for item in items
        ]
        claims.append(
            AnswerClaim(
                text=f"{name} [{label.value}]: {quoted}",
                citations=claim_citations,
                expertise_type=label,
            )
        )
        citations.extend(claim_citations)

    answer_text = "\n\n".join(f"Evidence for '{query}':\n" + claim.text for claim in claims)
    return Answer(
        query=query,
        answer_text=answer_text,
        claims=claims,
        citations=citations,
        evidence=list(evidence),
        status=Status.OK,
        llm_model=settings.llm.model,
    )


def _strongest_label(items: list[EvidenceItem]) -> ExpertiseType:
    order = {
        ExpertiseType.STATED: 3,
        ExpertiseType.EVIDENCE_BASED: 2,
        ExpertiseType.INFERRED: 1,
    }
    return max((item.expertise_type for item in items), key=lambda t: order[t])
