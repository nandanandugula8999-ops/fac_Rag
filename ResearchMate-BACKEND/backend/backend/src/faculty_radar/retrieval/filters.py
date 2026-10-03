"""Shared retrieval filters.

Filters narrow the candidate set before scoring. They are intentionally boring
equality and range checks: a faculty, institution, year, document-type, or
stated-evidence constraint must never change a score, only decide which
documents are eligible to receive one.
"""

from __future__ import annotations

from dataclasses import dataclass

from faculty_radar.models import CorpusDocument, DocumentType


@dataclass(frozen=True)
class SearchFilters:
    faculty_ids: tuple[str, ...] = ()
    institution_ids: tuple[str, ...] = ()
    document_types: tuple[DocumentType, ...] = ()
    year_min: int | None = None
    year_max: int | None = None
    stated_only: bool = False


def apply_filters(
    documents: list[CorpusDocument], filters: SearchFilters | None
) -> list[CorpusDocument]:
    """Return eligible documents in their input order."""
    if filters is None:
        return list(documents)

    selected: list[CorpusDocument] = []
    for doc in documents:
        if filters.faculty_ids and doc.faculty_id not in filters.faculty_ids:
            continue
        if filters.institution_ids and doc.institution_id not in filters.institution_ids:
            continue
        if filters.document_types and doc.document_type not in filters.document_types:
            continue
        if filters.year_min is not None and (doc.year or 0) < filters.year_min:
            continue
        if filters.year_max is not None and (doc.year is None or doc.year > filters.year_max):
            continue
        if filters.stated_only and not doc.is_stated:
            continue
        selected.append(doc)
    return selected
