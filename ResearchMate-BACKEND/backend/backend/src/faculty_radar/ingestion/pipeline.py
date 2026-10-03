"""Ingestion orchestration: institution -> authors -> works, into the raw store.

The whole stage is expressed against two collaborators - a source client and a
raw store - so tests substitute a fake client and never touch the network.

The contract of this stage is deliberately narrow: fetch, dedupe, store. No
cleaning, no interpretation, no merging. A record that reaches `raw/` is the
record the source returned.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from faculty_radar.config import IngestionSettings, Settings, get_logger, get_settings
from faculty_radar.ingestion.client import OpenAlexClient
from faculty_radar.ingestion.store import RawStore
from faculty_radar.paths import DataPaths, build_paths

logger = get_logger(__name__)


@dataclass
class IngestionResult:
    """What an ingestion run did. Reported, never assumed."""

    institutions: int = 0
    authors_fetched: int = 0
    authors_stored: int = 0
    works_fetched: int = 0
    works_stored: int = 0
    works_skipped: int = 0
    requests: int = 0
    cache_stats: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def stored_per_request(self) -> float:
        """Ingesting an already-populated corpus should approach zero new records."""
        if self.requests == 0:
            return 0.0
        total = self.authors_stored + self.works_stored
        return round(total / self.requests, 3)

    def as_dict(self) -> dict:
        data = asdict(self)
        data["stored_per_request"] = self.stored_per_request
        return data


def ingest_institution(
    client: OpenAlexClient,
    store: RawStore,
    institution_id: str,
    settings: IngestionSettings | None = None,
) -> IngestionResult:
    """Fetch every author at an institution and their works into `raw/`."""
    settings = settings or IngestionSettings()
    result = IngestionResult(institutions=1)

    logger.info(
        "ingesting institution",
        extra={"institution_id": institution_id, "max_authors": settings.max_authors},
    )

    try:
        institution = client.get_institution(institution_id)
    except Exception as exc:
        message = f"institution {institution_id}: {exc}"
        logger.error(
            "institution fetch failed", extra={"institution_id": institution_id, "error": str(exc)}
        )
        result.errors.append(message)
        return result

    store.append("institution", institution)
    source_url = institution.get("id")

    # Pass 1: collect author payloads first, so the work budget can be shared
    # evenly rather than letting the first author consume the whole quota.
    authors: list[dict] = []
    for author in client.iter_authors(institution_id, limit=settings.max_authors):
        result.authors_fetched += 1
        if store.append("author", author, source_url=author.get("id")):
            result.authors_stored += 1
        authors.append(author)

    if not authors:
        logger.warning("institution returned no authors", extra={"institution_id": institution_id})
        return result

    per_author = max(1, settings.max_works_total // len(authors))
    per_author = min(per_author, settings.max_works_per_author)

    logger.info(
        "ingesting works",
        extra={"authors": len(authors), "max_works_per_author": per_author},
    )

    seen_works: set[str] = set()
    for author in authors:
        author_id = author.get("id")
        if not author_id:
            continue
        try:
            for work in client.iter_works(author_id, limit=per_author):
                result.works_fetched += 1
                work_id = str(work.get("id") or "")
                if work_id and work_id in seen_works:
                    # The same work surfaces once per co-author; store it once.
                    result.works_skipped += 1
                    continue
                if settings.require_abstract and not work.get("abstract_inverted_index"):
                    result.works_skipped += 1
                    continue
                if store.append("work", work, source_url=source_url or work.get("id")):
                    result.works_stored += 1
                if work_id:
                    seen_works.add(work_id)
        except Exception as exc:
            message = f"author {author_id}: {exc}"
            logger.warning(
                "author work fetch failed", extra={"author_id": author_id, "error": str(exc)}
            )
            result.errors.append(message)
            continue

    logger.info(
        "institution ingestion complete",
        extra={"institution_id": institution_id, **result.as_dict()},
    )
    return result


def ingest_all(
    client: OpenAlexClient | None = None,
    store: RawStore | None = None,
    settings: Settings | None = None,
    paths: DataPaths | None = None,
    *,
    institution_ids: list[str] | None = None,
) -> IngestionResult:
    """Ingest every institution in scope. Falls back to the fixture-free default."""
    settings = settings or get_settings()
    owns_client = client is None
    client = client or OpenAlexClient(settings.openalex)
    store = store or RawStore(paths or build_paths(settings))

    scope_ids = institution_ids if institution_ids is not None else settings.scope.institution_ids
    if not scope_ids:
        logger.warning("no institutions configured; nothing to ingest")
        return IngestionResult(errors=["scope.institution_ids is empty"])

    total = IngestionResult()
    for institution_id in scope_ids:
        result = ingest_institution(client, store, institution_id, settings.ingestion)
        total.institutions += result.institutions
        total.authors_fetched += result.authors_fetched
        total.authors_stored += result.authors_stored
        total.works_fetched += result.works_fetched
        total.works_stored += result.works_stored
        total.works_skipped += result.works_skipped
        total.errors.extend(result.errors)

    total.requests = client.request_count
    if client.cache is not None:
        total.cache_stats = client.cache.get_stats()

    logger.info("ingestion complete", extra=total.as_dict())
    if owns_client:
        client.close()
    return total
