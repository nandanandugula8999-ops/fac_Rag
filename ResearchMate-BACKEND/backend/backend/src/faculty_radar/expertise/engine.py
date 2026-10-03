"""Faculty expertise scoring from reranked retrieval hits.

The engine groups reranked hits by faculty and scores seven explainable
signals. Provenance decides the kind of each contribution:

* stated profile/project hits -> STATED
* publication hits with a literal (`bm25`) signal -> EVIDENCE_BASED
* publication hits found only by vectors -> INFERRED

Recency is measured against the newest publication year in the corpus, not the
wall clock, so the same snapshot always scores the same way. A faculty member
with no quotable passage is never returned: an expertise claim without
evidence is exactly what Rule 2 forbids.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from faculty_radar.config import Settings, get_logger, get_settings
from faculty_radar.models import (
    CorpusDocument,
    DocumentType,
    EvidenceItem,
    ExpertiseMatch,
    ExpertiseReport,
    ExpertiseType,
    FacultyProfile,
    NormalizedWork,
    RankingSignal,
    RetrievalHit,
    Status,
)
from faculty_radar.normalization.text import tokenize
from faculty_radar.ranking.rerank import RerankResult, rerank_hits
from faculty_radar.retrieval.filters import SearchFilters
from faculty_radar.retrieval.hybrid import HybridRetriever

logger = get_logger(__name__)

_SIGNAL_NAMES = (
    "explicit_topic",
    "topic_evidence",
    "semantic",
    "keyword",
    "recency",
    "consistency",
    "citations",
)


@dataclass
class ExpertiseEngine:
    """Scores consented faculty profiles against a query."""

    profiles: list[FacultyProfile]
    works: list[NormalizedWork]
    documents: list[CorpusDocument]
    settings: Settings | None = None
    retriever: HybridRetriever = field(init=False)

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()
        self.retriever = HybridRetriever(self.documents, self.settings)

    def find_experts(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: SearchFilters | None = None,
    ) -> ExpertiseReport:
        """Rank faculty with supporting passages for one query."""
        settings = self.settings or get_settings()
        limit = settings.retrieval.top_k if top_k is None else top_k
        if limit <= 0 or not tokenize(query):
            return ExpertiseReport(
                query=query,
                filters=_filters_dict(filters),
                matches=[],
                status=Status.INSUFFICIENT_EVIDENCE,
                total_candidates=0,
            )

        candidates = self.retriever.search(query, top_k=limit * 5, filters=filters)
        reranked = rerank_hits(candidates, query, settings)
        if not reranked.hits:
            return ExpertiseReport(
                query=query,
                filters=_filters_dict(filters),
                matches=[],
                status=Status.INSUFFICIENT_EVIDENCE,
                total_candidates=0,
            )

        groups = _group_by_faculty(reranked, self.profiles)
        matches = _score_groups(query, groups, reranked, self.works, settings)
        matches = [m for m in matches if m.score >= settings.expertise.min_score]
        matches.sort(key=lambda m: (-m.score, m.faculty_id))
        matches = matches[:limit]
        report = ExpertiseReport(
            query=query,
            filters=_filters_dict(filters),
            matches=matches,
            status=Status.OK if matches else Status.INSUFFICIENT_EVIDENCE,
            total_candidates=len(groups),
        )
        logger.debug(
            "expertise search complete",
            extra={
                "query": query,
                "candidates": len(groups),
                "returned": len(matches),
            },
        )
        return report


def find_experts(
    query: str,
    profiles: list[FacultyProfile],
    works: list[NormalizedWork],
    documents: list[CorpusDocument],
    settings: Settings | None = None,
    *,
    top_k: int | None = None,
    filters: SearchFilters | None = None,
) -> ExpertiseReport:
    """Convenience entry point for one-off expertise searches."""
    return ExpertiseEngine(profiles, works, documents, settings).find_experts(
        query, top_k=top_k, filters=filters
    )


def _group_by_faculty(reranked: RerankResult, profiles: list[FacultyProfile]) -> dict[str, dict]:
    by_profile = {p.faculty_id: p for p in profiles if p.consented}
    groups: dict[str, dict] = {}
    for hit in reranked.hits:
        doc = hit.document
        if doc is None or doc.faculty_id not in by_profile:
            continue
        group = groups.setdefault(
            doc.faculty_id, {"profile": by_profile[doc.faculty_id], "hits": []}
        )
        group["hits"].append((hit, reranked.evidence_spans.get(hit.doc_id, "")))
    return groups


def _score_groups(
    query: str,
    groups: dict[str, dict],
    reranked: RerankResult,
    works: list[NormalizedWork],
    settings: Settings,
) -> list[ExpertiseMatch]:
    query_terms = set(tokenize(query))
    works_by_id = {w.openalex_id: w for w in works}
    present_years = [w.year for w in works if w.year is not None]
    present = max(present_years) if present_years else None

    raw: dict[str, dict[str, float]] = {}
    for faculty_id, group in groups.items():
        raw[faculty_id] = _raw_signals(
            query_terms, group["hits"], group["profile"], works_by_id, present, settings
        )
    normalized = _normalize_signals(raw)
    matches = []
    for faculty_id, group in groups.items():
        match = _build_match(
            query, group["profile"], group["hits"], normalized[faculty_id], works_by_id, settings
        )
        if match is not None:
            matches.append(match)
    return matches


def _raw_signals(
    query_terms: set[str],
    hits: list[tuple[RetrievalHit, str]],
    profile: FacultyProfile,
    works_by_id: dict[str, NormalizedWork],
    present: int | None,
    settings: Settings,
) -> dict[str, float]:
    stated = [hit.rerank_score or 0.0 for hit, _ in hits if _is_stated_hit(hit)]
    evidence_hits = [(hit, span) for hit, span in hits if _is_evidence_hit(hit)]
    inferred = [hit.rerank_score or 0.0 for hit, _ in hits if _is_inferred_hit(hit)]
    supporting_works = [
        works_by_id[hit.document.work_id]
        for hit, _ in evidence_hits
        if hit.document and hit.document.work_id and hit.document.work_id in works_by_id
    ]
    supporting_ids = sorted({w.openalex_id for w in supporting_works})
    enough = len(supporting_ids) >= settings.expertise.min_publications_for_evidence

    topic_matched = [
        hit.rerank_score or 0.0 for hit, _ in evidence_hits if "topics" in hit.matched_fields
    ]
    keyword_matched = [
        hit.rerank_score or 0.0 for hit, _ in evidence_hits if "keywords" in hit.matched_fields
    ]
    on_topic = sum(
        1
        for hit, _ in evidence_hits
        if query_terms & set(tokenize(" ".join(hit.document.topics)))
        or query_terms & set(tokenize(" ".join(hit.document.keywords)))
        or query_terms & set(tokenize(hit.document.text))
    )
    years = [w.year for w in supporting_works if w.year is not None]
    latest = max(years) if years else None
    recency = (
        0.5 ** ((present - latest) / settings.expertise.recency_half_life_years)
        if present is not None and latest is not None
        else 0.0
    )
    cited = sum(w.cited_by_count for w in supporting_works)

    values = {
        "explicit_topic": max(stated, default=0.0),
        "topic_evidence": max(topic_matched, default=0.0),
        "semantic": max(inferred, default=0.0),
        "keyword": max(keyword_matched, default=0.0),
        "recency": recency,
        "consistency": on_topic / len(evidence_hits) if evidence_hits else 0.0,
        "citations": cited,
    }
    if not enough:
        # Evidence-based expertise needs enough supporting works; stated and
        # inferred signals are unaffected by this gate.
        for name in ("topic_evidence", "keyword", "recency", "consistency", "citations"):
            values[name] = 0.0
    values["citations"] = float(values["citations"])
    return values


def _normalize_signals(raw: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    normalized: dict[str, dict[str, float]] = {}
    for name in _SIGNAL_NAMES:
        peak = max((values[name] for values in raw.values()), default=0.0)
        for faculty_id, values in raw.items():
            normalized.setdefault(faculty_id, {})[name] = values[name] / peak if peak > 0 else 0.0
    # Citations were compared raw above; log scaling here keeps one highly-cited
    # work from dwarfing every other signal.
    for faculty_id in normalized:
        raw_cited = raw[faculty_id]["citations"]
        peak_cited = max(v["citations"] for v in raw.values())
        normalized[faculty_id]["citations"] = (
            math.log1p(raw_cited) / math.log1p(peak_cited) if peak_cited > 0 else 0.0
        )
    return normalized


def _build_match(
    query: str,
    profile: FacultyProfile,
    hits: list[tuple[RetrievalHit, str]],
    signals: dict[str, float],
    works_by_id: dict[str, NormalizedWork],
    settings: Settings,
) -> ExpertiseMatch | None:
    weights = {
        "explicit_topic": settings.expertise.weight_explicit_topic,
        "topic_evidence": settings.expertise.weight_topic_evidence,
        "semantic": settings.expertise.weight_semantic,
        "keyword": settings.expertise.weight_keyword,
        "recency": settings.expertise.weight_recency,
        "consistency": settings.expertise.weight_consistency,
        "citations": settings.expertise.weight_citations,
    }
    total_weight = sum(weights.values())
    score = sum(weights[name] * signals[name] for name in _SIGNAL_NAMES) / total_weight

    evidence = _evidence_items(hits, works_by_id)
    if not evidence:
        return None
    evidence_weight = sum(
        weights[name] * signals[name]
        for name in ("topic_evidence", "keyword", "recency", "consistency", "citations")
    ) / sum(
        weights[name]
        for name in ("topic_evidence", "keyword", "recency", "consistency", "citations")
    )
    supporting = _supporting_publications(profile, hits)
    matched_topics = _matched_topics(query, hits)
    signal_models = [
        RankingSignal(
            name=name,
            value=signals[name],
            weight=weights[name],
            contribution=weights[name] * signals[name],
            explanation=_signal_explanation(name, profile.faculty_id),
        )
        for name in _SIGNAL_NAMES
        if signals[name] > 0 or name in ("explicit_topic", "topic_evidence", "semantic")
    ]
    return ExpertiseMatch(
        faculty_id=profile.faculty_id,
        faculty_name=profile.name,
        query=query,
        score=score,
        expertise_type=ExpertiseType.INFERRED,
        stated_score=signals["explicit_topic"],
        evidence_score=evidence_weight,
        inferred_score=signals["semantic"],
        signals=signal_models,
        evidence=evidence,
        supporting_publications=supporting,
        institutions=list(profile.institutions),
        matched_topics=matched_topics,
        notes=[
            f"{sum(1 for hit, _ in hits if _is_stated_hit(hit))} stated passage(s), "
            f"{sum(1 for hit, _ in hits if _is_evidence_hit(hit))} evidence passage(s), "
            f"{sum(1 for hit, _ in hits if _is_inferred_hit(hit))} inferred passage(s)"
        ],
    )


def _is_stated_hit(hit: RetrievalHit) -> bool:
    return (
        hit.document is not None
        and hit.document.is_stated
        and hit.document.document_type in (DocumentType.FACULTY_PROFILE, DocumentType.PROJECT)
    )


def _is_evidence_hit(hit: RetrievalHit) -> bool:
    return (
        hit.document is not None
        and hit.document.document_type is DocumentType.PUBLICATION
        and "bm25" in hit.signals
    )


def _is_inferred_hit(hit: RetrievalHit) -> bool:
    return (
        hit.document is not None
        and hit.document.document_type is DocumentType.PUBLICATION
        and "bm25" not in hit.signals
        and "vector" in hit.signals
    )


def _evidence_items(
    hits: list[tuple[RetrievalHit, str]], works_by_id: dict[str, NormalizedWork]
) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    peak = max((hit.rerank_score or 0.0 for hit, _ in hits), default=0.0)
    for hit, span in sorted(
        hits, key=lambda item: (-(item[0].rerank_score or 0.0), item[0].doc_id)
    ):
        doc = hit.document
        if doc is None:
            continue
        quote = span or ""
        if not quote:
            # Only quotable passages become evidence. Metadata-only matches are
            # scored but never cited.
            continue
        work = works_by_id.get(doc.work_id) if doc.work_id else None
        if _is_stated_hit(hit):
            expertise = ExpertiseType.STATED
        elif _is_evidence_hit(hit):
            expertise = ExpertiseType.EVIDENCE_BASED
        else:
            expertise = ExpertiseType.INFERRED
        items.append(
            EvidenceItem(
                evidence_id=f"{doc.doc_id}:{hit.rank or 0}",
                faculty_id=doc.faculty_id,
                work_id=doc.work_id,
                doc_id=doc.doc_id,
                quote=quote,
                title=work.title if work else None,
                authors=[],
                year=doc.year,
                venue=None,
                doi=doc.doi,
                source_url=doc.source_url,
                source_type=doc.document_type,
                relevance=(hit.rerank_score or 0.0) / peak if peak > 0 else 0.0,
                expertise_type=expertise,
            )
        )
    return items[:8]


def _supporting_publications(profile: FacultyProfile, hits) -> list:
    work_ids = {
        hit.document.work_id
        for hit, _ in hits
        if hit.document
        and hit.document.document_type is DocumentType.PUBLICATION
        and hit.document.work_id
    }
    return sorted(
        (p for p in profile.publications if p.work_id in work_ids),
        key=lambda p: (-(p.year or 0), p.work_id),
    )


def _matched_topics(query: str, hits) -> list[str]:
    query_terms = set(tokenize(query))
    topics: set[str] = set()
    for hit, _ in hits:
        doc = hit.document
        if doc is None:
            continue
        for topic in doc.topics:
            if query_terms & set(tokenize(topic)):
                topics.add(topic)
    return sorted(topics)


def _signal_explanation(name: str, faculty_id: str) -> str:
    explanations = {
        "explicit_topic": f"declared expertise for {faculty_id} in the consent registry",
        "topic_evidence": f"retrieved publications of {faculty_id} tagged with query topics",
        "semantic": f"vector-space publication matches for {faculty_id} without literal terms",
        "keyword": f"retrieved publications of {faculty_id} tagged with query keywords",
        "recency": f"recency of supporting publications for {faculty_id}",
        "consistency": f"share of retrieved publications on the query topic for {faculty_id}",
        "citations": f"citations to supporting publications for {faculty_id}",
    }
    return explanations[name]


def _filters_dict(filters: SearchFilters | None) -> dict:
    if filters is None:
        return {}
    return {
        "faculty_ids": list(filters.faculty_ids),
        "institution_ids": list(filters.institution_ids),
        "document_types": [t.value for t in filters.document_types],
        "year_min": filters.year_min,
        "year_max": filters.year_max,
        "stated_only": filters.stated_only,
    }
