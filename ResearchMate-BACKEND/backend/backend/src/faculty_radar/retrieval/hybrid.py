"""Hybrid lexical/vector retrieval with reciprocal-rank fusion.

BM25 and vector search fail in opposite ways: BM25 misses paraphrases, while
vectors can miss rare exact terms. RRF fuses their ranked lists without
requiring their incompatible scores to share a scale. A document found by both
retrievers outranks one found by either alone, even at lower individual ranks.

The fused hit keeps both raw component scores and both signal names. That is
not bookkeeping: expertise scoring must know whether a candidate matched
literally, semantically, or both.
"""

from __future__ import annotations

from dataclasses import dataclass

from faculty_radar.config import Settings, get_logger, get_settings
from faculty_radar.models import CorpusDocument, RetrievalHit
from faculty_radar.retrieval.bm25 import KeywordRetriever
from faculty_radar.retrieval.filters import SearchFilters
from faculty_radar.retrieval.semantic import SemanticRetriever

logger = get_logger(__name__)


def fuse_rankings(rankings: list[list[RetrievalHit]], *, rrf_k: int = 60) -> dict[str, float]:
    """Reciprocal-rank fusion over one or more ranked hit lists."""
    if rrf_k <= 0:
        raise ValueError(f"RRF constant must be positive, got {rrf_k}")
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            fused[hit.doc_id] = fused.get(hit.doc_id, 0.0) + 1.0 / (rrf_k + rank)
    return fused


@dataclass
class HybridRetriever:
    """BM25 + vector retrieval fused into one candidate list."""

    documents: list[CorpusDocument]
    settings: Settings | None = None
    candidate_k: int | None = None
    keyword: KeywordRetriever = None  # type: ignore[assignment]
    semantic: SemanticRetriever = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()
        self.keyword = KeywordRetriever(self.documents, self.settings)
        self.semantic = SemanticRetriever(self.documents, self.settings)

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: SearchFilters | None = None,
    ) -> list[RetrievalHit]:
        """Fuse lexical and vector candidates for one query."""
        settings = self.settings or get_settings()
        limit = settings.retrieval.top_k if top_k is None else top_k
        if limit <= 0:
            return []
        candidate_limit = self.candidate_k or max(limit * 5, limit + 10)

        lexical = {
            hit.doc_id: hit
            for hit in self.keyword.search(query, top_k=candidate_limit, filters=filters)
        }
        semantic = {
            hit.doc_id: hit
            for hit in self.semantic.search(query, top_k=candidate_limit, filters=filters)
        }
        if not lexical and not semantic:
            return []

        fused = fuse_rankings(
            [list(lexical.values()), list(semantic.values())],
            rrf_k=settings.retrieval.rrf_k,
        )
        hits = [
            RetrievalHit(
                doc_id=doc_id,
                score=score,
                lexical_score=lexical[doc_id].lexical_score if doc_id in lexical else 0.0,
                semantic_score=semantic[doc_id].semantic_score if doc_id in semantic else 0.0,
                document=(lexical.get(doc_id) or semantic[doc_id]).document,
                signals=_ordered_signals(lexical.get(doc_id), semantic.get(doc_id)),
                matched_fields=sorted(
                    set((lexical.get(doc_id) or semantic[doc_id]).matched_fields)
                    | set((semantic.get(doc_id) or lexical[doc_id]).matched_fields)
                ),
                matched_terms=sorted(
                    set((lexical.get(doc_id) or semantic[doc_id]).matched_terms)
                    | set((semantic.get(doc_id) or lexical[doc_id]).matched_terms)
                ),
            )
            for doc_id, score in fused.items()
        ]
        hits.sort(key=lambda hit: (-hit.score, hit.doc_id))
        for rank, hit in enumerate(hits[:limit], start=1):
            hit.rank = rank
        logger.debug(
            "hybrid retrieval complete",
            extra={
                "query": query,
                "lexical": len(lexical),
                "semantic": len(semantic),
                "returned": min(limit, len(hits)),
            },
        )
        return hits[:limit]


def _ordered_signals(lexical: RetrievalHit | None, semantic: RetrievalHit | None) -> list[str]:
    signals: list[str] = []
    for hit in (lexical, semantic):
        if hit is not None:
            signals.extend(s for s in hit.signals if s not in signals)
    return signals
