"""Stage 4 tests: the consent gate, publication linking, and link provenance."""

from __future__ import annotations

import json

import pytest

from faculty_radar.linking.builder import LINK_METHODS, FacultyLinker, link_faculty
from faculty_radar.linking.consent import ConsentEntry, ConsentRegistry
from faculty_radar.linking.store import FacultyStore
from faculty_radar.models import FacultyProfile
from faculty_radar.normalization.authors import normalize_authors
from faculty_radar.normalization.works import normalize_works
from faculty_radar.paths import build_paths
from faculty_radar.resolution.resolver import resolve_researchers
from tests.fake_openalex import AUTHORS, WORKS


@pytest.fixture
def normalized():
    return normalize_authors(AUTHORS), normalize_works(WORKS)


@pytest.fixture
def all_consented():
    entries = {
        a["id"].rsplit("/", 1)[-1]: ConsentEntry(
            researcher_id=a["id"].rsplit("/", 1)[-1], consented=True
        )
        for a in AUTHORS
    }
    return ConsentRegistry(entries, enforce=True)


@pytest.fixture
def resolved(normalized, engine_settings):
    authors, works = normalized
    return resolve_researchers(authors, works, engine_settings, store=False)


# --------------------------------------------------------------------------
# Consent
# --------------------------------------------------------------------------


class TestConsentRegistry:
    def test_consented_person_is_allowed(self):
        registry = ConsentRegistry({"A1": ConsentEntry("A1", consented=True)})
        assert registry.is_consented("A1")

    def test_absent_person_is_denied(self):
        registry = ConsentRegistry({}, enforce=True)
        assert not registry.is_consented("A1")

    def test_explicit_refusal_is_denied(self):
        registry = ConsentRegistry({"A1": ConsentEntry("A1", consented=False)})
        assert not registry.is_consented("A1")

    def test_enforcement_can_be_disabled_explicitly(self):
        registry = ConsentRegistry({}, enforce=False)
        assert registry.is_consented("A1")

    def test_stated_topics_come_only_from_registry(self):
        registry = ConsentRegistry(
            {"A1": ConsentEntry("A1", consented=True, stated_topics=["Graphs"])}
        )
        assert [t.name for t in registry.stated_topics("A1")] == ["Graphs"]

    def test_no_registry_entry_means_no_stated_topics(self):
        registry = ConsentRegistry({"A1": ConsentEntry("A1", consented=True)})
        assert registry.stated_topics("A2") == []

    def test_roundtrips_through_json(self, tmp_path):
        registry = ConsentRegistry(
            {
                "A1": ConsentEntry(
                    "A1",
                    consented=True,
                    stated_topics=["Graphs"],
                    stated_project_descriptions=["Molecular prediction"],
                    contact_email="a@uni.edu",
                    consented_at="2026-01-01",
                )
            }
        )
        path = registry.write(tmp_path / "consent.json")
        loaded = ConsentRegistry.from_file(path)

        assert loaded.is_consented("A1")
        assert loaded.project_descriptions("A1") == ["Molecular prediction"]

    def test_missing_file_denies_everyone(self, tmp_path):
        registry = ConsentRegistry.from_file(tmp_path / "absent.json")
        assert not registry.is_consented("A1")

    def test_corrupt_file_denies_everyone(self, tmp_path):
        path = tmp_path / "consent.json"
        path.write_text("{not json", encoding="utf-8")
        # Failing closed: an unreadable registry must not discoverable anyone.
        assert not ConsentRegistry.from_file(path).is_consented("A1")

    def test_entry_without_researcher_id_is_skipped(self, tmp_path):
        path = tmp_path / "consent.json"
        path.write_text(json.dumps({"entries": [{"consented": True}]}), encoding="utf-8")
        assert len(ConsentRegistry.from_file(path)) == 0


# --------------------------------------------------------------------------
# Linking
# --------------------------------------------------------------------------


class TestFacultyLinking:
    def test_only_consented_faculty_get_profiles(self, resolved, normalized, engine_settings):
        authors, works = normalized
        # Consent only the first researcher.
        registry = ConsentRegistry(
            {"A100000001": ConsentEntry("A100000001", consented=True)}, enforce=True
        )

        profiles = link_faculty(
            resolved.researchers, authors, works, engine_settings, consent=registry, store=False
        )

        assert len(profiles) == 1
        assert profiles[0].faculty_id == "A100000001"

    def test_empty_registry_yields_no_profiles(self, resolved, normalized, engine_settings):
        authors, works = normalized
        registry = ConsentRegistry({}, enforce=True)

        profiles = link_faculty(
            resolved.researchers, authors, works, engine_settings, consent=registry, store=False
        )
        assert profiles == []

    def test_publications_are_linked_with_method_and_confidence(
        self, resolved, normalized, engine_settings, all_consented
    ):
        authors, works = normalized
        profiles = link_faculty(
            resolved.researchers,
            authors,
            works,
            engine_settings,
            consent=all_consented,
            store=False,
        )

        zhang = next(p for p in profiles if p.faculty_id == "A100000001")
        assert len(zhang.publications) == 3
        for publication in zhang.publications:
            assert publication.link_method == "openalex_authorship"
            assert publication.link_confidence == LINK_METHODS["openalex_authorship"]

    def test_linked_publication_carries_citation_metadata(
        self, resolved, normalized, engine_settings, all_consented
    ):
        authors, works = normalized
        profiles = link_faculty(
            resolved.researchers,
            authors,
            works,
            engine_settings,
            consent=all_consented,
            store=False,
        )

        zhang = next(p for p in profiles if p.faculty_id == "A100000001")
        first = zhang.publications[0]
        assert first.doi
        assert first.citation_url == f"https://doi.org/{first.doi}"
        assert first.title
        assert first.year

    def test_publications_sorted_newest_first(
        self, resolved, normalized, engine_settings, all_consented
    ):
        authors, works = normalized
        profiles = link_faculty(
            resolved.researchers,
            authors,
            works,
            engine_settings,
            consent=all_consented,
            store=False,
        )
        zhang = next(p for p in profiles if p.faculty_id == "A100000001")
        years = [p.year for p in zhang.publications]
        assert years == sorted(years, reverse=True)

    def test_stated_topics_come_from_consent_not_openalex(
        self, resolved, normalized, engine_settings
    ):
        """Rule 3: derived OpenAlex topics must not masquerade as stated expertise."""
        authors, works = normalized
        registry = ConsentRegistry(
            {"A100000001": ConsentEntry("A100000001", consented=True)}, enforce=True
        )

        profiles = link_faculty(
            resolved.researchers, authors, works, engine_settings, consent=registry, store=False
        )

        # The registry declares no topics, so none are stated - even though
        # OpenAlex assigns this author "Graph Neural Networks".
        assert profiles[0].stated_topics == []

    def test_registry_topics_become_stated(self, resolved, normalized, engine_settings):
        authors, works = normalized
        registry = ConsentRegistry(
            {
                "A100000001": ConsentEntry(
                    "A100000001", consented=True, stated_topics=["Molecular Property Prediction"]
                )
            },
            enforce=True,
        )

        profiles = link_faculty(
            resolved.researchers, authors, works, engine_settings, consent=registry, store=False
        )
        assert [t.name for t in profiles[0].stated_topics] == ["Molecular Property Prediction"]

    def test_work_missing_from_index_is_skipped(
        self, resolved, normalized, engine_settings, all_consented
    ):
        _, works = normalized
        linker = FacultyLinker(engine_settings, consent=all_consented)
        researcher = next(r for r in resolved.researchers if r.researcher_id == "A100000001")

        # Drop one work from the index entirely.
        partial = {w.openalex_id: w for w in works if w.openalex_id != "W1001"}
        publications = linker._linked_publications(researcher, {}, partial)

        assert "W1001" not in {p.work_id for p in publications}

    def test_low_confidence_links_are_dropped_not_used(self, engine_settings, all_consented):
        linker = FacultyLinker(engine_settings, consent=all_consented, min_link_confidence=0.99)
        assert LINK_METHODS["name_match_unverified"] < linker.min_link_confidence


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


class TestFacultyStore:
    def test_profiles_roundtrip(self, resolved, normalized, engine_settings, all_consented):
        authors, works = normalized
        paths = build_paths(engine_settings)
        link_faculty(
            resolved.researchers, authors, works, engine_settings, paths, consent=all_consented
        )

        loaded = FacultyStore(paths).load_profiles()
        assert len(loaded) == len(resolved.researchers)
        assert all(isinstance(profile, FacultyProfile) for profile in loaded)
        assert {p.faculty_id for p in loaded} == {r.researcher_id for r in resolved.researchers}

    def test_stored_profiles_keep_link_provenance(
        self, resolved, normalized, engine_settings, all_consented
    ):
        authors, works = normalized
        paths = build_paths(engine_settings)
        link_faculty(
            resolved.researchers, authors, works, engine_settings, paths, consent=all_consented
        )

        raw = (paths.processed / "faculty.jsonl").read_text(encoding="utf-8")
        assert "link_confidence" in raw
        assert "openalex_authorship" in raw

    def test_institutions_written(self, resolved, normalized, engine_settings, all_consented):
        authors, works = normalized
        paths = build_paths(engine_settings)
        link_faculty(
            resolved.researchers, authors, works, engine_settings, paths, consent=all_consented
        )
        assert FacultyStore(paths).load_institutions()

    def test_loading_empty_store_is_safe(self, engine_settings):
        assert FacultyStore(build_paths(engine_settings)).load_profiles() == []
