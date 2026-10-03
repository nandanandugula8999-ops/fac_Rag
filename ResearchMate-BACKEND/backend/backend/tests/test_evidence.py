"""Stage 14 tests: evidence budgets, dedup, and relevance floor."""

from __future__ import annotations

import pytest

from faculty_radar.corpus.builder import build_corpus
from faculty_radar.evidence.selection import EvidenceSelector, select_evidence
from faculty_radar.expertise.engine import ExpertiseEngine
from faculty_radar.linking.builder import link_faculty
from faculty_radar.linking.consent import ConsentEntry, ConsentRegistry
from faculty_radar.models import EvidenceItem
from faculty_radar.normalization.authors import normalize_authors
from faculty_radar.normalization.works import normalize_works
from faculty_radar.resolution.resolver import resolve_researchers
from tests.fake_openalex import AUTHORS, WORKS

WEI = "A100000001"
LUIS = "A100000004"
PRIYA = "A100000003"
SOUTHPORT = "A100000002"


@pytest.fixture
def matches(engine_settings):
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
    documents = build_corpus(profiles, works, engine_settings, store=False)
    engine = ExpertiseEngine(profiles, works, documents, engine_settings)
    return engine.find_experts("graph neural networks").matches


def _settings(engine_settings, **updates):
    evidence = engine_settings.evidence.model_copy(update=updates)
    return engine_settings.model_copy(update={"evidence": evidence})


class TestEvidenceSelection:
    def test_selects_quotable_passages(self, matches, engine_settings):
        selected = select_evidence(matches, engine_settings)

        assert selected
        assert all(item.quote for item in selected)
        assert all(item.source_url for item in selected)

    def test_total_cap_respected(self, matches, engine_settings):
        settings = _settings(engine_settings, max_items=2)

        assert len(select_evidence(matches, settings)) == 2

    def test_per_faculty_cap_enforced(self, matches, engine_settings):
        settings = _settings(engine_settings, max_items=100, max_per_faculty=1)
        selected = select_evidence(matches, settings)
        counts: dict[str, int] = {}
        for item in selected:
            counts[item.faculty_id] = counts.get(item.faculty_id, 0) + 1

        assert all(count <= 1 for count in counts.values())

    def test_relevance_floor_filters_weak_passages(self, matches, engine_settings):
        settings = _settings(engine_settings, min_relevance=0.99)
        selected = select_evidence(matches, settings)

        assert all(item.relevance >= 0.99 for item in selected)

    def test_duplicates_keep_strongest_only(self, engine_settings):
        first = EvidenceItem(
            evidence_id="a",
            doc_id="doc:1",
            quote=" passage ",
            relevance=0.4,
        )
        second = EvidenceItem(
            evidence_id="b",
            doc_id="doc:1",
            quote=" passage ",
            relevance=0.9,
        )

        selected = EvidenceSelector(engine_settings).select(
            [_match_with([first]), _match_with([second])]
        )

        assert [item.evidence_id for item in selected] == ["b"]

    def test_selection_is_deterministic(self, matches, engine_settings):
        first = [item.evidence_id for item in select_evidence(matches, engine_settings)]
        second = [item.evidence_id for item in select_evidence(matches, engine_settings)]

        assert first == second

    def test_empty_input_selects_nothing(self, engine_settings):
        assert select_evidence([], engine_settings) == []


def _match_with(evidence):
    from faculty_radar.models import ExpertiseMatch, ExpertiseType

    return ExpertiseMatch(
        faculty_id="A1",
        faculty_name="Test",
        query="q",
        score=0.5,
        expertise_type=ExpertiseType.INFERRED,
        evidence=evidence,
    )
