"""Raw author payload -> `NormalizedAuthor`.

Every field carries provenance, and no value is invented: a missing ORCID
stays None, and an absent affiliation list yields no institutions rather than a
placeholder. Normalization only reshapes data that the source actually
supplied.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from faculty_radar.models import (
    Affiliation,
    Institution,
    NormalizedAuthor,
    Provenance,
    Topic,
)
from faculty_radar.normalization.text import (
    collapse_whitespace,
    extract_orcid,
    normalize_ror,
    openalex_id,
)

SOURCE = "openalex"


def normalize_institution(payload: dict[str, Any] | None) -> Institution | None:
    """Build an Institution, deduplicating on the OpenAlex id when present."""
    if not payload:
        return None
    name = collapse_whitespace(payload.get("display_name") or "")
    if not name and not payload.get("id"):
        return None
    return Institution(
        id=openalex_id(str(payload["id"])) if payload.get("id") else None,
        name=name or "Unknown institution",
        ror=normalize_ror(payload.get("ror")),
        country_code=payload.get("country_code"),
        type=payload.get("type"),
    )


def normalize_affiliation(payload: dict[str, Any] | None) -> Affiliation | None:
    """Build a per-work Affiliation from an OpenAlex authorship affiliation."""
    if not payload:
        return None
    institution = normalize_institution(payload)
    if institution is None:
        return None
    return Affiliation(
        institution=institution,
        raw_string=collapse_whitespace(payload.get("raw_affiliation_string") or "") or None,
        is_primary=bool(payload.get("is_primary", False)),
        country_code=payload.get("country_code"),
        type=payload.get("type"),
    )


def normalize_topics(payloads: list[dict[str, Any]] | None) -> list[Topic]:
    """Normalize and deduplicate topics, keeping the strongest share per topic."""
    best: dict[str, Topic] = {}
    for payload in payloads or []:
        name = collapse_whitespace(payload.get("display_name") or "")
        if not name:
            continue
        subfield = (payload.get("subfield") or {}).get("display_name")
        field = (payload.get("field") or {}).get("display_name")
        topic = Topic(
            id=openalex_id(str(payload["id"])) if payload.get("id") else None,
            name=name,
            subfield=collapse_whitespace(subfield) if subfield else None,
            field=collapse_whitespace(field) if field else None,
            share=float(payload.get("score") or 1.0),
        )
        existing = best.get(topic.key)
        if existing is None or topic.share > existing.share:
            best[topic.key] = topic
    return sorted(best.values(), key=lambda t: -t.share)


def normalize_affiliations(payloads: list[dict[str, Any]] | None) -> list[Affiliation]:
    """Normalize a list of affiliations, deduplicating on institution id."""
    seen: dict[str, Affiliation] = {}
    for payload in payloads or []:
        affiliation = normalize_affiliation(payload)
        if affiliation is None:
            continue
        key = affiliation.institution.id or affiliation.institution.name.casefold()
        current = seen.get(key)
        if current is None or (affiliation.is_primary and not current.is_primary):
            seen[key] = affiliation
    return list(seen.values())


def unique_institutions(affiliations: list[Affiliation]) -> list[Institution]:
    seen: dict[str, Institution] = {}
    for affiliation in affiliations:
        key = affiliation.institution.id or affiliation.institution.name.casefold()
        seen.setdefault(key, affiliation.institution)
    return list(seen.values())


def normalize_author(
    payload: dict[str, Any],
    *,
    raw_path: str | None = None,
    retrieved_at: datetime | None = None,
    source_url: str | None = None,
) -> NormalizedAuthor | None:
    """Normalize one raw author record.

    Returns None when the payload has no usable identifier, since an author
    without an OpenAlex id cannot be linked to anything and must not enter the
    pipeline as an untraceable row.

    Accepts both OpenAlex affiliation shapes: the `affiliations` list on the
    author record and the `last_known_institutions` list, which is what the live
    API actually returns for an author.
    """
    author_id = openalex_id(payload.get("id"))
    if not author_id:
        return None

    display_name = collapse_whitespace(payload.get("display_name") or "")
    name = collapse_whitespace(payload.get("display_name") or "") or author_id

    # Name variants are the cheapest non-identifying signal available to entity
    # resolution, so they are preserved verbatim as well as canonically keyed.
    variants: list[str] = []
    for raw in payload.get("display_name_alternatives") or []:
        variant = collapse_whitespace(raw or "")
        if variant and variant.casefold() != display_name.casefold():
            variants.append(variant)

    raw_affiliations = list(payload.get("affiliations") or [])
    if not raw_affiliations:
        # `last_known_institutions` entries have no is_primary/ type fields;
        # `normalize_institution` reads only the fields they do carry.
        raw_affiliations = [
            dict(inst, is_primary=index == 0, type=inst.get("type"))
            for index, inst in enumerate(payload.get("last_known_institutions") or [])
            if inst
        ]
    affiliations = normalize_affiliations(raw_affiliations)

    return NormalizedAuthor(
        openalex_id=author_id,
        name=name,
        display_name=display_name or None,
        orcid=extract_orcid(payload.get("orcid")),
        name_variants=variants,
        affiliations=affiliations,
        institutions=unique_institutions(affiliations),
        topics=normalize_topics(payload.get("topics")),
        works_count=int(payload.get("works_count") or 0),
        cited_by_count=int(payload.get("cited_by_count") or 0),
        h_index=(payload.get("summary_stats") or {}).get("h_index"),
        provenance=Provenance.from_payload(
            SOURCE,
            author_id,
            payload,
            source_url=source_url or payload.get("id"),
            raw_path=raw_path,
            retrieved_at=retrieved_at,
        ),
    )


def normalize_authors(
    payloads: list[dict[str, Any]],
    *,
    raw_path: str | None = None,
    retrieved_at: datetime | None = None,
) -> list[NormalizedAuthor]:
    """Normalize many authors, dropping unusable records and deduplicating by id."""
    by_id: dict[str, NormalizedAuthor] = {}
    for payload in payloads:
        author = normalize_author(payload, raw_path=raw_path, retrieved_at=retrieved_at)
        if author is None:
            continue
        # First writer wins: the store is append-only, so the earliest snapshot
        # is the one we treat as authoritative.
        by_id.setdefault(author.openalex_id, author)
    return list(by_id.values())
