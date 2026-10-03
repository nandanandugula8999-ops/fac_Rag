"""Stage 7 tests: deterministic hashing vectors and model-pinned storage."""

from __future__ import annotations

import json

import numpy as np
import pytest
from numpy.testing import assert_allclose

import faculty_radar.embeddings.pipeline as embedding_pipeline
from faculty_radar.corpus.builder import build_corpus
from faculty_radar.embeddings.backends import (
    EmbeddingError,
    HashingEmbedder,
    embed_texts,
    get_embedder,
    text_hash,
)
from faculty_radar.embeddings.pipeline import build_embeddings
from faculty_radar.embeddings.store import VectorIndexError, VectorStore
from faculty_radar.linking.builder import link_faculty
from faculty_radar.linking.consent import ConsentEntry, ConsentRegistry
from faculty_radar.normalization.authors import normalize_authors
from faculty_radar.normalization.works import normalize_works
from faculty_radar.paths import build_paths
from faculty_radar.resolution.resolver import resolve_researchers
from tests.fake_openalex import AUTHORS, WORKS

WEI = "A100000001"


@pytest.fixture
def documents(engine_settings):
    authors = normalize_authors(AUTHORS)
    works = normalize_works(WORKS)
    resolved = resolve_researchers(authors, works, engine_settings, store=False)
    consent = ConsentRegistry({WEI: ConsentEntry(WEI, consented=True)}, enforce=True)
    profiles = link_faculty(
        resolved.researchers, authors, works, engine_settings, consent=consent, store=False
    )
    return build_corpus(profiles, works, engine_settings, store=False)


def _bad_settings(settings, **updates):
    embeddings = settings.embeddings.model_copy(update=updates)
    return settings.model_copy(update={"embeddings": embeddings})


# --------------------------------------------------------------------------
# Hashing backend
# --------------------------------------------------------------------------


class TestHashingBackend:
    def test_vectors_have_configured_dimension_and_unit_length(self, documents, engine_settings):
        result = build_embeddings(documents, engine_settings, store=False)

        assert result.stats["dimension"] == 256
        assert result.stats["embedding_model"] == "hashing-v1"
        assert len(result.vectors) == len(documents) == 4
        for vector in result.vectors:
            assert vector.shape == (256,)
            assert_allclose(float(np.linalg.norm(vector)), 1.0)

    def test_same_text_always_produces_same_vector(self, documents, engine_settings):
        first = build_embeddings(documents, engine_settings, store=False)
        second = build_embeddings(documents, engine_settings, store=False)

        for old, new in zip(first.vectors, second.vectors, strict=True):
            assert_allclose(old, new)

    def test_changed_text_changes_vector(self, documents):
        altered = documents[0].model_copy(update={"text": documents[0].text + " extra"})
        first = HashingEmbedder(64).embed_text(documents[0].embed_text)
        second = HashingEmbedder(64).embed_text(altered.embed_text)

        assert not np.allclose(first, second)
        assert text_hash(documents[0].embed_text) != text_hash(altered.embed_text)

    def test_batching_does_not_change_vectors(self, documents):
        texts = [doc.embed_text for doc in documents]
        embedder = HashingEmbedder(64)

        assert_allclose(
            np.stack(embedder.embed_texts(texts, batch_size=1)),
            np.stack(embedder.embed_texts(texts, batch_size=len(texts))),
        )

    def test_empty_text_produces_zero_vector(self):
        vector = HashingEmbedder(32).embed_text("")

        assert vector.shape == (32,)
        assert not np.any(vector)

    def test_invalid_configuration_fails_fast(self):
        with pytest.raises(EmbeddingError, match="positive"):
            HashingEmbedder(0)
        with pytest.raises(EmbeddingError, match="positive"):
            HashingEmbedder(32, max_tokens=0)
        with pytest.raises(EmbeddingError, match="positive"):
            HashingEmbedder(32).embed_texts(["text"], batch_size=0)

    def test_unimplemented_provider_is_explicit(self, engine_settings):
        settings = _bad_settings(engine_settings, provider="openai")

        with pytest.raises(EmbeddingError, match="not implemented"):
            get_embedder(settings)
        with pytest.raises(EmbeddingError, match="not implemented"):
            embed_texts(["text"], settings)


# --------------------------------------------------------------------------
# Vector index behaviour
# --------------------------------------------------------------------------


class TestVectorIndex:
    def test_exact_vector_retrieves_itself_first(self, documents, engine_settings):
        result = build_embeddings(documents, engine_settings, store=False)
        hits = result.index.search(result.vectors[0], top_k=3)

        assert next(hit.doc_id for hit in hits) == documents[0].doc_id
        assert hits[0].score == pytest.approx(1.0)
        assert len(hits) == 3

    def test_empty_query_has_no_meaningful_matches(self, documents, engine_settings):
        result = build_embeddings(documents, engine_settings, store=False)

        assert result.index.search(np.zeros(256, dtype=np.float32)) == []
        assert result.index.search(result.vectors[0], top_k=0) == []

    def test_wrong_query_dimension_is_rejected(self, documents, engine_settings):
        result = build_embeddings(documents, engine_settings, store=False)

        with pytest.raises(VectorIndexError, match="dimension"):
            result.index.search(np.zeros(8, dtype=np.float32))

    def test_missing_document_lookup_is_explicit(self, documents, engine_settings):
        result = build_embeddings(documents, engine_settings, store=False)

        with pytest.raises(VectorIndexError, match="not in the vector index"):
            result.index.vector_for("missing")

    def test_changed_text_marks_index_stale(self, documents, engine_settings):
        result = build_embeddings(documents, engine_settings, store=False)
        altered = documents[0].model_copy(update={"text": documents[0].text + " extra"})

        assert result.index.needs_rebuild([altered, *documents[1:]]) is True
        assert result.index.needs_rebuild(documents) is False


# --------------------------------------------------------------------------
# Persistence and cache reuse
# --------------------------------------------------------------------------


class TestVectorPersistence:
    def test_roundtrip_preserves_vectors_and_metadata(self, documents, engine_settings):
        paths = build_paths(engine_settings)
        result = build_embeddings(documents, engine_settings, paths, store=True)
        index_path, metadata_path = VectorStore(paths).index_paths("hashing-v1")

        assert result.path == index_path
        assert index_path.exists()
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert metadata["embedding_model"] == "hashing-v1"
        assert metadata["embedding_version"] == "1"
        assert metadata["dimension"] == 256
        assert metadata["document_count"] == len(documents)

        loaded = VectorStore(paths).load_index("hashing-v1", "1")
        loaded.ensure_compatible(embedding_model="hashing-v1", embedding_version="1", dimension=256)
        assert loaded.doc_ids == result.index.doc_ids
        assert_allclose(loaded.vectors, result.index.vectors)

    def test_incompatible_representation_is_refused(self, documents, engine_settings):
        paths = build_paths(engine_settings)
        result = build_embeddings(documents, engine_settings, paths, store=True)

        with pytest.raises(VectorIndexError, match="model"):
            result.index.ensure_compatible(
                embedding_model="other-model", embedding_version="1", dimension=256
            )
        with pytest.raises(VectorIndexError, match="version"):
            result.index.ensure_compatible(
                embedding_model="hashing-v1", embedding_version="2", dimension=256
            )
        with pytest.raises(VectorIndexError, match="dimension"):
            result.index.ensure_compatible(
                embedding_model="hashing-v1", embedding_version="1", dimension=128
            )

    def test_missing_index_is_explicitly_absent(self, engine_settings):
        loaded = VectorStore(build_paths(engine_settings)).load_index("absent-model", "1")

        assert loaded.exists is False
        assert loaded.search(np.ones(8, dtype=np.float32)) == []

    def test_invalid_writes_are_rejected(self, documents, engine_settings):
        store = VectorStore(build_paths(engine_settings))

        with pytest.raises(VectorIndexError, match="empty"):
            store.write_index([], [], embedding_model="hashing-v1", embedding_version="1")
        with pytest.raises(VectorIndexError, match="misalign"):
            store.write_index(
                documents,
                [np.zeros(256, dtype=np.float32)],
                embedding_model="hashing-v1",
                embedding_version="1",
            )
        with pytest.raises(VectorIndexError, match="duplicate"):
            store.write_index(
                [documents[0], documents[0]],
                [np.zeros(256, dtype=np.float32)] * 2,
                embedding_model="hashing-v1",
                embedding_version="1",
            )

    def test_unchanged_documents_reuse_cached_vectors(
        self, documents, engine_settings, monkeypatch
    ):
        paths = build_paths(engine_settings)
        first = build_embeddings(documents, engine_settings, paths, store=True)

        calls = []
        real_embed_texts = embedding_pipeline.embed_texts

        def counting_embed_texts(texts, settings=None, **kwargs):
            calls.append(list(texts))
            return real_embed_texts(texts, settings, **kwargs)

        monkeypatch.setattr(embedding_pipeline, "embed_texts", counting_embed_texts)
        second = build_embeddings(documents, engine_settings, paths, store=True)

        assert calls == []
        assert second.stats["computed"] == 0
        assert second.stats["reused"] == len(documents)
        assert second.stats["documents"] == first.stats["documents"]
        assert_allclose(np.stack(second.vectors), np.stack(first.vectors))

    def test_changed_document_is_recomputed_selectively(
        self, documents, engine_settings, monkeypatch
    ):
        paths = build_paths(engine_settings)
        build_embeddings(documents, engine_settings, paths, store=True)
        altered = documents[0].model_copy(update={"text": documents[0].text + " extra"})

        calls = []
        real_embed_texts = embedding_pipeline.embed_texts

        def counting_embed_texts(texts, settings=None, **kwargs):
            calls.append(list(texts))
            return real_embed_texts(texts, settings, **kwargs)

        monkeypatch.setattr(embedding_pipeline, "embed_texts", counting_embed_texts)
        result = build_embeddings([altered, *documents[1:]], engine_settings, paths, store=True)

        assert calls == [[altered.embed_text]]
        assert result.stats["computed"] == 1
        assert result.stats["reused"] == len(documents) - 1
