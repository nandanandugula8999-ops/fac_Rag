"""Stage 1 tests: HTTP cache, OpenAlex client, raw store, ingestion pipeline."""

from __future__ import annotations

import json

import httpx
import pytest

from faculty_radar.config.settings import ScopeSettings
from faculty_radar.ingestion.cache import ResponseCache, make_cache_key
from faculty_radar.ingestion.client import OpenAlexClient, OpenAlexError
from faculty_radar.ingestion.pipeline import ingest_all, ingest_institution
from faculty_radar.ingestion.store import ENTITIES, RawStore
from faculty_radar.paths import build_paths
from tests.fake_openalex import (
    AUTHORS,
    INSTITUTIONS,
    WORKS,
    FakeOpenAlexTransport,
    build_fake_client,
)

# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------


class TestCacheKey:
    def test_key_is_stable_across_param_order(self):
        a = make_cache_key("GET", "https://x/y", {"b": 2, "a": 1})
        b = make_cache_key("GET", "https://x/y", {"a": 1, "b": 2})
        assert a == b

    def test_key_changes_with_params(self):
        assert make_cache_key("GET", "u", {"a": 1}) != make_cache_key("GET", "u", {"a": 2})

    def test_secrets_are_excluded_from_key(self):
        with_key = make_cache_key("GET", "u", {"a": 1, "api_key": "secret"})
        without = make_cache_key("GET", "u", {"a": 1})
        assert with_key == without


class TestResponseCache:
    def test_miss_then_hit(self, tmp_path):
        cache = ResponseCache(tmp_path)
        key = make_cache_key("GET", "u", {"a": 1})

        assert cache.get(key) is None
        cache.put(key, {"value": 7})
        assert cache.get(key) == {"value": 7}
        assert cache.get_stats()["hits"] == 1

    def test_expired_entry_is_a_miss(self, tmp_path):
        cache = ResponseCache(tmp_path, ttl_hours=0)
        key = make_cache_key("GET", "u")
        cache.put(key, {"value": 1})
        assert cache.get(key) is None

    def test_disabled_cache_never_stores(self, tmp_path):
        cache = ResponseCache(tmp_path, enabled=False)
        key = make_cache_key("GET", "u")
        cache.put(key, {"value": 1})
        assert cache.get(key) is None
        assert not list(tmp_path.rglob("*.json"))

    def test_corrupt_entry_degrades_to_miss(self, tmp_path):
        cache = ResponseCache(tmp_path)
        key = make_cache_key("GET", "u")
        path = cache._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json", encoding="utf-8")
        assert cache.get(key) is None

    def test_clear_removes_entries(self, tmp_path):
        cache = ResponseCache(tmp_path)
        cache.put(make_cache_key("GET", "u"), {"v": 1})
        cache.clear()
        assert cache.get(make_cache_key("GET", "u")) is None


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------


class TestOpenAlexClient:
    def test_fetches_single_record(self, engine_settings):
        client, _ = build_fake_client(engine_settings)
        institution = client.get_institution("I1000")
        assert institution["display_name"] == "Northgate University"

    def test_paginates_across_cursors(self, engine_settings):
        # page_size=2 against 3 matching authors forces a second page.
        settings = engine_settings.model_copy(
            update={"openalex": engine_settings.openalex.model_copy(update={"page_size": 2})}
        )
        client, transport = build_fake_client(settings)

        authors = list(client.iter_authors("I1000"))

        assert len(authors) == 3
        assert len(transport.requests) == 2
        # The second request must carry the cursor from the first response.
        assert "cursor=" in str(transport.requests[1].url)

    def test_limit_short_circuits_pagination(self, engine_settings):
        settings = engine_settings.model_copy(
            update={"openalex": engine_settings.openalex.model_copy(update={"page_size": 2})}
        )
        client, transport = build_fake_client(settings)

        authors = list(client.iter_authors("I1000", limit=1))

        assert len(authors) == 1
        # The second page must never be requested.
        assert len(transport.requests) == 1

    def test_works_filtered_by_author(self, engine_settings):
        client, _ = build_fake_client(engine_settings)

        works = list(client.iter_works("A100000001"))
        titles = {w["title"] for w in works}

        assert len(works) == 3
        assert "Graph Neural Networks for Molecular Property Prediction" in titles

    def test_sends_polite_pool_mailto(self, engine_settings):
        settings = engine_settings.model_copy(
            update={
                "openalex": engine_settings.openalex.model_copy(update={"mailto": "me@uni.edu"})
            }
        )
        client, transport = build_fake_client(settings)
        client.get_institution("I1000")
        # Compare decoded params: httpx percent-encodes '@' in the query string.
        assert transport.requests[-1].url.params["mailto"] == "me@uni.edu"

    def test_api_key_is_never_written_to_cache(self, engine_settings, tmp_path):

        settings = engine_settings.model_copy(
            update={"openalex": engine_settings.openalex.model_copy(update={"api_key": "s3cret"})}
        )
        cache = ResponseCache(tmp_path / "http")
        transport = FakeOpenAlexTransport()
        client = OpenAlexClient(
            settings.openalex, cache, http_client=httpx.Client(transport=transport)
        )

        client.get_institution("I1000")

        written = "".join(
            p.read_text(encoding="utf-8") for p in (tmp_path / "http").rglob("*.json")
        )
        assert "s3cret" not in written

    def test_retries_on_server_error(self, engine_settings):
        client, transport = build_fake_client(engine_settings, failures=2)
        institution = client.get_institution("I1000")
        assert institution["id"].endswith("I1000")
        assert len(transport.requests) == 3

    def test_raises_after_exhausting_retries(self, engine_settings):
        settings = engine_settings.model_copy(
            update={"openalex": engine_settings.openalex.model_copy(update={"max_retries": 2})}
        )
        client, _ = build_fake_client(settings, failures=99)
        with pytest.raises(OpenAlexError):
            client.get_institution("I1000")

    def test_404_raises_immediately(self, engine_settings):
        client, transport = build_fake_client(settings=engine_settings, failures=0)
        with pytest.raises(OpenAlexError):
            client.get_institution("I999999")
        # A client error is not retried.
        assert len(transport.requests) == 1

    def test_response_cache_prevents_refetch(self, engine_settings, tmp_path):
        cache = ResponseCache(tmp_path / "http")

        transport = FakeOpenAlexTransport()
        http = httpx.Client(transport=transport)
        client = OpenAlexClient(engine_settings.openalex, cache, http_client=http)

        client.get_institution("I1000")
        client.get_institution("I1000")

        assert len(transport.requests) == 1
        assert cache.get_stats()["hits"] == 1

    def test_missing_record_raises(self, engine_settings):
        client, _ = build_fake_client(settings=engine_settings)
        with pytest.raises(OpenAlexError):
            client.get_work("W_MISSING")


# --------------------------------------------------------------------------
# Raw store
# --------------------------------------------------------------------------


class TestRawStore:
    def test_appends_and_reads_back(self, engine_settings):
        store = RawStore(build_paths(engine_settings))
        assert store.append("author", AUTHORS[0]) is True
        payloads = list(store.iter_payloads("author"))
        assert payloads[0]["display_name"] == "Wei Zhang"

    def test_append_is_idempotent_by_id(self, engine_settings):
        store = RawStore(build_paths(engine_settings))
        assert store.append("author", AUTHORS[0]) is True
        assert store.append("author", AUTHORS[0]) is False
        assert store.count("author") == 1

    def test_preserves_original_payload_unmodified(self, engine_settings):
        store = RawStore(build_paths(engine_settings))
        original = json.loads(json.dumps(WORKS[0]))
        store.append("work", original)

        # read() returns parsed envelopes; the payload must be byte-identical
        # to what the source returned, with no normalization applied.
        stored = store.read("work")[0]["payload"]
        assert stored == original

    def test_envelope_carries_provenance(self, engine_settings):
        store = RawStore(build_paths(engine_settings))
        store.append("institution", INSTITUTIONS[0])
        envelope = store.read("institution")[0]
        assert envelope["source"] == "openalex"
        assert envelope["retrieved_at"]
        assert envelope["source_url"]

    def test_record_without_id_is_rejected(self, engine_settings):
        store = RawStore(build_paths(engine_settings))
        with pytest.raises(ValueError, match="no 'id'"):
            store.append("author", {"display_name": "Nameless"})

    def test_unknown_entity_is_rejected(self, engine_settings):
        store = RawStore(build_paths(engine_settings))
        with pytest.raises(ValueError, match="unknown entity"):
            store.path_for("planets")

    def test_seen_ids_survive_new_store_instance(self, engine_settings):
        paths = build_paths(engine_settings)
        RawStore(paths).append("author", AUTHORS[0])
        # A fresh store must re-read ids from disk, not re-append.
        assert RawStore(paths).append("author", AUTHORS[0]) is False

    def test_stats_covers_all_entities(self, engine_settings):
        store = RawStore(build_paths(engine_settings))
        assert set(store.stats()) == set(ENTITIES)

    def test_read_missing_file_returns_empty(self, engine_settings):
        assert RawStore(build_paths(engine_settings)).read("topic") == []


# --------------------------------------------------------------------------
# Pipeline
# --------------------------------------------------------------------------


class TestIngestionPipeline:
    # Authors at I1000 are A100000001, A100000003 and A100000004. Their
    # distinct works are W1001, W1002, W1003 and W1005. W1004 belongs to
    # A100000002, who is at I2000, so it must never appear here.
    EXPECTED_AUTHORS = 3
    EXPECTED_WORKS = 4

    def test_ingests_authors_and_works(self, engine_settings):
        client, _ = build_fake_client(engine_settings)
        store = RawStore(build_paths(engine_settings))

        result = ingest_institution(client, store, "I1000", engine_settings.ingestion)

        assert result.authors_stored == self.EXPECTED_AUTHORS
        assert result.works_stored == self.EXPECTED_WORKS
        assert store.count("institution") == 1

    def test_out_of_scope_institution_work_is_excluded(self, engine_settings):
        client, _ = build_fake_client(engine_settings)
        store = RawStore(build_paths(engine_settings))

        ingest_institution(client, store, "I1000", engine_settings.ingestion)

        stored_ids = {r["id"] for r in store.read("work")}
        assert "https://openalex.org/W1004" not in stored_ids

    def test_shared_works_are_stored_once(self, engine_settings):
        client, _ = build_fake_client(engine_settings)
        store = RawStore(build_paths(engine_settings))

        result = ingest_institution(client, store, "I1000", engine_settings.ingestion)

        # W1001 has two in-scope authors; it must not be written twice.
        assert result.works_skipped >= 1
        assert store.count("work") == self.EXPECTED_WORKS

    def test_reingest_is_idempotent(self, engine_settings):
        client, _ = build_fake_client(engine_settings)
        store = RawStore(build_paths(engine_settings))
        ingest_institution(client, store, "I1000", engine_settings.ingestion)

        second = ingest_institution(client, store, "I1000", engine_settings.ingestion)

        assert second.authors_stored == 0
        assert second.works_stored == 0
        assert store.count("work") == self.EXPECTED_WORKS

    def test_respects_max_authors_cap(self, engine_settings):
        settings = engine_settings.model_copy(
            update={"ingestion": engine_settings.ingestion.model_copy(update={"max_authors": 1})}
        )
        client, _ = build_fake_client(settings)
        store = RawStore(build_paths(engine_settings))

        result = ingest_institution(client, store, "I1000", settings.ingestion)

        assert result.authors_stored == 1

    def test_require_abstract_filters_works(self, engine_settings):
        settings = engine_settings.model_copy(
            update={
                "ingestion": engine_settings.ingestion.model_copy(
                    update={"require_abstract": True, "max_works_total": 100}
                )
            }
        )
        client, _ = build_fake_client(settings)
        store = RawStore(build_paths(engine_settings))

        ingest_institution(client, store, "I1000", settings.ingestion)

        # Every fixture work carries an abstract, so nothing is dropped.
        assert store.count("work") == self.EXPECTED_WORKS

    def test_unreachable_institution_reports_error(self, engine_settings):
        settings = engine_settings.model_copy(
            update={"ingestion": engine_settings.ingestion.model_copy(update={"max_retries": 1})}
        )
        client, _ = build_fake_client(settings, failures=99)
        store = RawStore(build_paths(engine_settings))

        result = ingest_institution(client, store, "I999", settings.ingestion)

        assert result.errors
        assert store.count("institution") == 0

    def test_ingest_all_with_empty_scope_is_noop(self, engine_settings):
        settings = engine_settings.model_copy(update={"scope": ScopeSettings()})

        result = ingest_all(settings=settings)

        assert result.authors_fetched == 0
        assert result.errors

    def test_ingest_all_aggregates_across_institutions(self, engine_settings):
        client, _ = build_fake_client(engine_settings)
        store = RawStore(build_paths(engine_settings))

        total = ingest_all(client, store, engine_settings, institution_ids=["I1000", "I2000"])

        assert total.institutions == 2
        assert store.count("author") == len(AUTHORS)
