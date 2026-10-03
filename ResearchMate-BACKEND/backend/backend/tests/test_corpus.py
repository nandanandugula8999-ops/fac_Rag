"""Stage 6 tests: whole-publication chunks, profile chunks, and provenance."""

from __future__ import annotations

import json

import pytest

from faculty_radar.corpus.builder import CorpusBuilder, build_corpus, corpus_stats
from faculty_radar.corpus.store import CorpusStore
from faculty_radar.linking.builder import link_faculty
from faculty_radar.linking.consent import ConsentEntry, ConsentRegistry
from faculty_radar.models import (
    CorpusDocument,
    DocumentType,
    LinkedPublication,
)
from faculty_radar.normalization.authors import normalize_authors
from faculty_radar.normalization.works import normalize_works
from faculty_radar.paths import build_paths
from faculty_radar.resolution.resolver import resolve_researchers
from tests.fake_openalex import AUTHORS, WORKS

WEI = "A100000001"
LUIS = "A100000004"
PRIYA = "A100000003"
SOUTHPORT = "A100000002"
STATED_TOPIC = "Molecular Property Prediction"
STATED_PROJECT = "Explain which molecular structures cause a predicted property."


@pytest.fixture
def normalized():
    return normalize_authors(AUTHORS), normalize_works(WORKS)


@pytest.fixture
def resolved(normalized, engine_settings):
    authors, _ = normalized
    works = normalize_works(WORKS)
    return resolve_researchers(authors, works, engine_settings, store=False)


def _registry(*researcher_ids, topics=None, projects=None):
    entries = {}
    for researcher_id in researcher_ids:
        entries[researcher_id] = ConsentEntry(
            researcher_id=researcher_id,
            consented=True,
            stated_topics=(topics or {}).get(researcher_id, []),
            stated_project_descriptions=(projects or {}).get(researcher_id, []),
        )
    return ConsentRegistry(entries, enforce=True)


@pytest.fixture
def full_corpus(normalized, resolved, engine_settings):
    authors, works = normalized
    profiles = link_faculty(
        resolved.researchers,
        authors,
        works,
        engine_settings,
        consent=_registry(
            WEI,
            LUIS,
            PRIYA,
            SOUTHPORT,
            topics={WEI: [STATED_TOPIC]},
            projects={WEI: [STATED_PROJECT]},
        ),
        store=False,
    )
    documents = build_corpus(profiles, works, engine_settings, store=False)
    return {"profiles": profiles, "works": works, "documents": documents}


@pytest.fixture
def wei_only_corpus(normalized, resolved, engine_settings):
    authors, works = normalized
    profiles = link_faculty(
        resolved.researchers,
        authors,
        works,
        engine_settings,
        consent=_registry(WEI),
        store=False,
    )
    return {
        "profiles": profiles,
        "works": works,
        "documents": build_corpus(profiles, works, engine_settings, store=False),
    }


def _by_id(documents):
    return {doc.doc_id: doc for doc in documents}


def _profile_chunk(documents, faculty_id):
    return next(
        doc
        for doc in documents
        if doc.faculty_id == faculty_id and doc.document_type is DocumentType.FACULTY_PROFILE
    )


def _publication_chunk(documents, faculty_id, work_id):
    return next(
        doc
        for doc in documents
        if doc.faculty_id == faculty_id
        and doc.work_id == work_id
        and doc.document_type is DocumentType.PUBLICATION
    )


# --------------------------------------------------------------------------
# Whole-publication chunks
# --------------------------------------------------------------------------


class TestPublicationChunks:
    def test_expected_profile_and_publication_counts(self, full_corpus):
        stats = corpus_stats(full_corpus["documents"])

        # Four consented profiles. Wei links three works; Priya, Luis, and the
        # Southport homonym link one each. W1001 therefore has one chunk for
        # each consented co-owner, not one global chunk.
        assert stats["documents"] == 10
        assert stats["faculty_profile_documents"] == 4
        assert stats["publication_documents"] == 6

    def test_one_whole_chunk_per_faculty_publication_link(self, full_corpus):
        documents = full_corpus["documents"]
        wei_publications = [
            doc
            for doc in documents
            if doc.faculty_id == WEI and doc.document_type is DocumentType.PUBLICATION
        ]

        assert sorted(doc.work_id for doc in wei_publications) == ["W1001", "W1002", "W1005"]
        assert len({doc.doc_id for doc in wei_publications}) == 3
        assert wei_publications[0].doc_id == CorpusDocument.make_id(
            WEI, "W1001", DocumentType.PUBLICATION
        )

    def test_publication_chunk_contains_the_whole_source_text(self, full_corpus):
        chunk = _publication_chunk(full_corpus["documents"], WEI, "W1002")

        assert "Scaling Graph Neural Networks on Large Molecular Datasets" in chunk.text
        assert "cluster based batching" in chunk.text
        assert chunk.text.count("Scaling Graph Neural Networks") == 1

    def test_publication_chunk_carries_full_metadata_and_provenance(self, full_corpus):
        chunk = _publication_chunk(full_corpus["documents"], WEI, "W1002")

        assert chunk.faculty_id == WEI
        assert chunk.work_id == "W1002"
        assert chunk.institution_id == "I1000"
        assert chunk.document_type is DocumentType.PUBLICATION
        assert chunk.topics == ["Graph Neural Networks"]
        assert chunk.keywords == ["graph neural network"]
        assert chunk.year == 2024
        assert chunk.doi == "10.1000/gnn2"
        assert chunk.source_url == "https://doi.org/10.1000/gnn2"
        assert chunk.field_origins == {
            "topics": "publication",
            "keywords": "publication",
            "title": "publication",
            "abstract": "publication",
        }
        assert chunk.is_stated is False
        assert chunk.provenance is not None
        assert chunk.provenance.source == "openalex"
        assert chunk.provenance.source_id == "W1002"
        assert chunk.provenance.record_hash

    def test_coauthored_work_has_separate_owner_chunks(self, full_corpus):
        wei_chunk = _publication_chunk(full_corpus["documents"], WEI, "W1001")
        luis_chunk = _publication_chunk(full_corpus["documents"], LUIS, "W1001")

        assert wei_chunk.doc_id != luis_chunk.doc_id
        assert wei_chunk.text == luis_chunk.text
        assert wei_chunk.provenance.record_hash == luis_chunk.provenance.record_hash


# --------------------------------------------------------------------------
# Profile chunks and stated/derived separation
# --------------------------------------------------------------------------


class TestProfileChunks:
    def test_one_profile_chunk_per_consented_faculty(self, full_corpus):
        documents = full_corpus["documents"]
        profile_chunks = [
            doc for doc in documents if doc.document_type is DocumentType.FACULTY_PROFILE
        ]

        assert sorted(doc.faculty_id for doc in profile_chunks) == sorted(
            [WEI, LUIS, PRIYA, SOUTHPORT]
        )
        assert len({doc.doc_id for doc in profile_chunks}) == 4

    def test_profile_chunk_marks_declared_expertise_as_stated(self, full_corpus):
        chunk = _profile_chunk(full_corpus["documents"], WEI)

        assert chunk.work_id is None
        assert chunk.institution_id == "I1000"
        assert chunk.year == 2025
        assert chunk.topics == [STATED_TOPIC]
        assert chunk.keywords == []
        assert chunk.doi is None
        assert STATED_TOPIC in chunk.text
        assert STATED_PROJECT in chunk.text
        assert chunk.field_origins["stated_topics"] == "stated"
        assert chunk.field_origins["project_descriptions"] == "stated"
        assert chunk.is_stated is True
        assert chunk.provenance is not None
        assert chunk.provenance.source == "openalex+consent_registry"
        assert chunk.provenance.source_id == WEI

    def test_publication_evidence_does_not_leak_into_profile_topics(self, full_corpus):
        profile_chunk = _profile_chunk(full_corpus["documents"], WEI)
        publication_chunk = _publication_chunk(full_corpus["documents"], WEI, "W1001")

        assert "Graph Neural Networks" in publication_chunk.topics
        assert "Graph Neural Networks" not in profile_chunk.topics
        assert "graph neural network" in publication_chunk.keywords
        assert profile_chunk.keywords == []

    def test_profile_without_declared_expertise_is_not_marked_stated(self, full_corpus):
        chunk = _profile_chunk(full_corpus["documents"], SOUTHPORT)

        assert chunk.topics == []
        assert chunk.is_stated is False
        assert chunk.field_origins["publication_activity"] == "derived"
        assert "Linked publications: 1" in chunk.text


# --------------------------------------------------------------------------
# Consent, determinism, and persistence
# --------------------------------------------------------------------------


class TestCorpusPipeline:
    def test_unconsented_people_have_no_chunks(self, wei_only_corpus):
        documents = wei_only_corpus["documents"]

        assert sorted({doc.faculty_id for doc in documents}) == [WEI]
        assert len(documents) == 4
        assert "Luis Moreno" not in "\n".join(doc.text for doc in documents)
        assert "Coral Reef Resilience Under Thermal Stress" not in "\n".join(
            doc.text for doc in documents
        )

    def test_build_is_deterministic(self, full_corpus):
        first = [doc.doc_id for doc in full_corpus["documents"]]
        rebuilt = build_corpus(full_corpus["profiles"], full_corpus["works"], store=False)

        assert [doc.doc_id for doc in rebuilt] == first
        assert [doc.text for doc in rebuilt] == [doc.text for doc in full_corpus["documents"]]

    def test_linked_publication_without_a_normalized_work_is_skipped(
        self, full_corpus, engine_settings
    ):
        profile = next(p for p in full_corpus["profiles"] if p.faculty_id == WEI)
        extended = profile.model_copy(
            update={
                "publications": [
                    *profile.publications,
                    LinkedPublication(
                        work_id="W999",
                        faculty_id=WEI,
                        link_method="openalex_authorship",
                        link_confidence=1.0,
                    ),
                ]
            }
        )

        documents = build_corpus([extended], full_corpus["works"], engine_settings, store=False)

        assert "W999" not in {doc.work_id for doc in documents}
        assert len(documents) == 4

    def test_store_roundtrip_preserves_documents(self, full_corpus, engine_settings):
        paths = build_paths(engine_settings)
        CorpusStore(paths).write_documents(full_corpus["documents"])

        loaded = CorpusStore(paths).load_documents()
        assert [doc.doc_id for doc in loaded] == [doc.doc_id for doc in full_corpus["documents"]]
        assert all(doc.provenance is not None for doc in loaded)
        assert all(doc.provenance.source for doc in loaded)
        assert _publication_chunk(loaded, WEI, "W1002").provenance.record_hash

        catalog = CorpusStore(paths).load_catalog()
        assert catalog["meta"]["documents"] == len(full_corpus["documents"])
        assert len(catalog["documents"]) == len(full_corpus["documents"])

    def test_documents_file_contains_one_record_per_line(self, full_corpus, engine_settings):
        paths = build_paths(engine_settings)
        store = CorpusStore(paths)
        store.write_documents(full_corpus["documents"])

        lines = store.documents_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == len(full_corpus["documents"])
        assert all(json.loads(line)["doc_id"] for line in lines)

    def test_missing_corpus_loads_safely(self, engine_settings):
        store = CorpusStore(build_paths(engine_settings))

        assert store.load_documents() == []
        assert store.load_catalog() == {}

    def test_builder_rejects_an_unconsented_profile_directly(self, full_corpus):
        profile = next(p for p in full_corpus["profiles"] if p.faculty_id == WEI)
        unconsented = profile.model_copy(update={"consented": False})

        assert CorpusBuilder().build_profile_chunk(unconsented) is None
        assert CorpusBuilder().build_publication_chunk(unconsented, full_corpus["works"][0]) is None
