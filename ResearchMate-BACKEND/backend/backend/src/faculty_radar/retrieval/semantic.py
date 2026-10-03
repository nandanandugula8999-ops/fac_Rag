"""Vector-space retrieval over corpus embeddings.

This retriever is intentionally backend-agnostic: it scores cosine similarity
against whatever representation Stage 7 produced. With the default offline
hashing backend that representation is lexical hashing, not neural semantics;
with a neural backend it becomes true semantic search. The hit contract does
not change either way, which is what lets hybrid fusion stay honest about which
signal produced each candidate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from faculty_radar.config import Settings, get_logger, get_settings
from faculty_radar.embeddings.backends import embed_texts, get_embedder
from faculty_radar.embeddings.pipeline import build_embeddings
from faculty_radar.embeddings.store import VectorIndex
from faculty_radar.models import CorpusDocument, RetrievalHit
from faculty_radar.normalization.text import tokenize
from faculty_radar.retrieval.filters import SearchFilters, apply_filters

logger = get_logger(__name__)


@dataclass
class SemanticRetriever:
    """Cosine-similarity retriever bound to one corpus snapshot."""

    documents: list[CorpusDocument]
    settings: Settings | None = None
    index: VectorIndex | None = None
    by_id: dict[str, CorpusDocument] = field(init=False)

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()
        self.by_id = {doc.doc_id: doc for doc in self.documents}
        if self.index is None:
            self.index = build_embeddings(self.documents, self.settings, store=False).index
        # Fail loudly if a caller injects vectors for another corpus snapshot.
        missing = set(self.by_id) - set(self.index.doc_ids)
        if missing:
            raise ValueError(f"vector index is missing {len(missing)} corpus documents")

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: SearchFilters | None = None,
    ) -> list[RetrievalHit]:
        """Return vector-space hits for eligible documents, best first."""
        settings = self.settings or get_settings()
        limit = settings.retrieval.top_k if top_k is None else top_k
        if limit <= 0 or not tokenize(query):
            return []

        eligible = {doc.doc_id for doc in apply_filters(self.documents, filters)}
        query_vector = embed_texts([query], settings)[0]
        index = self.index
        assert index is not None
        candidates = index.search(query_vector, top_k=len(eligible))
        selected = [hit for hit in candidates if hit.doc_id in eligible][:limit]

        hits = [
            RetrievalHit(
                doc_id=hit.doc_id,
                score=hit.score,
                lexical_score=0.0,
                semantic_score=hit.score,
                rank=rank,
                document=self.by_id[hit.doc_id],
                signals=["vector"],
                matched_fields=[],
                matched_terms=[],
            )
            for rank, hit in enumerate(selected, start=1)
        ]
        logger.debug(
            "vector retrieval complete",
            extra={
                "query": query,
                "candidates": len(candidates),
                "returned": len(hits),
                "embedding_model": get_embedder(settings).model,
            },
        )
        return hits
