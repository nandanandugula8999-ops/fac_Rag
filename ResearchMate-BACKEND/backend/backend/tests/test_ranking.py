"""Stage 10 tests: field-weighted reranking and evidence spans."""

from __future__ import annotations

import pytest

from faculty_radar.corpus.builder import build_corpus
from faculty_radar.linking.builder import link_faculty
from faculty_radar.linking.consent import ConsentEntry, ConsentRegistry
from faculty_radar.models import RetrievalHit
from faculty_radar.normalization.authors import normalize_authors
from faculty_radar.normalization.works import normalize_works
from faculty_radar.ranking.rerank import rerank_hits
from faculty_radar.resolution.resolver import resolve_researchers
from faculty_radar.retrieval.hybrid import HybridRetriever
from tests.fake_openalex import AUTHORS, WORKS

WEI = "A100000001"
QUERY = "molecular property prediction"


@pytest.fixture
def candidates(engine_settings):
    authors = normalize_authors(AUTHORS)
    works = normalize_works(WORKS)
    resolved = resolve_researchers(authors, works, engine_settings, store=False)
    consent = ConsentRegistry({WEI: ConsentEntry(WEI, consented=True)}, enforce=True)
    profiles = link_faculty(
        resolved.researchers, authors, works, engine_settings, consent=consent, store=False
    )
    documents = build_corpus(profiles, works, engine_settings, store=False)
    retriever = HybridRetriever(documents, engine_settings)
    return retriever.search(QUERY, top_k=10)


class TestFieldWeightedRerank:
    def test_title_match_outranks_passing_mention(self, candidates, engine_settings):
        result = rerank_hits(candidates, QUERY, engine_settings, method="weighted")

        assert result.hits[0].document.work_id == "W1001"
        assert result.hits[0].rerank_score > result.hits[1].rerank_score
        assert "title" in result.hits[0].matched_fields
        assert set(result.hits[0].matched_terms) >= {"molecular", "property", "prediction"}

    def test_original_score_preserved_and_rerank_recorded(self, candidates, engine_settings):
        original = {hit.doc_id: hit.score for hit in candidates}
        result = rerank_hits(candidates, QUERY, engine_settings, method="weighted")

        assert [hit.rank for hit in result.hits] == list(range(1, len(result.hits) + 1))
        for hit in result.hits:
            assert hit.score == original[hit.doc_id]
            assert hit.rerank_score is not None
            assert hit.signals[-1] == "rerank:weighted"

    def test_evidence_span_is_verbatim_document_text(self, candidates, engine_settings):
        result = rerank_hits(candidates, QUERY, engine_settings, method="weighted")
        top = result.hits[0]

        span = result.evidence_spans[top.doc_id]
        assert span
        assert span in top.document.text
        assert "Molecular Property Prediction" in span

    def test_rrf_keeps_hybrid_signal_competitive(self, candidates, engine_settings):
        result = rerank_hits(candidates, QUERY, engine_settings, method="rrf")

        assert result.method == "rrf"
        assert result.hits[0].document.work_id == "W1001"
        assert all(hit.signals[-1] == "rerank:rrf" for hit in result.hits)
        assert all(hit.rerank_score is not None for hit in result.hits)

    def test_top_k_limits_reranked_hits(self, candidates, engine_settings):
        result = rerank_hits(candidates, QUERY, engine_settings, method="weighted", top_k=1)

        assert len(result.hits) == 1
        assert result.hits[0].rank == 1

    def test_missing_document_scores_zero_without_span(self, engine_settings):
        hits = [RetrievalHit(doc_id="missing", score=0.5)]
        result = rerank_hits(hits, QUERY, engine_settings, method="weighted")

        assert result.hits[0].rerank_score == 0.0
        assert result.evidence_spans == {"missing": ""}

    def test_empty_inputs_and_methods(self, candidates, engine_settings):
        assert rerank_hits([], QUERY, engine_settings).hits == ()
        assert rerank_hits(candidates, "   ", engine_settings).hits == ()
        assert rerank_hits(candidates, QUERY, engine_settings, top_k=0).hits == ()
        with pytest.raises(ValueError, match="unknown rerank method"):
            rerank_hits(candidates, QUERY, engine_settings, method="mystery")
