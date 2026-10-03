"""Stage 12 tests: existing vs potential collaboration evidence grading."""

from __future__ import annotations

import pytest

from faculty_radar.collaboration.engine import CollaborationEngine, find_collaborations
from faculty_radar.graph.builder import build_graph
from faculty_radar.graph.queries import GraphQueries
from faculty_radar.linking.builder import link_faculty
from faculty_radar.linking.consent import ConsentEntry, ConsentRegistry
from faculty_radar.models import (
    Affiliation,
    Authorship,
    CollaborationType,
    FacultyProfile,
    Institution,
    LinkedPublication,
    NormalizedWork,
    Provenance,
    Status,
    Topic,
)
from faculty_radar.normalization.authors import normalize_authors
from faculty_radar.normalization.works import normalize_works
from faculty_radar.resolution.resolver import resolve_researchers
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
    graph = build_graph(profiles, works, engine_settings, store=False)
    return {
        "profiles": profiles,
        "works": works,
        "engine": CollaborationEngine(profiles, works, GraphQueries(graph), engine_settings),
    }


def _synthetic_pair():
    """Two researchers sharing a topic but no works: a potential collaboration."""
    provenance = Provenance(source="openalex", source_id="synthetic")
    shared = Topic(id="T900", name="Quantum Dots")
    affiliation = Affiliation(
        institution=Institution(id="I900", name="Sample University"), is_primary=True
    )
    works = [
        NormalizedWork(
            openalex_id="WS1",
            title="Quantum dot synthesis",
            year=2024,
            authorships=[Authorship(raw_author_id="S1", affiliation=affiliation)],
            topics=[shared, Topic(id="T901", name="Nanochemistry")],
            provenance=Provenance(source="openalex", source_id="WS1"),
        ),
        NormalizedWork(
            openalex_id="WS2",
            title="Quantum dot displays",
            year=2024,
            authorships=[Authorship(raw_author_id="S2", affiliation=affiliation)],
            topics=[shared, Topic(id="T902", name="Optoelectronics")],
            provenance=Provenance(source="openalex", source_id="WS2"),
        ),
    ]
    profiles = [
        FacultyProfile(
            faculty_id="S1",
            name="Ada Sample",
            researcher_id="S1",
            publications=[
                LinkedPublication(
                    work_id="WS1",
                    faculty_id="S1",
                    link_method="openalex_authorship",
                    link_confidence=1.0,
                )
            ],
            provenance=provenance,
        ),
        FacultyProfile(
            faculty_id="S2",
            name="Bob Sample",
            researcher_id="S2",
            publications=[
                LinkedPublication(
                    work_id="WS2",
                    faculty_id="S2",
                    link_method="openalex_authorship",
                    link_confidence=1.0,
                )
            ],
            provenance=provenance,
        ),
    ]
    return profiles, works


class TestExistingCollaborations:
    def test_coauthors_are_existing(self, pipeline):
        report = pipeline["engine"].find_collaborations(faculty_id=WEI)

        assert report.status is Status.OK
        assert len(report.pairs) == 1
        pair = report.pairs[0]
        assert pair.collaboration_type is CollaborationType.EXISTING
        assert {pair.faculty_a, pair.faculty_b} == {WEI, LUIS}
        assert pair.shared_work_ids == ["W1001"]
        assert pair.score == pytest.approx(1.0)
        assert 0.0 <= pair.topic_overlap <= 1.0

    def test_existing_pair_carries_shared_work_evidence(self, pipeline):
        pair = pipeline["engine"].find_collaborations(faculty_id=WEI).pairs[0]

        assert pair.evidence
        assert pair.evidence[0].work_id == "W1001"
        assert pair.evidence[0].source_url == "https://doi.org/10.1000/gnn1"
        assert {signal.name for signal in pair.signals} >= {
            "shared_works",
            "latest_shared_year",
        }

    def test_solo_researcher_has_no_pairs(self, pipeline):
        report = pipeline["engine"].find_collaborations(faculty_id=PRIYA)

        assert report.status is Status.OK
        assert report.pairs == []

    def test_unknown_faculty_is_insufficient(self, pipeline):
        report = pipeline["engine"].find_collaborations(faculty_id="A999")

        assert report.status is Status.INSUFFICIENT_EVIDENCE
        assert report.pairs == []


class TestPotentialCollaborations:
    def test_adjacent_topics_propose_potential(self, pipeline, engine_settings):
        profiles, works = _synthetic_pair()
        graph = build_graph(profiles, works, engine_settings, store=False)
        engine = CollaborationEngine(profiles, works, GraphQueries(graph), engine_settings)

        report = engine.find_collaborations()

        assert len(report.pairs) == 1
        pair = report.pairs[0]
        assert pair.collaboration_type is CollaborationType.POTENTIAL
        assert pair.shared_work_ids == []
        assert pair.shared_topics == ["Quantum Dots"]
        assert pair.topic_overlap == pytest.approx(1 / 3)
        assert "adjacent" in " ".join(pair.notes)
        assert pair.evidence

    def test_disjoint_topics_propose_nothing(self, pipeline):
        report = pipeline["engine"].find_collaborations(faculty_id=PRIYA)

        assert report.pairs == []

    def test_near_duplicates_are_not_proposed(self, pipeline, engine_settings):
        profiles, works = _synthetic_pair()
        # Give both researchers the identical topic set: Jaccard 1.0, which the
        # engine treats as near-duplicate rather than complementary.
        for work in works:
            work.topics.append(Topic(id="T903", name="Nanoscience"))
        works[0].topics = [works[0].topics[0], works[0].topics[2]]
        works[1].topics = [works[1].topics[0], works[1].topics[2]]
        graph = build_graph(profiles, works, engine_settings, store=False)
        engine = CollaborationEngine(profiles, works, GraphQueries(graph), engine_settings)

        assert engine.find_collaborations().pairs == []


class TestCollaborationReport:
    def test_all_pairs_lists_existing_only_on_fixture(self, pipeline):
        report = pipeline["engine"].find_collaborations()

        assert {p.collaboration_type for p in report.pairs} == {CollaborationType.EXISTING}

    def test_scores_bounded_and_deterministic(self, pipeline):
        first = pipeline["engine"].find_collaborations()
        second = pipeline["engine"].find_collaborations()

        assert all(0.0 <= p.score <= 1.0 for p in first.pairs)
        assert [(p.faculty_a, p.faculty_b) for p in first.pairs] == [
            (p.faculty_a, p.faculty_b) for p in second.pairs
        ]

    def test_top_k_limits_pairs(self, pipeline):
        assert pipeline["engine"].find_collaborations(top_k=0).pairs == []

    def test_convenience_entry_point(self, pipeline, engine_settings):
        report = find_collaborations(
            pipeline["profiles"],
            pipeline["works"],
            pipeline["engine"].queries,
            engine_settings,
            faculty_id=WEI,
        )

        assert len(report.pairs) == 1

    def test_explanation_names_the_relationship(self, pipeline):
        pair = pipeline["engine"].find_collaborations(faculty_id=WEI).pairs[0]

        assert "Wei Zhang" in pair.explain()
        assert "EXISTING" in pair.explain()
