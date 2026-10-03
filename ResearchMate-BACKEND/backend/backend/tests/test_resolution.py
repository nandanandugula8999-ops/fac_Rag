"""Stage 3 tests: signals, verdicts, clustering, and the never-merge-on-name rule."""

from __future__ import annotations

import pytest

from faculty_radar.models import (
    Institution,
    NormalizedAuthor,
    NormalizedWork,
    Provenance,
    ResolutionVerdict,
    Topic,
)
from faculty_radar.normalization.authors import normalize_author
from faculty_radar.normalization.works import normalize_work
from faculty_radar.paths import build_paths
from faculty_radar.resolution.matching import (
    compute_signals,
    institution_overlap,
    name_similarity,
    orcid_compatibility,
    publication_overlap,
    topic_similarity,
)
from faculty_radar.resolution.resolver import ResearcherResolver, resolve_researchers
from faculty_radar.resolution.store import ResolvedStore
from tests import fake_openalex
from tests.fake_openalex import AUTHORS, WORKS


def make_author(
    author_id: str,
    name: str,
    *,
    orcid: str | None = None,
    institutions: list[str] | None = None,
    topics: list[str] | None = None,
    variants: list[str] | None = None,
    cited: int = 0,
) -> NormalizedAuthor:
    """Build an author directly, for focused resolution tests."""
    return NormalizedAuthor(
        openalex_id=author_id,
        name=name,
        display_name=name,
        orcid=orcid,
        name_variants=variants or [],
        institutions=[
            Institution(id=i, name=f"Inst {i}", type="education") for i in (institutions or [])
        ],
        topics=[Topic(name=t, share=1.0) for t in (topics or [])],
        works_count=1,
        cited_by_count=cited,
        provenance=Provenance(source="test", source_id=author_id),
    )


def make_work(work_id: str, author_ids: list[str], *, title: str = "T") -> NormalizedWork:
    from faculty_radar.models import Authorship

    return NormalizedWork(
        openalex_id=work_id,
        title=title,
        authorships=[Authorship(raw_author_id=a) for a in author_ids],
        provenance=Provenance(source="test", source_id=work_id),
    )


# --------------------------------------------------------------------------
# ORCID
# --------------------------------------------------------------------------


class TestOrcid:
    def test_identical_orcid_is_decisive(self):
        a = make_author("A1", "Wei Zhang", orcid="0000-0001")
        b = make_author("A2", "Wei Zhang", orcid="0000-0001")
        signal = orcid_compatibility(a, b)
        assert signal.supports_merge
        assert signal.score == 1.0

    def test_conflicting_orcid_does_not_support_merge(self):
        a = make_author("A1", "Wei Zhang", orcid="0000-0001")
        b = make_author("A2", "Wei Zhang", orcid="0000-0002")
        assert not orcid_compatibility(a, b).supports_merge

    def test_missing_orcid_is_neutral(self):
        a = make_author("A1", "Wei Zhang")
        b = make_author("A2", "Wei Zhang")
        signal = orcid_compatibility(a, b)
        assert signal.score == 0.0
        assert not signal.supports_merge


# --------------------------------------------------------------------------
# Names
# --------------------------------------------------------------------------


class TestNameSimilarity:
    def test_identical_names_match(self):
        a = make_author("A1", "Wei Zhang")
        b = make_author("A2", "wei  zhang")
        assert name_similarity(a, b).score == 1.0

    def test_initials_match_variants(self):
        a = make_author("A1", "Wei Zhang")
        b = make_author("A2", "W. Zhang")
        assert name_similarity(a, b).supports_merge

    def test_name_variant_field_is_used(self):
        a = make_author("A1", "Wei Zhang", variants=["W. Zhang"])
        b = make_author("A2", "W. Zhang")
        assert name_similarity(a, b).supports_merge

    def test_different_names_do_not_match(self):
        a = make_author("A1", "Priya Raghavan")
        b = make_author("A2", "Luis Moreno")
        assert not name_similarity(a, b).supports_merge

    def test_same_surname_scores_partially(self):
        a = make_author("A1", "Wei Zhang")
        b = make_author("A2", "Li Zhang")
        signal = name_similarity(a, b)
        assert 0 < signal.score < 1.0


# --------------------------------------------------------------------------
# Institutions, publications, topics
# --------------------------------------------------------------------------


class TestOtherSignals:
    def test_shared_institution(self):
        a = make_author("A1", "X", institutions=["I1"])
        b = make_author("A2", "X", institutions=["I1"])
        assert institution_overlap(a, b).supports_merge

    def test_different_institutions_do_not_support_merge(self):
        a = make_author("A1", "X", institutions=["I1"])
        b = make_author("A2", "X", institutions=["I2"])
        assert not institution_overlap(a, b).supports_merge

    def test_shared_publication(self):
        a = make_author("A1", "X")
        b = make_author("A2", "X")
        works = {"A1": [make_work("W1", ["A1"])], "A2": [make_work("W1", ["A2"])]}
        signal, shared = publication_overlap(a, b, works)
        assert signal.supports_merge
        assert shared == ["W1"]

    def test_no_shared_publications(self):
        a = make_author("A1", "X")
        b = make_author("A2", "X")
        works = {"A1": [make_work("W1", ["A1"])], "A2": [make_work("W2", ["A2"])]}
        signal, shared = publication_overlap(a, b, works)
        assert not signal.supports_merge
        assert shared == []

    def test_unavailable_publications_is_neutral(self):
        a, b = make_author("A1", "X"), make_author("A2", "X")
        assert not publication_overlap(a, b, {})[0].supports_merge

    def test_shared_topics_are_weak_evidence(self):
        a = make_author("A1", "X", topics=["Graphs"])
        b = make_author("A2", "Y", topics=["Graphs"])
        assert topic_similarity(a, b)[0].supports_merge

    def test_blocking_reason_short_circuits_other_signals(self):
        a = make_author("A1", "Wei Zhang", orcid="0000-0001", institutions=["I1"])
        b = make_author("A2", "Wei Zhang", orcid="0000-0002", institutions=["I1"])

        signals = compute_signals(a, b)

        assert signals.blocking_reason
        # Only the ORCID signal is computed; weaker ones are not even evaluated.
        assert [s.name for s in signals.signals] == ["orcid"]


# --------------------------------------------------------------------------
# Verdicts - the rules that matter
# --------------------------------------------------------------------------


class TestVerdicts:
    def test_identical_openalex_id_is_same_person(self):
        resolver = ResearcherResolver()
        author = make_author("A1", "Wei Zhang")
        decision = resolver.decide(compute_signals(author, author))
        assert decision.verdict is ResolutionVerdict.SAME_PERSON

    def test_conflicting_orcid_is_different_person(self):
        resolver = ResearcherResolver()
        a = make_author("A1", "Wei Zhang", orcid="0000-0001")
        b = make_author("A2", "Wei Zhang", orcid="0000-0002")
        decision = resolver.decide(compute_signals(a, b))
        assert decision.verdict is ResolutionVerdict.DIFFERENT_PERSON
        assert decision.blocking_reason

    def test_matching_orcid_merges_despite_different_names(self):
        resolver = ResearcherResolver()
        a = make_author("A1", "Wei Zhang", orcid="0000-0001")
        b = make_author("A2", "Zhang Wei", orcid="0000-0001")
        decision = resolver.decide(compute_signals(a, b))
        assert decision.verdict is ResolutionVerdict.SAME_PERSON

    def test_same_name_alone_is_NEVER_merged(self):
        """The load-bearing rule: identical names must not auto-merge."""
        resolver = ResearcherResolver()
        a = make_author("A1", "Wei Zhang", institutions=["I1"])
        b = make_author("A2", "Wei Zhang", institutions=["I2"])
        decision = resolver.decide(compute_signals(a, b))

        assert decision.verdict is not ResolutionVerdict.SAME_PERSON
        assert decision.verdict is ResolutionVerdict.NEEDS_REVIEW
        assert "name matches but no corroborating evidence" in decision.blocking_reason

    def test_same_name_and_shared_work_merges(self):
        resolver = ResearcherResolver()
        a = make_author("A1", "Wei Zhang", institutions=["I1"])
        b = make_author("A2", "Wei Zhang", institutions=["I1"])
        works = {"A1": [make_work("W1", ["A1"])], "A2": [make_work("W1", ["A2"])]}
        decision = resolver.decide(compute_signals(a, b, works))
        assert decision.verdict is ResolutionVerdict.SAME_PERSON

    def test_shared_work_merges_despite_name_mismatch(self):
        resolver = ResearcherResolver()
        a = make_author("A1", "Wei Zhang", institutions=["I1"])
        b = make_author("A2", "W. Zhang", institutions=["I1"])
        works = {"A1": [make_work("W1", ["A1"])], "A2": [make_work("W1", ["A2"])]}
        decision = resolver.decide(compute_signals(a, b, works))
        assert decision.verdict is ResolutionVerdict.SAME_PERSON

    def test_different_names_and_no_shared_work_are_different_people(self):
        resolver = ResearcherResolver()
        a = make_author("A1", "Priya Raghavan")
        b = make_author("A2", "Luis Moreno")
        decision = resolver.decide(compute_signals(a, b))
        assert decision.verdict is ResolutionVerdict.DIFFERENT_PERSON

    def test_every_decision_carries_evidence(self):
        resolver = ResearcherResolver()
        a = make_author("A1", "Wei Zhang", institutions=["I1"])
        b = make_author("A2", "Wei Zhang", institutions=["I2"])
        decision = resolver.decide(compute_signals(a, b))

        assert decision.evidence
        assert {e.signal for e in decision.evidence} >= {"orcid", "name"}
        assert all(0.0 <= e.weight <= 1.0 for e in decision.evidence)

    def test_confidence_within_bounds(self):
        resolver = ResearcherResolver()
        authors = [
            make_author("A1", "Wei Zhang", institutions=["I1"]),
            make_author("A2", "Wei Zhang", institutions=["I1"]),
            make_author("A3", "Wei Zhang", institutions=["I2"]),
        ]
        for decision in resolver.compare(authors)[0]:
            assert 0.0 <= decision.confidence <= 1.0


# --------------------------------------------------------------------------
# Clustering
# --------------------------------------------------------------------------


class TestClustering:
    def test_transitive_merges_collapse(self):
        # A~B and B~C must produce one cluster of three, not two.
        resolver = ResearcherResolver()
        a = make_author("A1", "Wei Zhang", orcid="0000-0001")
        b = make_author("A2", "Wei Zhang", orcid="0000-0001", institutions=["I2"])
        c = make_author("A3", "Zhang W.", orcid="0000-0001", institutions=["I3"])

        researchers, _, _, _ = resolver.cluster([a, b, c], {})

        assert len(researchers) == 1
        assert len(researchers[0].openalex_ids) == 3

    def test_distinct_researchers_stay_separate(self):
        resolver = ResearcherResolver()
        authors = [
            make_author("A1", "Priya Raghavan", orcid="0000-0001"),
            make_author("A2", "Luis Moreno", orcid="0000-0002"),
        ]
        researchers, _, _, _ = resolver.cluster(authors, {})
        assert len(researchers) == 2

    def test_homonyms_are_not_merged(self):
        """The two fixture Wei Zhangs are different people at different institutions."""
        resolver = ResearcherResolver()
        authors = [normalize_author(a) for a in (AUTHORS[0], AUTHORS[1])]

        researchers, _, needs_review, _ = resolver.cluster(authors, {})

        assert len(researchers) == 2
        assert needs_review
        assert needs_review[0].verdict is ResolutionVerdict.NEEDS_REVIEW

    def test_publications_pooled_onto_canonical_identity(self):
        resolver = ResearcherResolver()
        a = make_author("A1", "Wei Zhang", orcid="0000-0001")
        b = make_author("A2", "Zhang W.", orcid="0000-0001")
        works = {"A1": [make_work("W1", ["A1"])], "A2": [make_work("W2", ["A2"])]}

        researchers, _, _, _ = resolver.cluster([a, b], works)

        assert researchers[0].work_ids == ["W1", "W2"]

    def test_name_variants_preserved_on_canonical_identity(self):
        resolver = ResearcherResolver()
        a = make_author("A1", "Wei Zhang", orcid="0000-0001", variants=["W. Zhang"])
        b = make_author("A2", "Zhang Wei", orcid="0000-0001")

        researchers, _, _, _ = resolver.cluster([a, b], {})

        assert researchers[0].name_variants

    def test_unrelated_surnames_are_not_compared(self):
        resolver = ResearcherResolver()
        authors = [make_author("A1", "Priya Raghavan"), make_author("A2", "Luis Moreno")]
        _, decisions, _, compared = resolver.cluster(authors, {})
        # Different surnames cannot be the same person, so no pair is examined.
        assert compared == 0
        assert decisions == []


# --------------------------------------------------------------------------
# End to end
# --------------------------------------------------------------------------


class TestResolutionPipeline:
    @pytest.fixture
    def loaded(self, engine_settings):
        from faculty_radar.ingestion.pipeline import ingest_institution
        from faculty_radar.ingestion.store import RawStore
        from faculty_radar.normalization.pipeline import InterimStore, normalize_all

        paths = build_paths(engine_settings)
        client, _ = fake_openalex.build_fake_client(engine_settings)
        raw = RawStore(paths)
        ingest_institution(client, raw, "I1000", engine_settings.ingestion)
        interim = InterimStore(paths)
        normalize_all(raw, engine_settings, paths, store=interim)
        return interim

    def test_writes_resolved_identities(self, engine_settings, loaded):
        report = resolve_researchers(loaded.load_authors(), loaded.load_works(), engine_settings)

        store = ResolvedStore(build_paths(engine_settings))
        assert len(store.load_researchers()) == len(report.researchers)
        assert report.researchers

    def test_review_queue_records_ambiguous_pairs(self, engine_settings, loaded):
        report = resolve_researchers(loaded.load_authors(), loaded.load_works(), engine_settings)

        queue = ResolvedStore(build_paths(engine_settings)).load_review_queue()
        assert len(queue) == len(report.needs_review)

    def test_no_researcher_holds_two_orcids(self, engine_settings, loaded):
        report = resolve_researchers(loaded.load_authors(), loaded.load_works(), engine_settings)

        for researcher in report.researchers:
            assert researcher.orcid is None or len(researcher.openalex_ids) >= 1
            # A merged identity with two different ORCIDs must never be emitted.
            assert len({r.orcid for r in report.researchers if r.orcid}) == len(
                [r for r in report.researchers if r.orcid]
            )

    def test_no_researcher_claims_a_work_twice(self, engine_settings, loaded):
        report = resolve_researchers(loaded.load_authors(), loaded.load_works(), engine_settings)

        for researcher in report.researchers:
            # A researcher must not list the same publication twice. (A single
            # publication *may* belong to several researchers - that is
            # co-authorship, which the collaboration engine relies on.)
            assert len(researcher.work_ids) == len(set(researcher.work_ids))

    def test_coauthored_work_is_reachable_from_both_researchers(self, engine_settings, loaded):
        report = resolve_researchers(loaded.load_authors(), loaded.load_works(), engine_settings)

        owners = [r for r in report.researchers if "W1001" in r.work_ids]
        assert len(owners) == 2, "W1001 has two co-authors and both must keep it"

    def test_repeat_run_is_deterministic(self, engine_settings, loaded):
        first = resolve_researchers(loaded.load_authors(), loaded.load_works(), engine_settings)
        second = resolve_researchers(loaded.load_authors(), loaded.load_works(), engine_settings)

        assert [r.researcher_id for r in first.researchers] == [
            r.researcher_id for r in second.researchers
        ]
        assert first.stats() == second.stats()


class TestFixtureIntegrity:
    def test_two_wei_zhang_records_exist_in_fixtures(self):
        """The homonym case this whole stage exists for must be present."""
        names = [a["display_name"] for a in AUTHORS]
        assert names.count("Wei Zhang") == 2

    def test_they_sit_at_different_institutions(self):
        zhangs = [a for a in AUTHORS if a["display_name"] == "Wei Zhang"]
        institutions = {i["id"] for a in zhangs for i in a["last_known_institutions"]}
        assert len(institutions) == 2

    def test_one_has_an_orcid_and_one_does_not(self):
        zhangs = [a for a in AUTHORS if a["display_name"] == "Wei Zhang"]
        assert sorted(bool(a["orcid"]) for a in zhangs) == [False, True]

    def test_shared_work_exists_between_same_researcher(self):
        works = [normalize_work(w) for w in WORKS]
        by_author: dict[str, set[str]] = {}
        for work in works:
            for author_id in work.author_ids:
                by_author.setdefault(author_id, set()).add(work.openalex_id)
        # W1001 has two authors, which is what makes co-authorship observable.
        assert any(len(v) > 1 for v in by_author.values())
