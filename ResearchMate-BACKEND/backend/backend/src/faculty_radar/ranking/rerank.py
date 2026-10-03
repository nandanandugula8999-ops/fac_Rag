"""Field-weighted reranking of hybrid retrieval hits.

Field weights come from settings so the same query always reranks the same
candidates the same way, and so an institution can tune title-vs-topic emphasis
without touching code. Two fusion modes:

* `weighted`: rank by field score, preserving hybrid order on ties.
* `rrf`: fuse the hybrid ranking with the field ranking, which keeps a strong
  hybrid signal competitive against a narrow field match.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from faculty_radar.config import Settings, get_logger, get_settings
from faculty_radar.models import CorpusDocument, RetrievalHit
from faculty_radar.normalization.text import tokenize

logger = get_logger(__name__)

TITLE_PREFIX = "Title:"
ABSTRACT_PREFIX = "Abstract:"
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
METHODS = ("rrf", "weighted")


@dataclass(frozen=True)
class RerankResult:
    hits: tuple[RetrievalHit, ...]
    evidence_spans: dict[str, str]
    method: str
    query: str


def rerank_hits(
    hits: list[RetrievalHit],
    query: str,
    settings: Settings | None = None,
    *,
    method: str | None = None,
    top_k: int | None = None,
) -> RerankResult:
    """Rerank hybrid hits and attach a verbatim evidence span to each."""
    settings = settings or get_settings()
    resolved_method = settings.ranking.method if method is None else method
    if resolved_method not in METHODS:
        raise ValueError(f"unknown rerank method {resolved_method!r}")
    limit = settings.ranking.top_k if top_k is None else top_k
    if limit <= 0 or not hits:
        return RerankResult(hits=(), evidence_spans={}, method=resolved_method, query=query)

    query_terms = Counter(tokenize(query))
    if not query_terms:
        return RerankResult(hits=(), evidence_spans={}, method=resolved_method, query=query)

    scored = [_score_hit(hit, query_terms, settings) for hit in hits]
    if resolved_method == "weighted":
        ordered = _order_weighted(hits, scored)
    else:
        ordered = _order_rrf(hits, scored, rrf_k=settings.ranking.rrf_k)

    reranked: list[RetrievalHit] = []
    spans: dict[str, str] = {}
    for rank, (hit, score, matched_terms, matched_fields, span) in enumerate(
        ordered[:limit], start=1
    ):
        reranked.append(
            hit.model_copy(
                update={
                    "rerank_score": score,
                    "rank": rank,
                    "signals": [*hit.signals, f"rerank:{resolved_method}"],
                    "matched_terms": matched_terms,
                    "matched_fields": matched_fields,
                }
            )
        )
        spans[hit.doc_id] = span
    logger.debug(
        "reranking complete",
        extra={"query": query, "candidates": len(hits), "returned": len(reranked)},
    )
    return RerankResult(
        hits=tuple(reranked), evidence_spans=spans, method=resolved_method, query=query
    )


def _score_hit(
    hit: RetrievalHit, query_terms: Counter[str], settings: Settings
) -> tuple[float, list[str], list[str], str]:
    """Field-weighted score plus the refined match explanation."""
    doc = hit.document
    if doc is None:
        return 0.0, [], [], ""

    fields = _field_counters(doc)
    weights = {
        "title": settings.ranking.title_weight,
        "abstract": settings.ranking.abstract_weight,
        "topics": settings.ranking.topic_weight,
        "keywords": settings.ranking.keyword_weight,
    }
    score = 0.0
    matched_terms: set[str] = set()
    matched_fields: set[str] = set()
    for name, counts in fields.items():
        for term, query_count in query_terms.items():
            count = counts.get(term, 0)
            if count:
                score += weights[name] * query_count * count
                matched_terms.add(term)
                matched_fields.add(name)
    ordered_terms = sorted(matched_terms)
    return score, ordered_terms, sorted(matched_fields), _evidence_span(doc, ordered_terms)


def _field_counters(doc: CorpusDocument) -> dict[str, Counter[str]]:
    title, abstract = _titled_sections(doc.text)
    return {
        "title": Counter(tokenize(title)),
        "abstract": Counter(tokenize(abstract)),
        "topics": Counter(tokenize(" ".join(doc.topics))),
        "keywords": Counter(tokenize(" ".join(doc.keywords))),
    }


def _titled_sections(text: str) -> tuple[str, str]:
    title = ""
    abstract = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(TITLE_PREFIX):
            title = stripped[len(TITLE_PREFIX) :].strip()
        elif stripped.startswith(ABSTRACT_PREFIX):
            abstract = stripped[len(ABSTRACT_PREFIX) :].strip()
    return title, abstract


def _evidence_span(doc: CorpusDocument, matched_terms: list[str]) -> str:
    """First text sentence covering the most matched terms.

    Returns an empty string when nothing in the prose matches verbatim, rather
    than inventing a span. Metadata-only matches are scored but not quotable.
    """
    if not matched_terms:
        return ""
    terms = set(matched_terms)
    best = ""
    best_overlap = 0
    for sentence in _SENTENCE_SPLIT.split(doc.text.strip()):
        overlap = len(terms & set(tokenize(sentence)))
        if overlap > best_overlap:
            best = sentence.strip()
            best_overlap = overlap
    return best[:500]


def _order_weighted(
    hits: list[RetrievalHit],
    scored: list[tuple[float, list[str], list[str], str]],
) -> list[tuple[RetrievalHit, float, list[str], list[str], str]]:
    """Field score first, hybrid order preserved on ties via stable sort."""
    hybrid_order = sorted(hits, key=lambda hit: (-hit.score, hit.doc_id))
    by_id = {
        hit.doc_id: (score, terms, fields, span)
        for hit, (score, terms, fields, span) in zip(hits, scored, strict=True)
    }
    ordered = sorted(
        ((hit, *by_id[hit.doc_id]) for hit in hybrid_order),
        key=lambda item: -item[1],
    )
    return [(hit, score, terms, fields, span) for hit, score, terms, fields, span in ordered]


def _order_rrf(
    hits: list[RetrievalHit],
    scored: list[tuple[float, list[str], list[str], str]],
    *,
    rrf_k: int,
) -> list[tuple[RetrievalHit, float, list[str], list[str], str]]:
    """Fuse hybrid ranking with field ranking."""
    if rrf_k <= 0:
        raise ValueError(f"RRF constant must be positive, got {rrf_k}")
    hybrid_rank = {
        hit.doc_id: rank
        for rank, hit in enumerate(sorted(hits, key=lambda hit: (-hit.score, hit.doc_id)), start=1)
    }
    field_rank = {
        hit.doc_id: rank
        for rank, (hit, (score, _, _, _)) in enumerate(
            sorted(
                zip(hits, scored, strict=True),
                key=lambda item: (-item[1][0], item[0].doc_id),
            ),
            start=1,
        )
    }
    ordered = []
    for hit, (_score, terms, fields, span) in zip(hits, scored, strict=True):
        fused = 1.0 / (rrf_k + hybrid_rank[hit.doc_id]) + 1.0 / (rrf_k + field_rank[hit.doc_id])
        ordered.append((hit, fused, terms, fields, span))
    ordered.sort(key=lambda item: (-item[1], item[0].doc_id))
    return ordered
