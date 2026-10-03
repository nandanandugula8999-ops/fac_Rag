"""Stage 9 tests: vector candidates and reciprocal-rank hybrid fusion."""

from __future__ import annotations

import numpy as np
import pytest

from faculty_radar.corpus.builder import build_corpus
from faculty_radar.embeddings.store import VectorIndex
from faculty_radar.linking.builder import link_faculty
from faculty_radar.linking.consent import ConsentEntry, ConsentRegistry
from faculty_radar.models import DocumentType, RetrievalHit
from faculty_radar.normalization.authors import normalize_authors
from faculty_radar.normalization.works import normalize_works
from faculty_radar.resolution.resolver import resolve_researchers
from faculty_radar.retrieval.filters import SearchFilters
from faculty_radar.retrieval.hybrid import HybridRetriever, fuse_rankings
from faculty_radar.retrieval.semantic import SemanticRetriever
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


@pytest.fixture
def hybrid(documents, engine_settings):
    return HybridRetriever(documents, engine_settings)


def _hit(doc_id, rank):
    return RetrievalHit(doc_id=doc_id, score=1.0 / rank, rank=rank)


# --------------------------------------------------------------------------
# Vector-space retrieval
# --------------------------------------------------------------------------


class TestSemanticRetrieval:
    def test_vector_search_returns_scored_documents(self, documents, engine_settings):
        retriever = SemanticRetriever(documents, engine_settings)
        hits = retriever.search("graph neural networks", top_k=3)

        assert len(hits) == 3
        assert all(hit.signals == ["vector"] for hit in hits)
        assert all(hit.lexical_score == 0.0 for hit in hits)
        assert all(hit.semantic_score == hit.score > 0 for hit in hits)
        assert all(hit.document is not None for hit in hits)
        assert [hit.rank for hit in hits] == [1, 2, 3]

    def test_empty_query_and_limit_match_nothing(self, documents, engine_settings):
        retriever = SemanticRetriever(documents, engine_settings)

        assert retriever.search("   ") == []
        assert retriever.search("graph neural networks", top_k=0) == []

    def test_injected_index_must_cover_the_corpus(self, documents, engine_settings):
        partial = VectorIndex(
            doc_ids=(documents[0].doc_id,),
            vectors=np.zeros((1, 256), dtype=np.float32),
            embedding_model="hashing-v1",
            embedding_version="1",
            text_hashes={documents[0].doc_id: "hash"},
        )

        with pytest.raises(ValueError, match="missing"):
            SemanticRetriever(documents, engine_settings, index=partial)


# --------------------------------------------------------------------------
# Hybrid fusion
# --------------------------------------------------------------------------


class TestHybridRetrieval:
    def test_hybrid_returns_union_with_both_signals(self, hybrid):
        hits = hybrid.search("graph neural networks", top_k=3)

        assert {hit.document.work_id for hit in hits} == {"W1001", "W1002", "W1005"}
        assert all(hit.signals == ["bm25", "vector"] for hit in hits)
        assert all(hit.lexical_score > 0 and hit.semantic_score > 0 for hit in hits)

    def test_vector_only_query_still_retrieves(self, hybrid):
        hits = hybrid.search("xylophone quantum zephyr", top_k=2)

        assert len(hits) == 2
        assert all(hit.signals == ["vector"] for hit in hits)
        assert all(hit.lexical_score == 0.0 for hit in hits)

    def test_fused_hits_preserve_component_scores(self, hybrid):
        lexical = {
            hit.document.work_id: hit
            for hit in hybrid.keyword.search("graph neural networks", top_k=10)
        }
        semantic = {
            hit.document.work_id: hit
            for hit in hybrid.semantic.search("graph neural networks", top_k=10)
        }
        fused = {hit.document.work_id: hit for hit in hybrid.search("graph neural networks")}

        assert fused["W1002"].lexical_score == lexical["W1002"].lexical_score
        assert fused["W1002"].semantic_score == semantic["W1002"].semantic_score
        assert set(fused["W1002"].matched_terms) >= set(lexical["W1002"].matched_terms)

    def test_reciprocal_rank_fusion_rewards_coverage(self):
        fused = fuse_rankings(
            [[_hit("only-lexical", 1), _hit("both", 2)], [_hit("both", 2)]],
            rrf_k=60,
        )

        # "both" ranks worse twice but appears twice; coverage beats one top rank.
        assert fused["both"] > fused["only-lexical"]
        assert fused["both"] == pytest.approx(1 / 62 + 1 / 61)

    def test_invalid_rrf_constant_is_rejected(self):
        with pytest.raises(ValueError, match="positive"):
            fuse_rankings([[_hit("doc", 1)]], rrf_k=0)

    def test_filters_apply_to_both_retrievers(self, hybrid):
        assert (
            hybrid.search(
                "graph neural networks",
                filters=SearchFilters(faculty_ids=("A999",)),
            )
            == []
        )
        hits = hybrid.search(
            "graph neural networks",
            filters=SearchFilters(document_types=(DocumentType.PUBLICATION,)),
        )
        assert {hit.document.work_id for hit in hits} == {"W1001", "W1002", "W1005"}

    def test_empty_and_nonpositive_requests(self, hybrid):
        assert hybrid.search("   ") == []
        assert hybrid.search("graph neural networks", top_k=0) == []

    def test_hybrid_search_is_deterministic(self, hybrid):
        first = [hit.doc_id for hit in hybrid.search("graph neural networks")]
        second = [hit.doc_id for hit in hybrid.search("graph neural networks")]

        assert first == second
