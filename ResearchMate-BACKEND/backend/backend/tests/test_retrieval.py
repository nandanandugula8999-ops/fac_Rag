"""Stage 8 tests: literal BM25 retrieval, filters, and hit provenance."""

from __future__ import annotations

import pytest

from faculty_radar.corpus.builder import build_corpus
from faculty_radar.linking.builder import link_faculty
from faculty_radar.linking.consent import ConsentEntry, ConsentRegistry
from faculty_radar.models import DocumentType
from faculty_radar.normalization.authors import normalize_authors
from faculty_radar.normalization.works import normalize_works
from faculty_radar.resolution.resolver import resolve_researchers
from faculty_radar.retrieval.bm25 import BM25Index, KeywordRetriever, keyword_search
from faculty_radar.retrieval.filters import SearchFilters, apply_filters
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
def retriever(documents, engine_settings):
    return KeywordRetriever(documents, engine_settings)


# --------------------------------------------------------------------------
# Lexical matching
# --------------------------------------------------------------------------


class TestKeywordRetrieval:
    def test_exact_technical_phrase_finds_tagged_publications(self, retriever):
        hits = retriever.search("graph neural networks")

        assert [hit.document.work_id for hit in hits] == ["W1005", "W1001", "W1002"]
        assert all(hit.document.document_type is DocumentType.PUBLICATION for hit in hits)

    def test_rare_term_is_discriminating(self, retriever):
        hits = retriever.search("cluster based batching")

        assert [hit.document.work_id for hit in hits] == ["W1002"]
        assert "batching" in hits[0].matched_terms
        assert hits[0].matched_fields == ["text"]

    def test_repeated_query_terms_scale_linearly(self, retriever):
        single = retriever.search("batching")[0].lexical_score
        double = retriever.search("batching batching")[0].lexical_score

        assert double == pytest.approx(2 * single)

    def test_stopword_only_and_empty_queries_match_nothing(self, retriever):
        assert retriever.search("the and of") == []
        assert retriever.search("   ") == []
        assert retriever.search("", top_k=5) == []

    def test_empty_corpus_matches_nothing(self, engine_settings):
        assert KeywordRetriever([], engine_settings).search("graph neural networks") == []

    def test_top_k_and_rank_are_explicit(self, retriever):
        hits = retriever.search("graph neural networks", top_k=2)

        assert [hit.rank for hit in hits] == [1, 2]
        assert retriever.search("graph neural networks", top_k=0) == []
        assert retriever.search("graph neural networks", top_k=-3) == []

    def test_hits_carry_lexical_provenance(self, retriever):
        hit = retriever.search("graph neural networks")[0]

        assert hit.signals == ["bm25"]
        assert hit.semantic_score == 0.0
        assert hit.lexical_score == hit.score > 0
        assert hit.document is not None
        assert hit.document.doc_id == hit.doc_id
        assert set(hit.matched_terms) >= {"graph", "neural", "networks"}
        assert set(hit.matched_fields) >= {"topics", "text"}

    def test_search_is_deterministic(self, retriever):
        first = [hit.doc_id for hit in retriever.search("graph neural networks")]
        second = [hit.doc_id for hit in retriever.search("graph neural networks")]

        assert first == second

    def test_convenience_entry_point_matches_retriever(self, documents, retriever, engine_settings):
        assert [hit.doc_id for hit in keyword_search(documents, "batching", engine_settings)] == [
            hit.doc_id for hit in retriever.search("batching")
        ]


# --------------------------------------------------------------------------
# Filters
# --------------------------------------------------------------------------


class TestRetrievalFilters:
    def test_faculty_filter(self, retriever):
        assert retriever.search("graph neural networks", filters=SearchFilters(faculty_ids=(WEI,)))
        assert (
            retriever.search("graph neural networks", filters=SearchFilters(faculty_ids=("A999",)))
            == []
        )

    def test_document_type_filter(self, retriever):
        hits = retriever.search(
            "Wei Zhang", filters=SearchFilters(document_types=(DocumentType.FACULTY_PROFILE,))
        )

        assert [hit.document.work_id for hit in hits] == [None]
        assert all(hit.document.document_type is DocumentType.FACULTY_PROFILE for hit in hits)

    def test_year_range_filter(self, retriever):
        hits = retriever.search(
            "graph neural networks", filters=SearchFilters(year_min=2024, year_max=2024)
        )

        assert [hit.document.work_id for hit in hits] == ["W1002"]

    def test_institution_and_stated_filters(self, retriever):
        assert (
            retriever.search(
                "graph neural networks",
                filters=SearchFilters(institution_ids=("I999",)),
            )
            == []
        )
        assert (
            retriever.search("graph neural networks", filters=SearchFilters(stated_only=True)) == []
        )

    def test_filters_preserve_input_order(self, documents):
        assert apply_filters(documents, None) == documents
        assert apply_filters(documents, SearchFilters()) == documents

    def test_empty_index_scores_nothing(self, engine_settings):
        assert BM25Index.build([]).average_length == 0.0
