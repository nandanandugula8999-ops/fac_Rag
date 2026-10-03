"""Stage 13 tests: windowed trend directions and small-number gates."""

from __future__ import annotations

import pytest

from faculty_radar.linking.builder import link_faculty
from faculty_radar.linking.consent import ConsentEntry, ConsentRegistry
from faculty_radar.models import NormalizedWork, Provenance, Status, Topic
from faculty_radar.normalization.authors import normalize_authors
from faculty_radar.normalization.works import normalize_works
from faculty_radar.resolution.resolver import resolve_researchers
from faculty_radar.trends.engine import TrendEngine, analyze_trends
from tests.fake_openalex import AUTHORS, WORKS

WEI = "A100000001"
LUIS = "A100000004"
PRIYA = "A100000003"
SOUTHPORT = "A100000002"


@pytest.fixture
def pipeline(engine_settings):
    authors = normalize_authors(AUTHORS)
    works = normalize_works(WORKS)
    resolved = resolve_researchers(authors, works, engine_settings, store=False)
    consent = ConsentRegistry(
        {rid: ConsentEntry(rid, consented=True) for rid in (WEI, LUIS, PRIYA, SOUTHPORT)},
        enforce=True,
    )
    profiles = link_faculty(
        resolved.researchers, authors, works, engine_settings, consent=consent, store=False
    )
    return {"profiles": profiles, "works": works}


def _settings(engine_settings, **updates):
    trends = engine_settings.trends.model_copy(update=updates)
    return engine_settings.model_copy(update={"trends": trends})


class TestTrendDirections:
    def test_rising_topic(self, pipeline, engine_settings):
        report = TrendEngine(pipeline["works"], pipeline["profiles"], engine_settings).analyze()
        gnn = next(t for t in report.topics if t.topic == "Graph Neural Networks")

        assert report.status is Status.OK
        assert gnn.direction == "rising"
        assert gnn.total_publications == 3
        assert gnn.recent_publications == 2
        assert gnn.baseline_publications == 1
        assert gnn.growth_ratio == pytest.approx(5.0)
        assert gnn.first_year == 2023
        assert gnn.last_year == 2025
        assert set(gnn.faculty_ids) == {WEI, LUIS}
        assert gnn.counts_by_year == {"2023": 1, "2024": 1, "2025": 1}

    def test_declining_topic(self, pipeline, engine_settings):
        settings = _settings(engine_settings, min_publications=1)
        report = TrendEngine(pipeline["works"], pipeline["profiles"], settings).analyze()
        protein = next(t for t in report.topics if t.topic == "Protein Folding")

        assert protein.direction == "declining"
        assert protein.growth_ratio == pytest.approx(0.0)
        assert protein.faculty_ids == [PRIYA]

    def test_small_topics_gated_out_by_default(self, pipeline, engine_settings):
        report = TrendEngine(pipeline["works"], pipeline["profiles"], engine_settings).analyze()

        assert {t.topic for t in report.topics} == {"Graph Neural Networks"}

    def test_emerging_topic(self, engine_settings):
        works = [
            NormalizedWork(
                openalex_id=f"WN{i}",
                title=f"Novel method {i}",
                year=2025,
                topics=[Topic(id="T999", name="Neuromorphic Photonics")],
                provenance=Provenance(source="openalex", source_id=f"WN{i}"),
            )
            for i in range(2)
        ]

        report = analyze_trends(works, [], engine_settings)
        topic = next(t for t in report.topics if t.topic == "Neuromorphic Photonics")

        assert topic.direction == "emerging"
        assert topic.baseline_publications == 0
        assert topic.faculty_ids == []

    def test_keywords_get_same_treatment(self, pipeline, engine_settings):
        report = TrendEngine(pipeline["works"], pipeline["profiles"], engine_settings).analyze()

        assert report.keywords
        assert all(
            t.direction in ("rising", "declining", "stable", "emerging") for t in report.keywords
        )

    def test_year_counts_cover_dated_works(self, pipeline, engine_settings):
        report = TrendEngine(pipeline["works"], pipeline["profiles"], engine_settings).analyze()

        assert report.year_counts == {
            "2021": 1,
            "2022": 1,
            "2023": 1,
            "2024": 1,
            "2025": 1,
        }

    def test_undated_works_excluded_with_note(self, pipeline, engine_settings):
        works = [
            NormalizedWork(
                openalex_id="WU",
                title="Undated work",
                year=None,
                topics=[Topic(id="T100", name="Graph Neural Networks")],
                provenance=Provenance(source="openalex", source_id="WU"),
            ),
            *pipeline["works"],
        ]
        report = TrendEngine(works, pipeline["profiles"], engine_settings).analyze()
        gnn = next(t for t in report.topics if t.topic == "Graph Neural Networks")

        assert gnn.total_publications == 3
        assert any("undated" in note for note in report.notes)

    def test_no_dated_works_is_insufficient(self, engine_settings):
        report = analyze_trends([], [], engine_settings)

        assert report.status is Status.INSUFFICIENT_EVIDENCE
        assert report.topics == []

    def test_analysis_is_deterministic(self, pipeline, engine_settings):
        first = TrendEngine(pipeline["works"], pipeline["profiles"], engine_settings).analyze()
        second = TrendEngine(pipeline["works"], pipeline["profiles"], engine_settings).analyze()

        assert [(t.topic, t.direction) for t in first.topics] == [
            (t.topic, t.direction) for t in second.topics
        ]
