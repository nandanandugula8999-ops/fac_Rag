"""Selecting the citable passages that may reach the generator.

The generator is only as honest as its context. This stage enforces three
budgets from settings: a total cap, a per-faculty cap (diversity of voices),
and a per-document cap (no single passage repeated under different guises),
plus a relevance floor. Duplicates - the same document cited twice - keep only
their strongest relevance.

Relevance here is rank-normalized within the candidate set: the best passage
scores 1.0 and the rest scale by reciprocal rank. Absolute retrieval scores
are not comparable across queries, so carrying them into generation would let
an easy query's weak tail outrank a hard query's best evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from faculty_radar.config import Settings, get_logger, get_settings
from faculty_radar.models import EvidenceItem, ExpertiseMatch

logger = get_logger(__name__)


@dataclass
class EvidenceSelector:
    """Applies selection budgets to expertise-match evidence."""

    settings: Settings | None = None
    matches: list[ExpertiseMatch] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()

    def select(self, matches: list[ExpertiseMatch] | None = None) -> list[EvidenceItem]:
        """Flatten, dedupe, budget, and return citable evidence."""
        settings = self.settings or get_settings()
        candidates = matches if matches is not None else self.matches
        pooled = _dedupe(item for match in candidates for item in match.evidence)
        if not pooled:
            return []

        ranked = sorted(pooled, key=lambda item: (-item.relevance, item.evidence_id))
        budgeted = _apply_budgets(ranked, settings)
        logger.debug(
            "evidence selection complete",
            extra={
                "candidates": len(pooled),
                "selected": len(budgeted),
                "max_items": settings.evidence.max_items,
            },
        )
        return budgeted


def select_evidence(
    matches: list[ExpertiseMatch],
    settings: Settings | None = None,
) -> list[EvidenceItem]:
    """Convenience entry point for evidence selection."""
    return EvidenceSelector(settings).select(matches)


def _dedupe(items) -> list[EvidenceItem]:
    """Keep the strongest relevance per document, deterministically ordered."""
    best: dict[str, EvidenceItem] = {}
    for item in items:
        key = item.doc_id or item.evidence_id
        current = best.get(key)
        if current is None or (
            item.relevance,
            item.evidence_id,
        ) > (current.relevance, current.evidence_id):
            best[key] = item
    return [best[key] for key in sorted(best)]


def _apply_budgets(ranked: list[EvidenceItem], settings: Settings) -> list[EvidenceItem]:
    """Enforce relevance floor, per-faculty/document caps, and total cap."""
    budgets = settings.evidence
    selected: list[EvidenceItem] = []
    per_faculty: dict[str, int] = {}
    per_document: dict[str, int] = {}
    for item in ranked:
        if item.relevance < budgets.min_relevance:
            continue
        faculty_key = item.faculty_id or ""
        if per_faculty.get(faculty_key, 0) >= budgets.max_per_faculty:
            continue
        document_key = item.doc_id or item.evidence_id
        if per_document.get(document_key, 0) >= budgets.max_per_document:
            continue
        per_faculty[faculty_key] = per_faculty.get(faculty_key, 0) + 1
        per_document[document_key] = per_document.get(document_key, 0) + 1
        selected.append(item)
        if len(selected) >= budgets.max_items:
            break
    return selected
