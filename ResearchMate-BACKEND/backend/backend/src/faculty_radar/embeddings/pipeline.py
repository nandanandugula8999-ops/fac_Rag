"""Build all corpus vectors, reusing unchanged vectors already on disk.

The cache exists for scale: embedding tens of thousands of publications should
not redo unchanged work after every run. Only an exact text-hash match is
reused. Added, removed, or edited documents are embedded fresh, and a changed
model, version, or dimension invalidates the whole cache.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from faculty_radar.config import Settings, get_logger, get_settings
from faculty_radar.embeddings.backends import embed_texts, get_embedder, text_hash
from faculty_radar.embeddings.store import VectorIndex, VectorStore
from faculty_radar.models import CorpusDocument
from faculty_radar.paths import DataPaths, build_paths

logger = get_logger(__name__)


@dataclass(frozen=True)
class EmbeddingResult:
    documents: tuple[CorpusDocument, ...]
    vectors: tuple[np.ndarray, ...]
    index: VectorIndex
    path: Path | None
    stats: dict[str, int | str]


def build_embeddings(
    documents: list[CorpusDocument],
    settings: Settings | None = None,
    paths: DataPaths | None = None,
    *,
    store: bool = True,
    cache_enabled: bool | None = None,
) -> EmbeddingResult:
    """Embed corpus documents and optionally persist the vector index."""
    settings = settings or get_settings()
    paths = paths or build_paths(settings)
    embedder = get_embedder(settings)
    ordered = sorted(documents, key=lambda doc: doc.doc_id)

    if not ordered:
        logger.warning("no corpus documents; no vectors to build")
        return EmbeddingResult(
            documents=(),
            vectors=(),
            index=VectorIndex(
                doc_ids=(),
                vectors=np.zeros((0, settings.embeddings.dimension), dtype=np.float32),
                embedding_model=embedder.model,
                embedding_version=embedder.model_version,
                text_hashes={},
                exists=False,
            ),
            path=None,
            stats={
                "documents": 0,
                "computed": 0,
                "reused": 0,
                "dimension": settings.embeddings.dimension,
                "embedding_model": embedder.model,
            },
        )

    cache_enabled = settings.embeddings.cache_enabled if cache_enabled is None else cache_enabled
    cached = _load_reusable_index(
        ordered, embedder, paths, store=store, cache_enabled=cache_enabled
    )
    computed_texts = [doc.embed_text for doc in ordered if doc.doc_id not in cached]
    computed = (
        embed_texts(computed_texts, settings, batch_size=settings.embeddings.batch_size)
        if computed_texts
        else []
    )
    computed_by_id = {
        doc.doc_id: vector
        for doc, vector in zip(
            [doc for doc in ordered if doc.doc_id not in cached], computed, strict=True
        )
    }
    vectors = tuple({**cached, **computed_by_id}[doc.doc_id] for doc in ordered)
    index = VectorIndex(
        doc_ids=tuple(doc.doc_id for doc in ordered),
        vectors=np.stack(vectors).astype(np.float32, copy=False),
        embedding_model=embedder.model,
        embedding_version=embedder.model_version,
        text_hashes={doc.doc_id: text_hash(doc.embed_text) for doc in ordered},
        exists=True,
    )

    path = (
        VectorStore(paths).write_index(
            ordered,
            list(vectors),
            embedding_model=embedder.model,
            embedding_version=embedder.model_version,
        )
        if store
        else None
    )
    stats = {
        "documents": len(ordered),
        "computed": len(computed),
        "reused": len(cached),
        "dimension": settings.embeddings.dimension,
        "embedding_model": embedder.model,
    }
    logger.info("corpus embeddings built", extra=stats)
    return EmbeddingResult(
        documents=tuple(ordered), vectors=vectors, index=index, path=path, stats=stats
    )


def _load_reusable_index(
    documents: list[CorpusDocument],
    embedder,
    paths: DataPaths,
    *,
    store: bool,
    cache_enabled: bool,
) -> dict[str, np.ndarray]:
    """Return exact-match cached vectors, or nothing when caching is unusable."""
    if not store or not cache_enabled:
        return {}
    index = VectorStore(paths).load_index(embedder.model, embedder.model_version)
    if not index.exists:
        return {}
    try:
        index.ensure_compatible(
            embedding_model=embedder.model,
            embedding_version=embedder.model_version,
            dimension=embedder.dimension,
        )
    except Exception:
        logger.info("ignoring stale vector cache and rebuilding all vectors")
        return {}

    cached_vectors = index.vectors_by_id()
    reusable: dict[str, np.ndarray] = {}
    for doc in documents:
        vector = cached_vectors.get(doc.doc_id)
        if (
            vector is not None
            and vector.shape == (embedder.dimension,)
            and index.text_hashes.get(doc.doc_id) == text_hash(doc.embed_text)
        ):
            reusable[doc.doc_id] = vector
    return reusable
