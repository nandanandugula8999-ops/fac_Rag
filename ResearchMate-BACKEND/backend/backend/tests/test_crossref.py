"""Crossref tests: verification verdicts, enrichment, and fail-open behavior.

All offline via httpx.MockTransport or stub lookups. No test here touches
the real Crossref API.
"""

from __future__ import annotations

import httpx

from faculty_radar.discovery.providers import CrossrefLookup
from faculty_radar.discovery.service import DiscoveryService


def _message(title="Graph methods for science", year=2023, doi="10.1000/w1"):
    return {
        "DOI": doi,
        "title": [title],
        "author": [{"given": "Wei", "family": "Zhang"}],
        "container-title": ["Journal of Graphs"],
        "issued": {"date-parts": [[year]]},
        "URL": f"https://doi.org/{doi}",
    }


def _lookup(payload=None, status=200, calls=None, raises=None):
    def handler(request):
        if calls is not None:
            calls.append(str(request.url))
        if raises is not None:
            raise raises
        return httpx.Response(status, json={"message": payload or {}})

    return httpx.Client(transport=httpx.MockTransport(handler))


class StubCrossref:
    """Scripted Crossref stand-in for service-level tests."""

    enabled = True

    def __init__(self, verdicts=None):
        from types import SimpleNamespace

        self.settings = SimpleNamespace(max_workers=2)
        self.verdicts = verdicts or {}
        self.lookups = []

    def lookup(self, doi):
        self.lookups.append(doi)
        return None

    def verify(self, doi, title):
        self.lookups.append(doi)
        return self.verdicts.get(doi, {"resolved": False, "title_agrees": None})


class TestLookup:
    def test_success_returns_message(self, engine_settings):
        client = _lookup(_message())
        lookup = CrossrefLookup(http_client=client, settings=engine_settings)

        assert lookup.lookup("10.1000/w1")["title"] == ["Graph methods for science"]

    def test_404_returns_none(self, engine_settings):
        client = _lookup(status=404)
        lookup = CrossrefLookup(http_client=client, settings=engine_settings)

        assert lookup.lookup("10.1000/missing") is None

    def test_transport_error_returns_none(self, engine_settings):
        client = _lookup(raises=httpx.ConnectError("down"))
        lookup = CrossrefLookup(http_client=client, settings=engine_settings)

        assert lookup.lookup("10.1000/w1") is None

    def test_disabled_returns_none_without_http(self, engine_settings):
        settings = engine_settings.model_copy(deep=True)
        settings.crossref.enabled = False
        calls: list = []
        client = _lookup(_message(), calls=calls)
        lookup = CrossrefLookup(http_client=client, settings=settings)

        assert lookup.lookup("10.1000/w1") is None
        assert lookup.enabled is False
        assert calls == []

    def test_results_are_cached(self, engine_settings, tmp_path):
        from faculty_radar.ingestion.cache import ResponseCache

        calls: list = []
        client = _lookup(_message(), calls=calls)
        lookup = CrossrefLookup(
            ResponseCache(tmp_path / "crossref"),
            http_client=client,
            settings=engine_settings,
        )

        assert lookup.lookup("10.1000/w1") is not None
        assert lookup.lookup("10.1000/w1") is not None
        assert len(calls) == 1


class TestVerify:
    def test_agreeing_titles_verify(self, engine_settings):
        client = _lookup(_message(title="Graph Methods for Science: A Survey"))
        lookup = CrossrefLookup(http_client=client, settings=engine_settings)

        verdict = lookup.verify("10.1000/w1", "Graph methods for science")

        assert verdict["resolved"] is True
        assert verdict["title_agrees"] is True
        assert verdict["year"] == 2023
        assert verdict["journal"] == "Journal of Graphs"
        assert verdict["has_authors"] is True

    def test_clashing_titles_mismatch(self, engine_settings):
        client = _lookup(_message(title="Completely Different Paper"))
        lookup = CrossrefLookup(http_client=client, settings=engine_settings)

        verdict = lookup.verify("10.1000/w1", "Graph methods for science")

        assert verdict["resolved"] is True
        assert verdict["title_agrees"] is False

    def test_unresolved_without_overclaiming(self, engine_settings):
        client = _lookup(status=404)
        lookup = CrossrefLookup(http_client=client, settings=engine_settings)

        verdict = lookup.verify("10.1000/nope", "Anything")

        assert verdict == {"resolved": False, "title_agrees": None}


class TestEnrichmentInService:
    def _service(self, engine_settings, tmp_path, payloads, crossref):
        from tests.test_discovery import FakeProvider

        return DiscoveryService(
            engine_settings,
            provider=FakeProvider(payloads),
            crossref=crossref,
            cache_dir=tmp_path / "discovery",
        )

    def test_missing_title_is_filled(self, engine_settings, tmp_path):
        from tests.test_discovery import _work

        payload = _work("W1", None, None, [("A1", "Wei Zhang")])
        payload["doi"] = "https://doi.org/10.1000/real"
        stub = StubCrossref(
            {
                "10.1000/real": {
                    "resolved": True,
                    "title_agrees": None,
                    "title": "Recovered Title",
                    "year": 2021,
                    "journal": "J",
                    "url": "https://doi.org/10.1000/real",
                    "has_authors": True,
                }
            }
        )
        service = self._service(engine_settings, tmp_path, [payload], stub)
        result = service.discover("recovered title")

        assert result.crossref_enriched == 1
        work = next(w for w in result.works if w.openalex_id == "W1")
        assert work.title == "Recovered Title"
        assert work.year == 2021

    def test_complete_records_are_not_rewritten(self, engine_settings, tmp_path):
        from tests.test_discovery import _work

        payload = _work("W1", "Original Title", 2023, [("A1", "Wei Zhang")])
        stub = StubCrossref(
            {
                "10.1000/w1": {
                    "resolved": True,
                    "title_agrees": True,
                    "title": "Slightly Different Title Variant",
                    "year": 1999,
                    "journal": "J",
                    "url": "https://example.org/other",
                    "has_authors": True,
                }
            }
        )
        service = self._service(engine_settings, tmp_path, [payload], stub)
        result = service.discover("original title")
        work = next(w for w in result.works if w.openalex_id == "W1")

        # OpenAlex wins every tie: enrichment only fills gaps.
        assert work.title == "Original Title"
        assert work.year == 2023
        assert result.crossref_verified == 1
        assert result.crossref_enriched == 0

    def test_mismatch_keeps_openalex_and_flags(self, engine_settings, tmp_path):
        from tests.test_discovery import _work

        payload = _work("W1", "Original Title", 2023, [("A1", "Wei Zhang")])
        stub = StubCrossref(
            {
                "10.1000/w1": {
                    "resolved": True,
                    "title_agrees": False,
                    "title": "Totally Other",
                    "year": 1999,
                    "journal": "J",
                    "url": None,
                    "has_authors": True,
                }
            }
        )
        service = self._service(engine_settings, tmp_path, [payload], stub)
        result = service.discover("original title")
        work = next(w for w in result.works if w.openalex_id == "W1")

        assert work.title == "Original Title"
        assert result.crossref_mismatched == 1
        assert result.crossref_verified == 0

    def test_crossref_outage_leaves_openalex_intact(self, engine_settings, tmp_path):
        from tests.test_discovery import _work

        payload = _work("W1", "Original Title", 2023, [("A1", "Wei Zhang")])

        class DownCrossref(StubCrossref):
            def verify(self, doi, title):
                raise httpx.ConnectError("crossref is down")

        service = self._service(engine_settings, tmp_path, [payload], DownCrossref())
        result = service.discover("original title")
        work = next(w for w in result.works if w.openalex_id == "W1")

        # Discovery succeeds on OpenAlex data alone; nothing was checked.
        assert work.title == "Original Title"
        assert result.crossref_checked == 0
        assert result.profiles
