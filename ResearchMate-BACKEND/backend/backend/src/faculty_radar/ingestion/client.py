"""OpenAlex API client.

Wraps cursor pagination, retry/backoff, and rate limiting so that no other
module deals with HTTP. The client is constructed with an injected
`httpx.Client`, which is what makes ingestion testable without network access.

Every request goes through the response cache, so re-running ingestion costs
nothing and is reproducible.

Note on `mailto`: OpenAlex's "polite pool" requires a contact address in the
query string. It is sent on the wire but never written to the cache.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Mapping
from typing import Any

import httpx

from faculty_radar.config import OpenAlexSettings, get_logger
from faculty_radar.ingestion.cache import ResponseCache, make_cache_key

logger = get_logger(__name__)

# Status codes worth retrying: rate limiting and transient server faults.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class OpenAlexError(RuntimeError):
    """Raised when a request cannot be completed after all retries."""


class OpenAlexClient:
    """Read-only OpenAlex client.

    Usage:
        with OpenAlexClient(settings.openalex, cache) as client:
            for author in client.iter_authors("I185315811"):
                ...
    """

    def __init__(
        self,
        settings: OpenAlexSettings | None = None,
        cache: ResponseCache | None = None,
        *,
        http_client: httpx.Client | None = None,
        cache_dir: Any = None,
    ) -> None:
        self.settings = settings or OpenAlexSettings()
        self.cache = cache
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=self.settings.timeout_seconds)
        self.request_count = 0
        self._last_request_at = 0.0
        self._min_interval = self.settings.requests_per_second

    # ---------------------------------------------------------------- plumbing

    def _throttle(self) -> None:
        """Sleep just enough to respect the configured request rate."""
        if self._min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        wait = (1.0 / self._min_interval) - elapsed
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    def _auth_params(self) -> dict[str, str]:
        params: dict[str, str] = {}
        if self.settings.mailto:
            params["mailto"] = self.settings.mailto
        if self.settings.api_key:
            params["api_key"] = self.settings.api_key
        return params

    def _build_url(self, path: str, params: Mapping[str, Any] | None) -> tuple[str, dict]:
        url = f"{self.settings.base_url.rstrip('/')}/{path.lstrip('/')}"
        merged: dict[str, Any] = dict(params or {})
        merged.update(self._auth_params())
        return url, merged

    def get_json(self, path: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Fetch one JSON document, with caching and retry."""
        url, merged = self._build_url(path, params)
        cache_key = make_cache_key("GET", url, merged)
        if self.cache is not None:
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.debug("cache hit", extra={"path": path})
                return cached

        last_error: Exception | None = None
        for attempt in range(1, self.settings.max_retries + 1):
            self._throttle()
            self.request_count += 1
            try:
                response = self._client.get(url, params=merged)
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning(
                    "request failed",
                    extra={"path": path, "attempt": attempt, "error": str(exc)},
                )
                self._sleep_backoff(attempt)
                continue

            if response.status_code in RETRYABLE_STATUS:
                last_error = OpenAlexError(f"HTTP {response.status_code}")
                logger.warning(
                    "retryable status",
                    extra={"path": path, "attempt": attempt, "status": response.status_code},
                )
                # A 429 with Retry-After is a server instruction, not a guess.
                if response.status_code == 429 and "Retry-After" in response.headers:
                    delay = float(response.headers["Retry-After"])
                    time.sleep(min(delay, 60.0))
                    continue
                self._sleep_backoff(attempt)
                continue

            if response.is_error:
                raise OpenAlexError(
                    f"HTTP {response.status_code} for {path}: {response.text[:200]}"
                )

            payload = response.json()
            if self.cache is not None:
                self.cache.put(cache_key, payload)
            return payload

        raise OpenAlexError(
            f"exhausted {self.settings.max_retries} attempts for {path}: {last_error}"
        )

    def _sleep_backoff(self, attempt: int) -> None:
        delay = self.settings.backoff_seconds * (2 ** (attempt - 1))
        time.sleep(min(delay, 30.0))

    def paginate(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
        *,
        limit: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield individual result items across all cursor pages.

        Stops early at `limit` without fetching the next page, which matters
        when a large author list is capped.
        """
        base_params = dict(params or {})
        base_params.setdefault("per-page", self.settings.page_size)
        cursor = "*"
        yielded = 0

        while cursor:
            page_params = {**base_params, "cursor": cursor}
            payload = self.get_json(path, page_params)
            results = payload.get("results") or []
            for item in results:
                yield item
                yielded += 1
                if limit is not None and yielded >= limit:
                    return
            cursor = (payload.get("meta") or {}).get("next_cursor")

    # ------------------------------------------------------------- endpoints

    def get_institution(self, institution_id: str) -> dict[str, Any]:
        return self.get_json(f"institutions/{institution_id}")

    def get_author(self, author_id: str) -> dict[str, Any]:
        return self.get_json(f"authors/{author_id}")

    def get_work(self, work_id: str) -> dict[str, Any]:
        return self.get_json(f"works/{work_id}")

    def iter_authors(
        self, institution_id: str, *, limit: int | None = None
    ) -> Iterator[dict[str, Any]]:
        """Authors affiliated with an institution, most-cited first."""
        yield from self.paginate(
            "authors",
            {
                "filter": f"last_known_institutions.id:{institution_id}",
                "sort": "cited_by_count:desc",
            },
            limit=limit,
        )

    def iter_works(
        self,
        author_id: str,
        *,
        limit: int | None = None,
        from_year: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Works by one author, newest first."""
        filters = [f"author.id:{author_id}"]
        if from_year is not None:
            filters.append(f"from_publication_date:{from_year}-01-01")
        yield from self.paginate(
            "works", {"filter": ",".join(filters), "sort": "publication_date:desc"}, limit=limit
        )

    def iter_topic_works(
        self,
        topic: str,
        institution_id: str | None = None,
        *,
        limit: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Works matching a topic seed, optionally scoped to an institution."""
        filters = (
            [f"topics.id:{topic}"]
            if _looks_like_openalex_id(topic)
            else [f"title_and_abstract.search:{topic}"]
        )
        if institution_id:
            filters.append(f"institutions.id:{institution_id}")
        yield from self.paginate("works", {"filter": ",".join(filters)}, limit=limit)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> OpenAlexClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def _looks_like_openalex_id(value: str) -> bool:
    """OpenAlex IDs are short uppercase alphanumeric tags, e.g. T10159, I185315811."""
    return value.isalnum() and value.isupper() and len(value) <= 12
