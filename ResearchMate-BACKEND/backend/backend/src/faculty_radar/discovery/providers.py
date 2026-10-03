"""External discovery providers: OpenAlex (primary) and Crossref (backfill).

The provider boundary is a tiny protocol on purpose: a future Semantic Scholar
provider only needs `name` and `search()`, and everything downstream keeps
working because it consumes plain OpenAlex-shaped payloads.

OpenAlex calls used (exactly one per uncached query):
  GET {base}/works?filter=title_and_abstract.search:<query>[,institutions.id:<scope>]
      &sort=cited_by_count:desc&per-page=<limit>&cursor=*

The institution filter restricts candidate works to in-scope affiliations,
which is what keeps the consent/institution rule intact in on-demand mode.
Sorting by citations surfaces the most established work first; the reranker
reorders by field relevance afterwards.

Crossref is used narrowly: when a discovered work arrives without a usable
title, its DOI is looked up once (cached) to backfill title/year/URL. It never
overwrites OpenAlex metadata and never blocks discovery when unreachable.
"""

from __future__ import annotations

from typing import Any, Protocol

import httpx

from faculty_radar.config import Settings, get_logger, get_settings
from faculty_radar.ingestion.cache import ResponseCache, make_cache_key
from faculty_radar.ingestion.client import OpenAlexClient
from faculty_radar.normalization.text import collapse_whitespace

logger = get_logger(__name__)

# Candidate-set size per query: enough for hybrid retrieval to choose from,
# small enough to stay fast. No bulk download, by construction.
DEFAULT_WORKS_LIMIT = 50

# Crossref politeness: a contact address joins the 50 req/s polite pool.
# Configured via FR_CROSSREF__MAILTO; unset works, just slower.


class DiscoveryProvider(Protocol):
    """Any source that can return OpenAlex-shaped work payloads for a query."""

    name: str

    def search(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        """Return up to `limit` raw work payloads, best first."""
        ...


def normalize_query(query: str) -> str:
    """Canonical form for cache keys: casefolded, whitespace-collapsed."""
    return collapse_whitespace(query or "").casefold()


class OpenAlexDiscoveryProvider:
    """Live OpenAlex topic discovery, optionally institution-scoped.

    When `institution_ids` is empty the search is global: no
    `institutions.id` filter is sent and candidates come from the whole
    OpenAlex universe. A non-empty scope (FR_SCOPE__INSTITUTION_IDS) keeps
    the PS23 institutional deployment mode, restricting candidates to
    in-scope affiliations.
    """

    name = "openalex"

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: OpenAlexClient | None = None,
        institution_ids: list[str] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or OpenAlexClient(self.settings.openalex)
        self.institution_ids = (
            institution_ids
            if institution_ids is not None
            else list(self.settings.scope.institution_ids)
        )
        if self.institution_ids:
            logger.info(
                "openalex discovery scoped to institutions",
                extra={"institution_ids": self.institution_ids},
            )
        else:
            logger.info("openalex discovery is global (no institution filter)")

    def search(self, query: str, *, limit: int = DEFAULT_WORKS_LIMIT) -> list[dict[str, Any]]:
        """One paginated works search; stops at `limit` without extra pages."""
        filters = [f"title_and_abstract.search:{query}"]
        if self.institution_ids:
            # OpenAlex OR-syntax keeps this a single request per page.
            scope = "|".join(f"institutions.id:{i}" for i in self.institution_ids)
            filters.append(scope)
        params = {
            "filter": ",".join(filters),
            "sort": "cited_by_count:desc",
            "select": (
                "id,doi,title,publication_year,publication_date,type,"
                "cited_by_count,abstract_inverted_index,authorships,topics,"
                "keywords,concepts,referenced_works,related_works,locations,is_retracted"
            ),
        }
        works: list[dict[str, Any]] = []
        try:
            for work in self.client.paginate("works", params, limit=limit):
                works.append(work)
        except Exception as exc:
            logger.warning("openalex discovery failed", extra={"error": str(exc)})
            return []
        logger.info(
            "openalex discovery complete",
            extra={"query": query, "works": len(works)},
        )
        return works


class CrossrefLookup:
    """Best-effort DOI verification and metadata backfill. Never raises.

    Two operations, one cached HTTP call each:
    * `lookup(doi)` - raw Crossref metadata for a DOI, or None on any failure.
    * `verify(doi, expected_title)` - does the DOI resolve, and does
      Crossref's title agree with the title OpenAlex supplied? Agreement is
      normalized containment either way, so subtitle and punctuation
      differences do not count as mismatches.

    Every failure mode (404, timeout, malformed JSON, unreachable host)
    returns None / `resolved=False`. Callers treat that as "unverified",
    never as "invalid" - OpenAlex data always wins ties.
    """

    name = "crossref"

    def __init__(
        self,
        cache: ResponseCache | None = None,
        *,
        http_client: httpx.Client | None = None,
        settings: Settings | None = None,
    ) -> None:
        resolved = settings or get_settings()
        self.settings = resolved.crossref
        self.cache = cache
        self._client = http_client or httpx.Client(timeout=self.settings.timeout_seconds)
        self._owns_client = http_client is None

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    def lookup(self, doi: str) -> dict[str, Any] | None:
        """Return Crossref metadata for a DOI, or None on any failure."""
        doi = (doi or "").strip()
        if not doi or not self.enabled:
            return None
        key = make_cache_key("CROSSREF", f"{self.settings.base_url}/works/{doi}", None)
        if self.cache is not None:
            cached = self.cache.get(key)
            if cached is not None:
                return cached
        try:
            response = self._client.get(
                f"{self.settings.base_url.rstrip('/')}/works/{doi}",
                params={"mailto": self.settings.mailto} if self.settings.mailto else None,
                headers={"User-Agent": _user_agent(self.settings.mailto)},
            )
            if response.status_code == 404:
                return None
            if response.is_error:
                return None
            message = response.json().get("message") or {}
        except Exception as exc:  # network, JSON, timeouts: all non-fatal here
            logger.debug("crossref lookup failed", extra={"doi": doi, "error": str(exc)})
            return None
        if self.cache is not None:
            self.cache.put(key, message)
        return message

    def verify(self, doi: str, expected_title: str | None) -> dict[str, Any]:
        """Check a DOI against Crossref and compare titles.

        Returns a small verdict dict; `resolved=False` means "could not
        confirm", never "proven fake".
        """
        message = self.lookup(doi)
        if not message:
            return {"resolved": False, "title_agrees": None}
        titles = [t for t in (message.get("title") or []) if t]
        crossref_title = titles[0] if titles else None
        agrees: bool | None = None
        if crossref_title and (expected_title or "").strip():
            left = _comparable_title(crossref_title)
            right = _comparable_title(expected_title or "")
            agrees = bool(left) and bool(right) and (left in right or right in left)
        journals = [j for j in (message.get("container-title") or []) if j]
        authors = message.get("author") or []
        return {
            "resolved": True,
            "title_agrees": agrees,
            "title": crossref_title,
            "year": _issued_year(message),
            "journal": journals[0] if journals else None,
            "url": message.get("URL"),
            "has_authors": bool(authors),
        }

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def _user_agent(mailto: str | None) -> str:
    contact = f" (mailto:{mailto})" if mailto else ""
    return f"faculty-radar/0.1{contact}"


def _comparable_title(title: str) -> str:
    """Lowercased alphanumeric-only form for agreement checks."""
    return "".join(ch for ch in title.casefold() if ch.isalnum())


def _issued_year(message: dict[str, Any]) -> int | None:
    parts = (message.get("issued") or {}).get("date-parts") or []
    if parts and parts[0]:
        try:
            return int(parts[0][0])
        except (ValueError, TypeError):
            return None
    for key in ("published-print", "published-online", "created"):
        parts = (message.get(key) or {}).get("date-parts") or []
        if parts and parts[0]:
            try:
                return int(parts[0][0])
            except (ValueError, TypeError):
                continue
    return None
