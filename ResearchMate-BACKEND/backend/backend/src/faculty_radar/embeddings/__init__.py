"""Embeddings and vector index.

Stage 7 converts consented corpus chunks into vectors. The default backend is a
deterministic hashed n-gram projection: offline, reproducible, and dependency
free. It is explicitly not a neural semantic model, so retrieval built on it
tests ranking, fusion, and provenance plumbing rather than language
understanding.

Every stored vector is namespaced by embedding model and version. A stale index
is refused rather than silently mixed into results.
"""

from faculty_radar.embeddings.backends import (
    EmbeddingError,
    HashingEmbedder,
    embed_texts,
    get_embedder,
    text_hash,
)
from faculty_radar.embeddings.pipeline import EmbeddingResult, build_embeddings
from faculty_radar.embeddings.store import (
    VectorHit,
    VectorIndex,
    VectorIndexError,
    VectorStore,
)

__all__ = [
    "EmbeddingError",
    "EmbeddingResult",
    "HashingEmbedder",
    "VectorHit",
    "VectorIndex",
    "VectorIndexError",
    "VectorStore",
    "build_embeddings",
    "embed_texts",
    "get_embedder",
    "text_hash",
]
