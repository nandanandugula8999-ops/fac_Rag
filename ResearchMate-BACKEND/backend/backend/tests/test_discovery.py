"""Discovery tests: normalization, adapter, scope gate, and cache.

All offline. The provider is faked; the resolution, linking, and corpus
stages under test are the real ones.
"""

from __future__ import annotations

import pytest

from faculty_radar.discovery.providers import normalize_query
from faculty_radar.discovery.service import DiscoveryResult, DiscoveryService
from faculty_radar.models import DocumentType


def _work(
    work_id,
    title,
    year,
    authors,
    topics=("Graph Neural Networks",),
    abstract="Some abstract text about the work.",
):
    return {
        "id": f"https://openalex.org/{work_id}",
        "doi": f"https://doi.org/10.1000/{work_id.lower()}",
        "title": title,
        "publication_year": year,
        "publication_date": f"{year}-01-01",
        "type": "article",
        "cited_by_count": 10,
        "abstract_inverted_index": {token: [i] for i, token in enumerate(abstract.lower().split())},
        "authorships": [
            {
                "author_position": "first",
                "is_corresponding": True,
                "author": {"id": f"https://openalex.org/{a[0]}", "display_name": a[1]},
                "raw_affiliation_strings": ["Northgate University"],
                "institutions": [
                    {
                        "id": "https://openalex.org/I1000",
                        "display_name": "Northgate University",
                        "country_code": "US",
                    }
                ],
            }
            for a in authors
        ],
        "topics": [{"id": "https://openalex.org/T100", "display_name": t} for t in topics],
        "keywords": [],
        "concepts": [],
        "referenced_works": [],
        "related_works": [],
        "locations": [{"landing_page_url": f"https://example.org/{work_id}"}],
        "is_retracted": False,
    }


class FakeProvider:
    name = "fake"

    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = 0

    def search(self, query, *, limit=50):
        self.calls += 1
        return self.payloads[:limit]


@pytest.fixture
def payloads():
    return [
        _work("W1", "Graph methods for science", 2023, [("A1", "Wei Zhang")]),
        _work("W2", "More graph methods", 2024, [("A1", "W. Zhang")]),
        _work(
            "W3",
            "Unrelated marine work",
            2022,
            [("A2", "Marina Costa")],
            topics=("Marine Biology",),
            abstract="Coral reefs under thermal stress.",
        ),
    ]


class _UnresolvedCrossref:
    """Hermetic stand-in: every DOI is unverifiable, OpenAlex stands alone."""

    enabled = True

    def __init__(self):
        from types import SimpleNamespace

        self.settings = SimpleNamespace(max_workers=2)

    def lookup(self, doi):
        return None

    def verify(self, doi, title):
        return {"resolved": False, "title_agrees": None}


@pytest.fixture
def service(engine_settings, tmp_path):
    return DiscoveryService(
        engine_settings,
        provider=FakeProvider([]),
        cache_dir=tmp_path / "discovery",
        crossref=_UnresolvedCrossref(),
    )


class TestNormalizeQuery:
    def test_case_and_whitespace_insensitive(self):
        assert normalize_query("  Graph   Neural\nNetworks ") == "graph neural networks"

    def test_empty_query_normalizes_empty(self):
        assert normalize_query("   ") == ""


class TestAdapter:
    def test_same_author_id_merges_across_works(self, engine_settings, tmp_path, payloads):
        service = DiscoveryService(
            engine_settings,
            provider=FakeProvider(payloads),
            cache_dir=tmp_path / "discovery",
            crossref=_UnresolvedCrossref(),
        )
        # Scope includes the fixture institution so all authors qualify.
        service.provider.calls = 0
        result = service.discover("graph methods")

        assert isinstance(result, DiscoveryResult)
        assert result.works_retrieved == 3
        wei = next(p for p in result.profiles if p.faculty_id == "A1")
        assert len(wei.publications) == 2
        assert {d.work_id for d in result.documents if d.faculty_id == "A1"} >= {"W1", "W2"}

    def test_out_of_scope_authors_get_no_profile(self, engine_settings, tmp_path):
        offshore = _work(
            "W9", "Offshore work", 2023, [("A9", "Far Away")], topics=("Marine Biology",)
        )
        offshore["authorships"][0]["institutions"] = [
            {
                "id": "https://openalex.org/I2000",
                "display_name": "Southport Institute",
                "country_code": "GB",
            }
        ]
        service = DiscoveryService(
            engine_settings,
            provider=FakeProvider([offshore]),
            cache_dir=tmp_path / "discovery",
            crossref=_UnresolvedCrossref(),
        )
        # engine_settings scopes I1000, so the I2000 author must not surface.
        result = service.discover("offshore work")

        assert result.works_retrieved == 1
        assert result.profiles == ()
        assert result.documents == ()

    def test_empty_scope_means_global_not_fallback(self, engine_settings):
        from faculty_radar.discovery.providers import OpenAlexDiscoveryProvider

        settings = engine_settings.model_copy(deep=True)
        settings.scope.institution_ids = []
        provider = OpenAlexDiscoveryProvider(settings, client=None)

        # No silent default institution: empty scope searches the whole universe.
        assert provider.institution_ids == []

    def test_global_scope_qualifies_every_author(self, engine_settings, tmp_path):
        from faculty_radar.discovery.providers import OpenAlexDiscoveryProvider

        offshore = _work(
            "W9", "Offshore work", 2023, [("A9", "Far Away")], topics=("Marine Biology",)
        )
        offshore["authorships"][0]["institutions"] = [
            {
                "id": "https://openalex.org/I2000",
                "display_name": "Southport Institute",
                "country_code": "GB",
            }
        ]
        settings = engine_settings.model_copy(deep=True)
        settings.scope.institution_ids = []
        service = DiscoveryService(
            settings,
            provider=OpenAlexDiscoveryProvider(settings, client=None),
            cache_dir=tmp_path / "discovery",
            crossref=_UnresolvedCrossref(),
        )
        # Monkeypatched search: no network, provider returns the payload.
        service.provider.search = lambda query, limit=50: [offshore]
        result = service.discover("offshore work")

        assert result.works_retrieved == 1
        assert [p.faculty_id for p in result.profiles] == ["A9"]

    def test_no_stated_expertise_without_registry(self, engine_settings, tmp_path, payloads):
        service = DiscoveryService(
            engine_settings,
            provider=FakeProvider(payloads),
            cache_dir=tmp_path / "discovery",
            crossref=_UnresolvedCrossref(),
        )
        result = service.discover("graph methods")
        profile_chunks = [
            doc for doc in result.documents if doc.document_type is DocumentType.FACULTY_PROFILE
        ]

        # No registry declares anything, so nothing may be marked stated and
        # profile topics must stay empty even though publications are topical.
        assert result.documents
        assert all(doc.is_stated is False for doc in result.documents)
        assert profile_chunks
        assert all(chunk.topics == [] for chunk in profile_chunks)

    def test_empty_discovery_adapts_to_empty(self, engine_settings, tmp_path):
        service = DiscoveryService(
            engine_settings,
            provider=FakeProvider([]),
            cache_dir=tmp_path / "discovery",
            crossref=_UnresolvedCrossref(),
        )
        result = service.discover("nothing matches this")

        assert result.profiles == ()
        assert result.documents == ()
        assert result.works_retrieved == 0

    def test_empty_query_short_circuits(self, service):
        result = service.discover("   ")

        assert result.profiles == ()
        assert result.api_calls == 0


class TestDiscoveryCache:
    def test_repeat_query_hits_cache(self, engine_settings, tmp_path, payloads):
        provider = FakeProvider(payloads)
        service = DiscoveryService(
            engine_settings, provider=provider, cache_dir=tmp_path / "discovery"
        )

        first = service.discover("Graph Methods")
        second = service.discover("graph methods")

        assert provider.calls == 1
        assert first.cached is False
        assert second.cached is True
        assert [d.doc_id for d in first.documents] == [d.doc_id for d in second.documents]

    def test_incomplete_results_are_not_cached(self, engine_settings, tmp_path):
        provider = FakeProvider([])
        service = DiscoveryService(
            engine_settings, provider=provider, cache_dir=tmp_path / "discovery"
        )

        service.discover("nothing")
        service.discover("nothing")

        assert provider.calls == 2
