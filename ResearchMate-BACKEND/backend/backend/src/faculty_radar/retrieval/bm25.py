"""BM25 lexical retrieval over corpus documents.

The indexed text is each document's `embed_text`: declared topics first, then
the full chunk text. That choice matters for faculty discovery. A query for an
exact research phrase should match a publication tagged with that topic even
when the abstract paraphrases it.

IDF statistics are global while eligibility is filtered. In other words, rare
terms remain rare even when the caller restricts results to one faculty member
or year range; filters decide candidacy, never term importance.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from faculty_radar.config import Settings, get_logger, get_settings
from faculty_radar.models import CorpusDocument, RetrievalHit
from faculty_radar.normalization.text import tokenize
from faculty_radar.retrieval.filters import SearchFilters, apply_filters

logger = get_logger(__name__)


@dataclass(frozen=True)
class BM25Index:
    """Precomputed corpus statistics for deterministic BM25 scoring."""

    doc_ids: tuple[str, ...]
    doc_lengths: dict[str, int]
    average_length: float
    doc_frequencies: dict[str, int]
    term_frequencies: dict[str, Counter[str]]
    document_count: int

    @classmethod
    def build(cls, documents: list[CorpusDocument]) -> BM25Index:
        doc_ids: list[str] = []
        doc_lengths: dict[str, int] = {}
        doc_frequencies: Counter[str] = Counter()
        term_frequencies: dict[str, Counter[str]] = {}

        for doc in documents:
            tokens = tokenize(doc.embed_text)
            counts = Counter(tokens)
            doc_ids.append(doc.doc_id)
            doc_lengths[doc.doc_id] = len(tokens)
            term_frequencies[doc.doc_id] = counts
            doc_frequencies.update(counts.keys())

        average = sum(doc_lengths.values()) / len(doc_lengths) if doc_lengths else 0.0
        return cls(
            doc_ids=tuple(doc_ids),
            doc_lengths=doc_lengths,
            average_length=average,
            doc_frequencies=dict(doc_frequencies),
            term_frequencies=term_frequencies,
            document_count=len(doc_ids),
        )

    def score(self, query_terms: Counter[str], doc_id: str, *, k1: float, b: float) -> float:
        """Score one document against already-counted query terms."""
        frequencies = self.term_frequencies.get(doc_id, Counter())
        doc_length = self.doc_lengths.get(doc_id, 0)
        if not frequencies or self.average_length <= 0:
            return 0.0

        total = 0.0
        for term, query_count in query_terms.items():
            frequency = frequencies.get(term, 0)
            if not frequency:
                continue
            doc_frequency = self.doc_frequencies.get(term, 0)
            # Plus-one smoothed IDF: unseen terms approach, but never reach, zero.
            idf = math.log(1 + (self.document_count - doc_frequency + 0.5) / (doc_frequency + 0.5))
            normalized_length = 1 - b + b * (doc_length / self.average_length)
            saturation = frequency * (k1 + 1) / (frequency + k1 * normalized_length)
            total += query_count * idf * saturation
        return total


@dataclass
class KeywordRetriever:
    """Stateful BM25 retriever bound to one consented corpus snapshot."""

    documents: list[CorpusDocument]
    settings: Settings | None = None
    index: BM25Index = field(init=False)

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()
        self.index = BM25Index.build(self.documents)

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: SearchFilters | None = None,
    ) -> list[RetrievalHit]:
        """Return BM25 hits for eligible documents, best first."""
        settings = self.settings or get_settings()
        limit = settings.retrieval.top_k if top_k is None else top_k
        if limit <= 0:
            return []

        query_terms = Counter(tokenize(query))
        if not query_terms:
            return []

        eligible = {doc.doc_id for doc in apply_filters(self.documents, filters)}
        by_id = {doc.doc_id: doc for doc in self.documents}
        scored: list[tuple[float, str]] = []
        for doc_id in self.index.doc_ids:
            if doc_id not in eligible:
                continue
            score = self.index.score(
                query_terms,
                doc_id,
                k1=settings.retrieval.bm25_k1,
                b=settings.retrieval.bm25_b,
            )
            if score > 0:
                scored.append((score, doc_id))
        scored.sort(key=lambda item: (-item[0], item[1]))

        hits: list[RetrievalHit] = []
        for rank, (score, doc_id) in enumerate(scored[:limit], start=1):
            doc = by_id[doc_id]
            matched_terms = sorted(
                term for term in query_terms if self.index.term_frequencies[doc_id].get(term, 0) > 0
            )
            hits.append(
                RetrievalHit(
                    doc_id=doc_id,
                    score=score,
                    lexical_score=score,
                    semantic_score=0.0,
                    rank=rank,
                    document=doc,
                    signals=["bm25"],
                    matched_fields=_matched_fields(doc, matched_terms),
                    matched_terms=matched_terms,
                )
            )
        logger.debug(
            "keyword retrieval complete",
            extra={"query": query, "candidates": len(scored), "returned": len(hits)},
        )
        return hits


def keyword_search(
    documents: list[CorpusDocument],
    query: str,
    settings: Settings | None = None,
    *,
    top_k: int | None = None,
    filters: SearchFilters | None = None,
) -> list[RetrievalHit]:
    """Convenience entry point for one-off keyword searches."""
    return KeywordRetriever(documents, settings).search(query, top_k=top_k, filters=filters)


def _matched_fields(doc: CorpusDocument, matched_terms: list[str]) -> list[str]:
    """Name the document fields containing each matched query term."""
    if not matched_terms:
        return []
    field_tokens = {
        "topics": set(tokenize(" ".join(doc.topics))),
        "keywords": set(tokenize(" ".join(doc.keywords))),
        "text": set(tokenize(doc.text)),
    }
    matched = {
        field
        for field, tokens in field_tokens.items()
        if any(term in tokens for term in matched_terms)
    }
    return sorted(matched)
