"""Stage 11 tests: expertise typing, signals, and evidence requirements."""

from __future__ import annotations

import pytest

from faculty_radar.corpus.builder import build_corpus
from faculty_radar.expertise.engine import ExpertiseEngine, find_experts
from faculty_radar.linking.builder import link_faculty
from faculty_radar.linking.consent import ConsentEntry, ConsentRegistry
from faculty_radar.models import ExpertiseType, Status
from faculty_radar.normalization.authors import normalize_authors
from faculty_radar.normalization.works import normalize_works
from faculty_radar.resolution.resolver import resolve_researchers
from tests.fake_openalex import AUTHORS, WORKS

WEI = "A100000001"
LUIS = "A100000004"
PRIYA = "A100000003"
SOUTHPORT = "A100000002"
STATED_TOPIC = "Molecular Property Prediction"
STATED_PROJECT = "Explain which molecular structures cause a predicted property."


@pytest.fixture
def pipeline(engine_settings):
    authors = normalize_authors(AUTHORS)
    works = normalize_works(WORKS)
    resolved = resolve_researchers(authors, works, engine_settings, store=False)
    consent = ConsentRegistry(
        {
            rid: ConsentEntry(
                rid,
                consented=True,
                stated_topics=[STATED_TOPIC] if rid == WEI else [],
                stated_project_descriptions=[STATED_PROJECT] if rid == WEI else [],
            )
            for rid in (WEI, LUIS, PRIYA, SOUTHPORT)
        },
        enforce=True,
    )
    profiles = link_faculty(
        resolved.researchers, authors, works, engine_settings, consent=consent, store=False
    )
    documents = build_corpus(profiles, works, engine_settings, store=False)
    return {
        "profiles": profiles,
        "works": works,
        "documents": documents,
        "engine": ExpertiseEngine(profiles, works, documents, engine_settings),
    }


class TestExpertiseSearch:
    def test_stated_and_evidence_signals_stay_separate(self, pipeline):
        report = pipeline["engine"].find_experts("molecular property prediction")

        assert report.status is Status.OK
        top = report.top
        assert top.faculty_id == WEI
        assert top.expertise_type is ExpertiseType.STATED
        assert top.stated_score > 0
        assert top.evidence_score > 0
        assert 0.0 <= top.score <= 1.0
        assert top.evidence, "an expertise claim must carry passages"
        assert top.supporting_publications
        # The stated topic matches the query lexically; the publication topic
        # "Graph Neural Networks" does not, so it must not appear here.
        assert set(top.matched_topics) == {"Molecular Property Prediction"}

    def test_coauthor_gets_evidence_not_stated(self, pipeline):
        report = pipeline["engine"].find_experts("molecular property prediction")
        luis = next(m for m in report.matches if m.faculty_id == LUIS)

        assert luis.expertise_type is ExpertiseType.EVIDENCE_BASED
        assert luis.stated_score == 0.0
        assert luis.evidence_score > 0

    def test_publication_evidence_is_citable(self, pipeline):
        report = pipeline["engine"].find_experts("protein folding dynamics")
        top = report.top

        assert top.faculty_id == PRIYA
        assert top.expertise_type is ExpertiseType.EVIDENCE_BASED
        first = top.evidence[0]
        assert first.quote
        assert first.work_id == "W1003"
        assert first.doi == "10.1000/fold1"
        assert first.source_url == "https://doi.org/10.1000/fold1"
        assert first.expertise_type is ExpertiseType.EVIDENCE_BASED
        assert 0.0 <= first.relevance <= 1.0

    def test_no_evidence_means_insufficient_evidence(self, pipeline):
        report = pipeline["engine"].find_experts("xylophone concerto")

        assert report.status is Status.INSUFFICIENT_EVIDENCE
        assert report.matches == []

    def test_empty_query_is_insufficient(self, pipeline):
        report = pipeline["engine"].find_experts("   ")

        assert report.status is Status.INSUFFICIENT_EVIDENCE

    def test_min_publications_gate_blocks_thin_evidence(self, pipeline, engine_settings):
        settings = engine_settings.model_copy(deep=True)
        settings.expertise.min_publications_for_evidence = 2
        engine = ExpertiseEngine(
            pipeline["profiles"], pipeline["works"], pipeline["documents"], settings
        )

        report = engine.find_experts("protein folding dynamics")

        # Priya has exactly one supporting work. With the gate at two, her
        # evidence signals zero out, nothing else supports her, and the query
        # correctly degrades to insufficient_evidence rather than a thin claim.
        assert report.status is Status.INSUFFICIENT_EVIDENCE
        assert report.matches == []

    def test_min_score_filters_weak_matches(self, pipeline, engine_settings):
        settings = engine_settings.model_copy(deep=True)
        settings.expertise.min_score = 0.99
        engine = ExpertiseEngine(
            pipeline["profiles"], pipeline["works"], pipeline["documents"], settings
        )

        report = engine.find_experts("molecular property prediction")

        assert report.status is Status.INSUFFICIENT_EVIDENCE

    def test_signals_are_named_and_weighted(self, pipeline):
        report = pipeline["engine"].find_experts("molecular property prediction")
        names = {signal.name for signal in report.top.signals}

        assert {"explicit_topic", "topic_evidence", "semantic"} <= names
        for signal in report.top.signals:
            assert 0.0 <= signal.value <= 1.0
            assert signal.weight > 0
            assert signal.explanation

    def test_top_k_and_determinism(self, pipeline):
        first = pipeline["engine"].find_experts("graph neural networks", top_k=1)
        second = pipeline["engine"].find_experts("graph neural networks", top_k=1)

        assert len(first.matches) == 1
        assert [m.faculty_id for m in first.matches] == [m.faculty_id for m in second.matches]

    def test_convenience_entry_point(self, pipeline, engine_settings):
        report = find_experts(
            "protein folding dynamics",
            pipeline["profiles"],
            pipeline["works"],
            pipeline["documents"],
            engine_settings,
        )

        assert report.top.faculty_id == PRIYA

    def test_explanation_is_human_readable(self, pipeline):
        report = pipeline["engine"].find_experts("molecular property prediction")

        assert "Wei Zhang" in report.explain()
        assert "stated=" in report.explain()
