"""End-to-end grounded question answering over consented faculty data.

The pipeline has no step that can introduce a fact: expertise matches carry
evidence, evidence selection only filters, context assembly only drops whole
items, the extractive generator only restates, and verification rejects
anything the corpus cannot vouch for. A question with no supporting evidence
returns `insufficient_evidence`, never a plausible-sounding guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from faculty_radar.config import Settings, get_logger, get_settings
from faculty_radar.evidence.selection import select_evidence
from faculty_radar.expertise.engine import ExpertiseEngine
from faculty_radar.llm.generate import generate_answer
from faculty_radar.models import (
    Answer,
    CorpusDocument,
    EvidenceItem,
    FacultyProfile,
    NormalizedWork,
    Status,
)
from faculty_radar.paths import DataPaths, build_paths
from faculty_radar.retrieval.filters import SearchFilters
from faculty_radar.verification.checks import verify_answer

logger = get_logger(__name__)


@dataclass
class RagPipeline:
    """Expertise -> evidence -> generation -> verification for one corpus."""

    profiles: list[FacultyProfile]
    works: list[NormalizedWork]
    documents: list[CorpusDocument]
    settings: Settings | None = None
    paths: DataPaths | None = None
    engine: ExpertiseEngine = field(init=False)

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()
        self.paths = self.paths or build_paths(self.settings)
        self.engine = ExpertiseEngine(self.profiles, self.works, self.documents, self.settings)

    def answer(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: SearchFilters | None = None,
    ) -> Answer:
        """Answer one query, verified, or return insufficient_evidence."""
        settings = self.settings or get_settings()
        paths = self.paths or build_paths(settings)

        report = self.engine.find_experts(query, top_k=top_k, filters=filters)
        if report.status is Status.INSUFFICIENT_EVIDENCE or not report.matches:
            logger.debug("RAG short-circuit: no expertise matches", extra={"query": query})
            return Answer(
                query=query,
                answer_text=(
                    "insufficient_evidence: no consented faculty evidence "
                    "supports an answer to this query."
                ),
                expertise_matches=report.matches,
                status=Status.INSUFFICIENT_EVIDENCE,
                warnings=["no expertise matches"],
                llm_model=settings.llm.model,
            )

        evidence = select_evidence(report.matches, settings)
        context = _fit_context(evidence, settings.rag.max_context_chars)
        if not context:
            return Answer(
                query=query,
                answer_text=(
                    "insufficient_evidence: supporting passages exist but none "
                    "fit the context budget intact."
                ),
                expertise_matches=report.matches,
                evidence=list(evidence),
                status=Status.INSUFFICIENT_EVIDENCE,
                warnings=["context budget excluded all evidence"],
                llm_model=settings.llm.model,
            )

        faculty_names = {p.faculty_id: p.name for p in self.profiles}
        draft = generate_answer(query, context, faculty_names, settings, paths)
        draft = draft.model_copy(
            update={"expertise_matches": report.matches, "evidence": list(context)}
        )
        verified = verify_answer(draft, self.documents, self.works, settings)
        logger.debug(
            "RAG answer complete",
            extra={
                "query": query,
                "claims": len(verified.answer.claims),
                "verified": verified.verified,
            },
        )
        return verified.answer


def answer_query(
    query: str,
    profiles: list[FacultyProfile],
    works: list[NormalizedWork],
    documents: list[CorpusDocument],
    settings: Settings | None = None,
    paths: DataPaths | None = None,
    *,
    top_k: int | None = None,
    filters: SearchFilters | None = None,
) -> Answer:
    """Convenience entry point for one-off grounded answers."""
    return RagPipeline(profiles, works, documents, settings, paths).answer(
        query, top_k=top_k, filters=filters
    )


def _fit_context(evidence: list[EvidenceItem], max_chars: int) -> list[EvidenceItem]:
    """Keep whole passages that fit; drop the rest rather than truncating."""
    fitted: list[EvidenceItem] = []
    total = 0
    for item in evidence:
        if total + len(item.quote) > max_chars:
            continue
        fitted.append(item)
        total += len(item.quote)
    return fitted
