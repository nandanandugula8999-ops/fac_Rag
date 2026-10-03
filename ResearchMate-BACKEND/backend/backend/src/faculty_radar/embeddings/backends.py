"""Deterministic embedding backends.

The hashing backend projects token unigrams and bigrams into a fixed-width
vector with a signed hash. Term frequency is preserved, collisions partly
cancel through random signs, and the final vector is L2-normalized for cosine
retrieval. The same text and dimension always produce the same vector.

Neural providers named in settings are intentionally unsupported here until
their optional dependencies and model artifacts are part of the environment.
Selecting one raises an explicit error instead of silently falling back to a
different representation.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from itertools import pairwise

import numpy as np

from faculty_radar.config import Settings, get_logger, get_settings
from faculty_radar.normalization.text import tokenize

logger = get_logger(__name__)

HASHING_MODEL_VERSION = "1"


class EmbeddingError(RuntimeError):
    """The requested embedding backend cannot be used."""


def text_hash(text: str) -> str:
    """Stable content fingerprint used for cache reuse and staleness checks."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ngrams(tokens: list[str]) -> Counter[str]:
    """Unigram and adjacent-bigram counts for the hashing projection."""
    counts: Counter[str] = Counter(tokens)
    counts.update(f"{left} {right}" for left, right in pairwise(tokens))
    return counts


def _hash_feature(feature: str, dimension: int) -> tuple[int, float]:
    """Map one n-gram to a signed vector position."""
    digest = hashlib.sha256(feature.encode("utf-8")).digest()
    index = int.from_bytes(digest[:8], "big") % dimension
    sign = 1.0 if digest[8] & 1 else -1.0
    return index, sign


class HashingEmbedder:
    """Offline hashed n-gram embedder with no model downloads."""

    def __init__(self, dimension: int, *, max_tokens: int = 8192) -> None:
        if dimension <= 0:
            raise EmbeddingError(f"embedding dimension must be positive, got {dimension}")
        if max_tokens <= 0:
            raise EmbeddingError(f"max tokens must be positive, got {max_tokens}")
        self.dimension = dimension
        self.max_tokens = max_tokens

    @property
    def model(self) -> str:
        return "hashing-v1"

    @property
    def model_version(self) -> str:
        return HASHING_MODEL_VERSION

    def embed_text(self, text: str) -> np.ndarray:
        """Embed one document; empty input yields the zero vector."""
        tokens = tokenize(text)[: self.max_tokens]
        vector = np.zeros(self.dimension, dtype=np.float32)
        if not tokens:
            return vector

        for feature, count in _ngrams(tokens).items():
            index, sign = _hash_feature(feature, self.dimension)
            vector[index] += sign * count

        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector /= norm
        return vector.astype(np.float32, copy=False)

    def embed_texts(self, texts: list[str], *, batch_size: int = 64) -> list[np.ndarray]:
        """Embed texts in batches to bound peak memory on large corpora."""
        if batch_size <= 0:
            raise EmbeddingError(f"batch size must be positive, got {batch_size}")
        vectors: list[np.ndarray] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            vectors.extend(self.embed_text(text) for text in batch)
        logger.debug(
            "embedded text batch",
            extra={"count": len(texts), "dimension": self.dimension},
        )
        return vectors


def get_embedder(settings: Settings | None = None) -> HashingEmbedder:
    """Return the configured embedder, refusing unimplemented providers."""
    settings = settings or get_settings()
    provider = settings.embeddings.provider
    if provider != "hashing":
        raise EmbeddingError(
            f"embedding provider {provider!r} is configured but not implemented; "
            "install its optional dependency and implement its backend before use"
        )
    return HashingEmbedder(settings.embeddings.dimension, max_tokens=settings.embeddings.max_tokens)


def embed_texts(
    texts: list[str], settings: Settings | None = None, *, batch_size: int | None = None
) -> list[np.ndarray]:
    """Embed texts with the configured backend and batch size."""
    settings = settings or get_settings()
    embedder = get_embedder(settings)
    return embedder.embed_texts(texts, batch_size=batch_size or settings.embeddings.batch_size)
