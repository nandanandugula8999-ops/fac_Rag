"""Stage 2 tests: text canonicalization, abstract reconstruction, normalizers."""

from __future__ import annotations

import pytest

from faculty_radar.models import NormalizedWork
from faculty_radar.normalization.abstract import (
    abstract_coverage,
    abstract_is_verbatim_safe,
    reconstruct_abstract,
)
from faculty_radar.normalization.authors import normalize_author, normalize_authors
from faculty_radar.normalization.pipeline import InterimStore, normalize_all
from faculty_radar.normalization.text import (
    canonical_key,
    extract_orcid,
    name_tokens,
    normalize_doi,
    normalize_ror,
    openalex_id,
    tokenize,
)
from faculty_radar.normalization.works import normalize_work, normalize_works
from faculty_radar.paths import build_paths
from tests import fake_openalex
from tests.fake_openalex import AUTHORS, INSTITUTIONS, WORKS

# --------------------------------------------------------------------------
# Text
# --------------------------------------------------------------------------


class TestCanonicalKey:
    def test_folds_case_accents_and_punctuation(self):
        assert canonical_key("José  María-López") == "jose maria lopez"

    def test_collapses_whitespace(self):
        assert canonical_key("Wei   Zhang \n") == "wei zhang"

    def test_empty_input(self):
        assert canonical_key("") == ""
        assert canonical_key(None) == ""

    def test_strips_german_umlaut(self):
        assert canonical_key("Müller") == "muller"


class TestTokens:
    def test_drops_stopwords(self):
        assert tokenize("the graph of neural networks") == ["graph", "neural", "networks"]

    def test_keeps_numbers_and_alphanumerics(self):
        assert tokenize("covid-19 sars-cov-2") == ["covid", "19", "sars", "cov", "2"]

    def test_handles_empty(self):
        assert tokenize(None) == []
        assert tokenize("   ") == []

    def test_name_tokens_keep_surname_particles(self):
        # "van" is part of the surname; dropping it would break name matching.
        assert name_tokens("Ludwig van Beethoven") == ("ludwig", "van", "beethoven")


class TestIdentifiers:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("https://orcid.org/0000-0002-1825-0097", "0000-0002-1825-0097"),
            ("orcid:0000-0002-1825-0097", "0000-0002-1825-0097"),
            ("0000-0002-1825-0097", "0000-0002-1825-0097"),
            # A trailing X check digit is a valid legacy ORCID and is preserved.
            ("https://orcid.org/0000-0002-1825-009X", "0000-0002-1825-009X"),
        ],
    )
    def test_orcid_extracted_from_any_spelling(self, raw, expected):
        assert extract_orcid(raw) == expected

    def test_orcid_absent(self):
        assert extract_orcid("not an orcid") is None
        assert extract_orcid(None) is None

    @pytest.mark.parametrize(
        "raw",
        [
            "https://doi.org/10.1000/ABC.123",
            "http://dx.doi.org/10.1000/abc.123",
            "doi:10.1000/abc.123",
            "10.1000/abc.123",
        ],
    )
    def test_doi_canonicalized(self, raw):
        assert normalize_doi(raw) == "10.1000/abc.123"

    def test_non_doi_returns_none(self):
        # Rule 2: never fabricate an identifier.
        assert normalize_doi("not-a-doi") is None
        assert normalize_doi("") is None

    def test_ror_canonicalized(self):
        assert normalize_ror("https://ror.org/05a0ya142") == "https://ror.org/05a0ya142"
        assert normalize_ror("05A0YA142") == "https://ror.org/05a0ya142"

    def test_invalid_ror_returns_none(self):
        assert normalize_ror("nonsense") is None

    def test_openalex_id_extracted_from_url(self):
        assert openalex_id("https://openalex.org/A100000001") == "A100000001"
        assert openalex_id(None) is None


# --------------------------------------------------------------------------
# Abstract reconstruction
# --------------------------------------------------------------------------


class TestAbstract:
    def test_reconstructs_in_correct_order(self):
        index = {"we": [0], "present": [1], "graph": [2], "networks": [3]}
        assert reconstruct_abstract(index) == "we present graph networks"

    def test_positions_drive_order_not_dict_order(self):
        # Keys are inserted out of order but positions are authoritative.
        index = {"networks": [3], "neural": [1], "graph": [2]}
        assert reconstruct_abstract(index) == "neural graph networks"

    def test_handles_repeated_token(self):
        index = {"protein": [0, 2], "folding": [1]}
        assert reconstruct_abstract(index) == "protein folding protein"

    def test_uses_max_position_not_token_count(self):
        # A sparse index must still produce a correctly ordered string.
        index = {"a": [0], "b": [5], "c": [6]}
        assert reconstruct_abstract(index).split() == ["a", "b", "c"]

    def test_empty_index_is_none(self):
        assert reconstruct_abstract({}) is None
        assert reconstruct_abstract(None) is None

    def test_unparseable_index_is_none(self):
        assert reconstruct_abstract({"a": "not-a-list"}) is None
        assert reconstruct_abstract({"a": [-1, "x"]}) is None

    def test_verbatim_safety_flags_sparse_index(self):
        dense = {"a": [0], "b": [1], "c": [2]}
        sparse = {"a": [0], "b": [5]}
        assert abstract_is_verbatim_safe(dense) is True
        assert abstract_is_verbatim_safe(sparse) is False
        assert abstract_coverage(dense) == 1.0
        assert abstract_coverage(sparse) == pytest.approx(2 / 6, abs=1e-4)


# --------------------------------------------------------------------------
# Authors
# --------------------------------------------------------------------------


class TestNormalizeAuthor:
    def test_normalizes_full_record(self):
        author = normalize_author(AUTHORS[0])

        assert author.openalex_id == "A100000001"
        assert author.orcid == "0000-0002-1825-0097"
        assert "W. Zhang" in author.name_variants
        assert author.works_count == 4

    def test_missing_orcid_stays_none(self):
        author = normalize_author(AUTHORS[1])
        assert author.orcid is None

    def test_topics_are_deduplicated_and_ordered(self):
        author = normalize_author(AUTHORS[0])
        assert len(author.topics) == 1
        assert author.topics[0].name == "Graph Neural Networks"

    def test_institutions_derived_from_affiliations(self):
        author = normalize_author(AUTHORS[0])
        assert [i.name for i in author.institutions] == ["Northgate University"]

    def test_payload_without_id_is_dropped(self):
        assert normalize_author({"display_name": "Nameless"}) is None

    def test_provenance_records_source_and_hash(self):
        author = normalize_author(AUTHORS[0])
        assert author.provenance.source == "openalex"
        assert author.provenance.source_id == "A100000001"
        assert author.provenance.record_hash

    def test_last_known_institutions_shape_is_supported(self):
        # Real OpenAlex author records use last_known_institutions, not affiliations.
        payload = {
            "id": "https://openalex.org/A9",
            "display_name": "Test Person",
            "last_known_institutions": [INSTITUTIONS[0]],
        }
        author = normalize_author(payload)

        assert author is not None
        assert [i.name for i in author.institutions] == ["Northgate University"]
        assert author.institutions[0].id == "I1000"

    def test_normalization_is_deterministic(self):
        """Same input must yield byte-identical provenance, so re-runs are no-ops."""
        first = normalize_author(AUTHORS[0], retrieved_at="2024-01-01T00:00:00+00:00")
        second = normalize_author(AUTHORS[0], retrieved_at="2024-01-01T00:00:00+00:00")
        assert first.model_dump(mode="json") == second.model_dump(mode="json")

    def test_deduplicates_across_payloads(self):
        authors = normalize_authors([AUTHORS[0], AUTHORS[0]])
        assert len(authors) == 1


# --------------------------------------------------------------------------
# Works
# --------------------------------------------------------------------------


class TestNormalizeWork:
    def test_normalizes_core_fields(self):
        work = normalize_work(WORKS[0])
        assert work.openalex_id == "W1001"
        assert work.doi == "10.1000/gnn1"
        assert work.year == 2023
        assert work.publication_date.isoformat() == "2023-04-12"

    def test_reconstructs_abstract(self):
        work = normalize_work(WORKS[0])
        assert "graph neural networks" in work.abstract

    def test_absent_abstract_stays_none(self):
        work = normalize_work({"id": "https://openalex.org/WX", "title": "T"})
        assert work.abstract is None

    def test_author_ids_extracted_from_authorship(self):
        work = normalize_work(WORKS[0])
        assert work.author_ids == ["A100000001", "A100000004"]

    def test_institutions_collected_from_authorships(self):
        work = normalize_work(WORKS[0])
        assert [i.id for i in work.institutions] == ["I1000"]

    def test_open_access_url_preferred(self):
        work = normalize_work(WORKS[0])
        assert work.best_oa_url == "https://example.org/gnn1.pdf"

    def test_closed_work_falls_back_to_landing_page(self):
        work = normalize_work(WORKS[3])
        assert work.best_oa_url == "https://example.org/marine1"

    def test_citation_url_from_doi(self):
        work = normalize_work(WORKS[0])
        assert work.citation_url == "https://doi.org/10.1000/gnn1"

    def test_references_are_short_ids_and_sorted(self):
        work = normalize_work(WORKS[0])
        assert work.referenced_work_ids == ["W1004"]
        assert work.related_work_ids == ["W1005"]

    def test_keywords_sorted_by_score(self):
        work = normalize_work(WORKS[0])
        assert [k.name for k in work.keywords] == [
            "graph neural network",
            "molecular property prediction",
        ]

    def test_bad_date_yields_none_not_epoch(self):
        payload = {"id": "https://openalex.org/WX", "publication_date": "sometime in 2019"}
        work = normalize_work(payload)
        assert work.publication_date is None
        assert work.year is None

    def test_partial_date_resolves_to_first_of_period(self):
        work = normalize_work({"id": "https://openalex.org/WY", "publication_date": "2019-05"})
        assert work.publication_date.isoformat() == "2019-05-01"

    def test_payload_without_id_is_dropped(self):
        assert normalize_work({"title": "Anonymous"}) is None

    def test_deduplicates_by_id(self):
        assert len(normalize_works([WORKS[0], WORKS[0]])) == 1

    def test_roundtrips_through_the_model(self):
        work = normalize_work(WORKS[0])
        assert NormalizedWork.model_validate(work.model_dump(mode="json")) == work


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------


class TestNormalizationPipeline:
    @pytest.fixture
    def loaded(self, engine_settings):
        from faculty_radar.ingestion.pipeline import ingest_institution

        client, _ = fake_openalex.build_fake_client(engine_settings)
        raw = __import__("faculty_radar.ingestion.store", fromlist=["RawStore"]).RawStore(
            build_paths(engine_settings)
        )
        ingest_institution(client, raw, "I1000", engine_settings.ingestion)
        return raw

    def test_writes_interim_records(self, engine_settings, loaded):
        store = InterimStore(build_paths(engine_settings))
        result = normalize_all(loaded, engine_settings)

        assert result.authors_out == 3
        assert result.works_out == 4
        assert len(store.load_authors()) == 3
        assert len(store.load_works()) == 4

    def test_interim_records_carry_provenance(self, engine_settings, loaded):
        store = InterimStore(build_paths(engine_settings))
        normalize_all(loaded, engine_settings)

        authors = store.load_authors()
        assert authors[0].provenance.raw_path
        assert authors[0].provenance.record_hash

    def test_rewrite_is_atomic_and_idempotent(self, engine_settings, loaded):
        store = InterimStore(build_paths(engine_settings))
        normalize_all(loaded, engine_settings)
        first = store.read("authors")

        normalize_all(loaded, engine_settings)
        assert store.read("authors") == first

    def test_temporary_file_is_cleaned_up(self, engine_settings, loaded):
        normalize_all(loaded, engine_settings)
        store = InterimStore(build_paths(engine_settings))
        assert not list(store.paths.interim.glob("*.tmp"))

    def test_empty_raw_store_yields_empty_interim(self, engine_settings):
        from faculty_radar.ingestion.store import RawStore

        store = InterimStore(build_paths(engine_settings))
        result = normalize_all(RawStore(build_paths(engine_settings)), engine_settings)

        assert result.authors_out == 0
        assert store.load_works() == []
