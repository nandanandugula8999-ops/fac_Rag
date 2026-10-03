"""Cached on-demand discovery and the payload-to-corpus adapter.

`DiscoveryService.discover()` is the only entry point the API needs: given a
free-text query it returns consented faculty profiles, normalized works, and
corpus documents ready for the unchanged `RagPipeline`. Results are cached by
normalized query + scope + limit with a 24h TTL, so repeats cost zero API
calls; only complete payload sets are cached, never partial failures.

The adapter reuses three pipeline stages verbatim instead of reimplementing
them:

* author groups become `NormalizedAuthor` records and go through the REAL
  `resolve_researchers` - same-ID merges, conflicting-ORCID separation, and
  the needs-review queue all apply, so duplicate names stay separate;
* an in-memory `ConsentRegistry` (every resolved researcher opted in, zero
  stated topics) feeds the REAL `link_faculty`, so the consent gate and
  link_method/link_confidence bookkeeping execute exactly as in corpus mode;
* `CorpusBuilder.build` makes the chunks, so stated/derived separation and
  provenance rules are identical.

Because no registry declares topics here, discovered profiles carry no stated
expertise. Every discovered match is therefore honestly labeled
EVIDENCE_BASED or INFERRED - STATED can only come from a curated registry.
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from faculty_radar.config import Settings, get_logger, get_settings
from faculty_radar.corpus.builder import CorpusBuilder
from faculty_radar.discovery.providers import (
    CrossrefLookup,
    DiscoveryProvider,
    OpenAlexDiscoveryProvider,
    normalize_query,
)
from faculty_radar.ingestion.cache import ResponseCache, make_cache_key
from faculty_radar.linking.builder import link_faculty
from faculty_radar.linking.consent import ConsentEntry, ConsentRegistry
from faculty_radar.models import (
    Affiliation,
    CorpusDocument,
    FacultyProfile,
    Institution,
    NormalizedAuthor,
    NormalizedWork,
    Provenance,
)
from faculty_radar.normalization.text import (
    collapse_whitespace,
    extract_orcid,
    openalex_id,
)
from faculty_radar.normalization.works import normalize_works
from faculty_radar.paths import DataPaths, build_paths
from faculty_radar.resolution.resolver import resolve_researchers

logger = get_logger(__name__)

# Discovery cache TTL: OpenAlex metadata changes slowly; a day keeps repeated
# demo searches free without serving stale science for long.
DISCOVERY_TTL_HOURS = 24


@dataclass(frozen=True)
class DiscoveryResult:
    """Everything the RAG pipeline needs, plus discovery transparency."""

    profiles: tuple[FacultyProfile, ...]
    works: tuple[NormalizedWork, ...]
    documents: tuple[CorpusDocument, ...]
    provider: str
    cached: bool
    works_retrieved: int
    api_calls: int
    crossref_checked: int = 0
    crossref_verified: int = 0
    crossref_enriched: int = 0
    crossref_mismatched: int = 0


@dataclass
class DiscoveryService:
    """On-demand candidate discovery with caching and stage reuse."""

    settings: Settings | None = None
    paths: DataPaths | None = None
    provider: DiscoveryProvider | None = None
    crossref: CrossrefLookup | None = None
    cache_dir: Path | None = None
    works_limit: int = 50

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()
        self.paths = self.paths or build_paths(self.settings)
        self.provider = self.provider or OpenAlexDiscoveryProvider(self.settings)
        cache_dir = self.cache_dir or (self.paths.cache / "discovery")
        self.cache = ResponseCache(cache_dir, ttl_hours=DISCOVERY_TTL_HOURS)
        if self.crossref is None:
            self.crossref = CrossrefLookup(
                ResponseCache(cache_dir / "crossref", ttl_hours=DISCOVERY_TTL_HOURS)
            )

    @property
    def scope_ids(self) -> list[str]:
        provider = self.provider
        if isinstance(provider, OpenAlexDiscoveryProvider):
            return list(provider.institution_ids)
        return list((self.settings or get_settings()).scope.institution_ids)

    def discover(self, query: str) -> DiscoveryResult:
        """Discover, adapt, and return RAG-ready inputs for one query."""
        normalized = normalize_query(query)
        if not normalized:
            return DiscoveryResult((), (), (), self.provider.name, False, 0, 0)

        key = make_cache_key(
            self.provider.name,
            normalized,
            {"scope": self.scope_ids, "limit": self.works_limit},
        )
        cached = self.cache.get(key)
        if cached is not None:
            logger.debug("discovery cache hit", extra={"query": normalized})
            return self._adapt(cached["works"], provider=self.provider.name, cached=True)

        before = getattr(self.provider, "client", None)
        requests_before = before.request_count if before is not None else 0
        payloads = self.provider.search(normalized, limit=self.works_limit)
        requests_made = before.request_count - requests_before if before is not None else 0
        # Only complete, usable result sets enter the cache.
        if payloads:
            self.cache.put(key, {"works": payloads})
        return self._adapt(
            payloads, provider=self.provider.name, cached=False, api_calls=requests_made
        )

    # ---------------------------------------------------------------- adapter

    def _adapt(
        self,
        payloads: list[dict[str, Any]],
        *,
        provider: str,
        cached: bool,
        api_calls: int = 0,
    ) -> DiscoveryResult:
        """Payloads -> Crossref check -> normalized resolution -> linked profiles."""
        works = normalize_works(payloads)
        if not works:
            return DiscoveryResult((), (), (), provider, cached, len(payloads), api_calls)

        works, crossref_stats = self._verify_and_enrich(works)
        authors = _group_authors(payloads, self.scope_ids)
        if not authors:
            return DiscoveryResult((), (), (), provider, cached, len(payloads), api_calls)

        works_by_author: dict[str, list[NormalizedWork]] = {}
        for work in works:
            for author_id in work.author_ids:
                works_by_author.setdefault(author_id, []).append(work)
        resolved = resolve_researchers(authors, works, self.settings, store=False)

        # On-demand consent: every resolved in-scope researcher is opted in by
        # the demo operator, with nothing stated. Production replaces this with
        # a curated registry; the gate itself still executes inside link_faculty.
        consent = ConsentRegistry(
            {
                researcher.researcher_id: ConsentEntry(
                    researcher_id=researcher.researcher_id,
                    consented=True,
                    reviewed_by="on-demand discovery: in-scope assumed consented",
                )
                for researcher in resolved.researchers
            },
            enforce=True,
        )
        profiles = link_faculty(
            resolved.researchers,
            authors,
            works,
            self.settings,
            consent=consent,
            store=False,
        )
        documents = CorpusBuilder(self.settings).build(profiles, works)
        logger.info(
            "discovery adapted",
            extra={
                "works": len(works),
                "researchers": len(resolved.researchers),
                "profiles": len(profiles),
                "documents": len(documents),
                **crossref_stats,
            },
        )
        return DiscoveryResult(
            profiles=tuple(profiles),
            works=tuple(works),
            documents=tuple(documents),
            provider=provider,
            cached=cached,
            works_retrieved=len(payloads),
            api_calls=api_calls,
            crossref_checked=crossref_stats["crossref_checked"],
            crossref_verified=crossref_stats["crossref_verified"],
            crossref_enriched=crossref_stats["crossref_enriched"],
            crossref_mismatched=crossref_stats["crossref_mismatched"],
        )

    def _verify_and_enrich(
        self, works: list[NormalizedWork]
    ) -> tuple[list[NormalizedWork], dict[str, int]]:
        """Verify every candidate DOI against Crossref and fill gaps.

        Runs concurrently (I/O-bound) with one cached call per DOI, so even a
        full 50-work candidate set checks in about a second. Outcomes:

        * verified   - DOI resolves and titles agree;
        * mismatched - DOI resolves but titles disagree (OpenAlex kept, flagged);
        * enriched   - Crossref filled a missing title, year, or landing URL;
        * everything else (no DOI, unresolvable, Crossref down) leaves the
          OpenAlex record untouched.

        `crossref=None` or `enabled=False` skips the whole step: OpenAlex-only.
        """
        stats = {
            "crossref_checked": 0,
            "crossref_verified": 0,
            "crossref_enriched": 0,
            "crossref_mismatched": 0,
        }
        if self.crossref is None or not self.crossref.enabled:
            return works, stats

        with ThreadPoolExecutor(max_workers=self.crossref.settings.max_workers) as pool:
            verdicts = list(
                pool.map(
                    lambda work: (work.openalex_id, _safe_verify(self.crossref, work)),
                    works,
                )
            )

        by_id = {work.openalex_id: work for work in works}
        enriched: list[NormalizedWork] = []
        for work_id, verdict in verdicts:
            work = by_id[work_id]
            if verdict is None:
                enriched.append(work)
                continue
            stats["crossref_checked"] += 1
            if not verdict["resolved"]:
                enriched.append(work)
                continue
            if verdict["title_agrees"] is True:
                stats["crossref_verified"] += 1
            elif verdict["title_agrees"] is False:
                stats["crossref_mismatched"] += 1
                logger.warning(
                    "crossref title disagrees with openalex; keeping openalex",
                    extra={"work_id": work_id, "doi": work.doi},
                )
            enriched.append(_enriched_work(work, verdict, stats))
        return enriched, stats


def _safe_verify(crossref, work: NormalizedWork) -> dict | None:
    """One Crossref verdict, or None when anything goes wrong.

    lookup() itself never raises, but this guards the whole call so a
    misbehaving lookup implementation can never take discovery down with it.
    """
    if not work.doi:
        return None
    try:
        return crossref.verify(work.doi, work.title)
    except Exception as exc:
        logger.warning(
            "crossref verification failed; keeping openalex record",
            extra={"work_id": work.openalex_id, "error": str(exc)},
        )
        return None


def _enriched_work(work: NormalizedWork, verdict: dict, stats: dict[str, int]) -> NormalizedWork:
    """Return a work with Crossref-filled gaps, or the original untouched.

    Only fills fields OpenAlex left empty - title, year, landing URL - and
    only from a resolved Crossref record. Revalidates through the model so a
    bad fill can never produce an invalid record (it would raise, loudly,
    rather than silently corrupt the corpus).
    """
    overrides: dict = {}
    if not work.title and verdict.get("title"):
        overrides["title"] = collapse_whitespace(str(verdict["title"]))
    if work.year is None and verdict.get("year") is not None:
        overrides["year"] = verdict["year"]
    if not work.locations and verdict.get("url"):
        from faculty_radar.models import OpenLocation

        overrides["locations"] = [OpenLocation(landing_page_url=verdict["url"])]
    if not overrides:
        return work
    stats["crossref_enriched"] += 1
    return NormalizedWork.model_validate({**work.model_dump(), **overrides})


def _group_authors(payloads: list[dict[str, Any]], scope_ids: list[str]) -> list[NormalizedAuthor]:
    """Group raw authorships by OpenAlex author ID, keeping in-scope authors.

    One group per author ID: the same ID across works is one candidate person
    (resolution merges them); different IDs are never merged here - the
    resolver decides same/different/needs-review from ORCID and evidence, so
    duplicate display names stay separate by construction.
    """
    scope = set(scope_ids)
    groups: dict[str, dict] = {}
    for payload in payloads:
        for authorship in payload.get("authorships") or []:
            raw = authorship.get("author") or {}
            author_id = openalex_id(raw.get("id"))
            if not author_id:
                continue
            institutions = [
                {
                    "id": openalex_id(inst.get("id")),
                    "name": collapse_whitespace(inst.get("display_name") or ""),
                    "ror": inst.get("ror"),
                    "country_code": inst.get("country_code"),
                    "type": inst.get("type"),
                }
                for inst in authorship.get("institutions") or []
            ]
            group = groups.setdefault(
                author_id,
                {"names": Counter(), "orcids": set(), "institutions": {}, "raw": []},
            )
            name = collapse_whitespace(raw.get("display_name") or "")
            if name:
                group["names"][name] += 1
            # Authorship ORCIDs arrive as URLs; normalize to bare IDs so the
            # resolver compares like with like.
            orcid = extract_orcid(raw.get("orcid") or "")
            if orcid:
                group["orcids"].add(orcid)
            for inst in institutions:
                if inst["id"] or inst["name"]:
                    group["institutions"][inst["id"] or inst["name"]] = inst
            group["raw"].append({"work": payload.get("id"), "author": raw})

    authors: list[NormalizedAuthor] = []
    for author_id, group in sorted(groups.items()):
        in_scope = {i["id"] for i in group["institutions"].values()} & scope
        if scope and not in_scope:
            continue  # consent/institution rule: out-of-scope authors get no profile
        if len(group["orcids"]) > 1:
            logger.warning(
                "author id carries conflicting ORCIDs; keeping first",
                extra={"author_id": author_id, "orcids": sorted(group["orcids"])},
            )
        institutions = [
            Institution(
                id=inst["id"],
                name=inst["name"] or "Unknown institution",
                ror=inst["ror"],
                country_code=inst["country_code"],
                type=inst["type"],
            )
            for inst in group["institutions"].values()
        ]
        canonical = group["names"].most_common(1)
        name = canonical[0][0] if canonical else author_id
        variants = [n for n, _ in group["names"].most_common() if n != name]
        authors.append(
            NormalizedAuthor(
                openalex_id=author_id,
                name=name,
                display_name=name,
                orcid=sorted(group["orcids"])[0] if group["orcids"] else None,
                name_variants=variants,
                affiliations=[
                    Affiliation(institution=inst, is_primary=False) for inst in institutions
                ],
                institutions=institutions,
                provenance=Provenance.from_payload(
                    "openalex",
                    author_id,
                    {"author_id": author_id, "authorships": group["raw"]},
                    source_url=f"https://openalex.org/{author_id}",
                ),
            )
        )
    return authors
