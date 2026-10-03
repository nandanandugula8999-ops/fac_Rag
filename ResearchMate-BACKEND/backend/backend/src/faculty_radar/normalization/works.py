"""Raw work payload -> `NormalizedWork`.

The abstract is reconstructed from the inverted index (see
`normalization.abstract`), identifiers are canonicalized, and every list is
deduplicated. Nothing is inferred: a work with no title keeps `title=None`
rather than being given its DOI as a stand-in.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from faculty_radar.models import (
    Authorship,
    Concept,
    Keyword,
    NormalizedWork,
    OpenLocation,
    Provenance,
)
from faculty_radar.normalization.abstract import reconstruct_abstract
from faculty_radar.normalization.authors import (
    normalize_affiliation,
    normalize_topics,
    unique_institutions,
)
from faculty_radar.normalization.text import (
    collapse_whitespace,
    normalize_doi,
    normalize_title,
    openalex_id,
)

SOURCE = "openalex"


def _parse_date(value: Any) -> date | None:
    """Parse an ISO-ish date. Returns None rather than an epoch fallback."""
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            parsed = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        return parsed
    return None


def normalize_authorship(payload: dict[str, Any]) -> Authorship:
    """One authorship entry, with its per-work affiliation preserved."""
    nested_author = payload.get("author") or {}
    return Authorship(
        author_position=collapse_whitespace(payload.get("author_position") or "") or None,
        is_corresponding=bool(payload.get("is_corresponding", False)),
        affiliation=normalize_affiliation(payload.get("affiliation"))
        or _affiliation_from_legacy(payload),
        # Live OpenAlex nests the id under `author`; older snapshots carried
        # a top-level `raw_author_id`. Both spellings resolve to one identity.
        raw_author_id=openalex_id(payload.get("raw_author_id") or nested_author.get("id")),
    )


def _affiliation_from_legacy(payload: dict[str, Any]):
    """Older OpenAlex shapes put institutions directly on the authorship."""
    institutions = payload.get("institutions") or []
    if not institutions:
        return None
    from faculty_radar.normalization.authors import normalize_institution

    institution = normalize_institution(institutions[0])
    if institution is None:
        return None
    from faculty_radar.models import Affiliation

    raw = payload.get("raw_affiliation_strings") or []
    return Affiliation(
        institution=institution,
        raw_string=collapse_whitespace(raw[0]) if raw else None,
        is_primary=True,
        country_code=institution.country_code,
        type="education",
    )


def normalize_keywords(payloads: list[dict[str, Any]] | None) -> list[Keyword]:
    seen: dict[str, Keyword] = {}
    for payload in payloads or []:
        name = collapse_whitespace(payload.get("display_name") or "")
        if not name:
            continue
        keyword = Keyword(
            id=openalex_id(str(payload["id"])) if payload.get("id") else None,
            name=name,
            score=float(payload["score"]) if payload.get("score") is not None else None,
        )
        existing = seen.get(name.casefold())
        if existing is None or (keyword.score or 0) > (existing.score or 0):
            seen[name.casefold()] = keyword
    return sorted(seen.values(), key=lambda k: -(k.score or 0.0))


def normalize_concepts(payloads: list[dict[str, Any]] | None) -> list[Concept]:
    seen: dict[str, Concept] = {}
    for payload in payloads or []:
        name = collapse_whitespace(payload.get("display_name") or "")
        if not name:
            continue
        concept = Concept(
            id=openalex_id(str(payload["id"])) if payload.get("id") else None,
            name=name,
            level=int(payload["level"]) if payload.get("level") is not None else None,
            score=float(payload["score"]) if payload.get("score") is not None else None,
        )
        existing = seen.get(name.casefold())
        if existing is None or (concept.score or 0) > (existing.score or 0):
            seen[name.casefold()] = concept
    return sorted(seen.values(), key=lambda c: -(c.score or 0.0))


def normalize_locations(payloads: list[dict[str, Any]] | None) -> list[OpenLocation]:
    seen: dict[tuple, OpenLocation] = {}
    for payload in payloads or []:
        landing = payload.get("landing_page_url") or None
        pdf = payload.get("pdf_url") or None
        if not landing and not pdf:
            continue
        location = OpenLocation(
            landing_page_url=landing,
            pdf_url=pdf,
            is_oa=bool(payload.get("is_oa", False)),
            oa_status=payload.get("oa_status"),
            version=payload.get("version"),
            license=payload.get("license"),
        )
        seen.setdefault((landing, pdf), location)
    return list(seen.values())


def normalize_work(
    payload: dict[str, Any],
    *,
    raw_path: str | None = None,
    retrieved_at: datetime | None = None,
    source_url: str | None = None,
) -> NormalizedWork | None:
    """Normalize one raw work record, or None if it has no usable identifier."""
    work_id = openalex_id(payload.get("id"))
    if not work_id:
        return None

    authorships = [normalize_authorship(a) for a in payload.get("authorships") or []]
    institutions = unique_institutions(
        [a.affiliation for a in authorships if a.affiliation is not None]
    )

    doi = normalize_doi(payload.get("doi"))
    year_raw = payload.get("publication_year")
    published = _parse_date(payload.get("publication_date"))

    return NormalizedWork(
        openalex_id=work_id,
        title=normalize_title(payload.get("title")),
        doi=doi,
        year=int(year_raw) if year_raw is not None else None,
        publication_date=published,
        abstract=reconstruct_abstract(payload.get("abstract_inverted_index")),
        type=collapse_whitespace(payload.get("type") or "") or None,
        is_retracted=bool(payload.get("is_retracted", False)),
        is_paratext=bool(payload.get("is_paratext", False)),
        authorships=authorships,
        institutions=institutions,
        topics=normalize_topics(payload.get("topics")),
        keywords=normalize_keywords(payload.get("keywords")),
        concepts=normalize_concepts(payload.get("concepts")),
        referenced_work_ids=sorted(
            {i for i in (openalex_id(w) for w in payload.get("referenced_works") or []) if i}
        ),
        related_work_ids=sorted(
            {i for i in (openalex_id(w) for w in payload.get("related_works") or []) if i}
        ),
        locations=normalize_locations(payload.get("locations")),
        cited_by_count=int(payload.get("cited_by_count") or 0),
        provenance=Provenance.from_payload(
            SOURCE,
            work_id,
            payload,
            source_url=source_url or payload.get("doi") or payload.get("id"),
            raw_path=raw_path,
            retrieved_at=retrieved_at,
        ),
    )


def normalize_works(
    payloads: list[dict[str, Any]],
    *,
    raw_path: str | None = None,
    retrieved_at: datetime | None = None,
) -> list[NormalizedWork]:
    """Normalize many works, deduplicating by id."""
    by_id: dict[str, NormalizedWork] = {}
    for payload in payloads:
        work = normalize_work(payload, raw_path=raw_path, retrieved_at=retrieved_at)
        if work is None:
            continue
        by_id.setdefault(work.openalex_id, work)
    return list(by_id.values())
