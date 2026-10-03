"""Deterministic faculty and publication chunk construction.

The corpus is intentionally coarse: one document per faculty-publication link
and one document per faculty profile. A publication is never split into
windows here, so a citation can always be traced to exactly one whole work for
one faculty member.

Co-authored works therefore appear once per consented owner. That duplication
is not an error; each document carries the faculty owner that its chunk may be
used to support. An unconsented co-author gets no document and contributes no
text.

Only consented profiles enter the corpus. Inputs are sorted before output, so
the same profiles and works always produce the same documents in the same
order.
"""

from __future__ import annotations

from faculty_radar.config import Settings, get_logger, get_settings
from faculty_radar.corpus.store import CorpusStore
from faculty_radar.models import (
    CorpusDocument,
    DocumentType,
    FacultyProfile,
    Institution,
    NormalizedWork,
)
from faculty_radar.paths import DataPaths, build_paths

logger = get_logger(__name__)


def _primary_institution_id(institutions: list[Institution]) -> str | None:
    """Use the first institution as the document owner's institution.

    Corpus metadata needs one stable institution identifier. The first profile
    institution is deterministic and identifies the owner on whose behalf the
    chunk may be retrieved; it does not claim that every co-author shares that
    affiliation.
    """
    for institution in institutions:
        identifier = institution.id or institution.name
        if identifier:
            return identifier
    return None


def _latest_publication_year(profile: FacultyProfile) -> int | None:
    """Latest linked-publication year, or None for undated profiles."""
    years = profile.publication_years()
    return max(years) if years else None


class CorpusBuilder:
    """Builds whole-publication and faculty-profile corpus documents."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def build_profile_chunk(self, profile: FacultyProfile) -> CorpusDocument | None:
        """Build one faculty-profile chunk, or None without consent."""
        if not profile.consented:
            return None

        institution_names = [i.name for i in profile.institutions if i.name]
        stated_topics = [t.name for t in profile.stated_topics if t.name]
        projects = [p for p in profile.stated_project_descriptions if p]
        is_stated = bool(stated_topics or projects)
        latest_year = _latest_publication_year(profile)

        sections = [f"Faculty profile: {profile.name}"]
        if institution_names:
            sections.append(f"Institution: {'; '.join(institution_names)}")
        if stated_topics:
            declared = "\n".join(f"- {topic}" for topic in stated_topics)
            sections.append(f"Declared research topics:\n{declared}")
        if projects:
            described = "\n".join(f"- {project}" for project in projects)
            sections.append(f"Project descriptions:\n{described}")
        if not is_stated:
            # A profile without declared expertise still needs a retrievable
            # identity document, but only from publication activity metadata.
            # Publication-derived topics and keywords stay out of this chunk.
            sections.append(f"Linked publications: {len(profile.publications)}")
            if latest_year is not None:
                sections.append(f"Latest publication year: {latest_year}")

        field_origins = {"name": "identity"}
        if institution_names:
            field_origins["institution"] = "identity"
        if stated_topics:
            field_origins["stated_topics"] = "stated"
        if projects:
            field_origins["project_descriptions"] = "stated"
        if latest_year is not None:
            field_origins["publication_activity"] = "derived"

        return CorpusDocument(
            doc_id=CorpusDocument.make_id(profile.faculty_id, None, DocumentType.FACULTY_PROFILE),
            text="\n\n".join(sections),
            document_type=DocumentType.FACULTY_PROFILE,
            faculty_id=profile.faculty_id,
            work_id=None,
            institution_id=_primary_institution_id(profile.institutions),
            year=latest_year,
            topics=stated_topics,
            keywords=[],
            source_url=profile.provenance.source_url,
            doi=None,
            field_origins=field_origins,
            is_stated=is_stated,
            provenance=profile.provenance,
        )

    def build_publication_chunk(
        self, profile: FacultyProfile, work: NormalizedWork
    ) -> CorpusDocument | None:
        """Build one whole-publication chunk, or None without consent."""
        if not profile.consented:
            return None

        topics = [t.name for t in work.topics if t.name]
        keywords = [k.name for k in work.keywords if k.name]
        sections: list[str] = []
        field_origins = {"topics": "publication", "keywords": "publication"}

        if work.title:
            sections.append(f"Title: {work.title}")
            field_origins["title"] = "publication"
        if work.abstract:
            sections.append(f"Abstract: {work.abstract}")
            field_origins["abstract"] = "publication"
        if not sections:
            # Keep one chunk per linked publication even when the source did
            # not supply retrievable prose. This fallback only restates
            # identifiers already carried as metadata.
            sections.append(f"OpenAlex work: {work.openalex_id}")
            field_origins["work_identifier"] = "publication"
            if work.doi:
                sections.append(f"DOI: {work.doi}")
                field_origins["doi"] = "publication"

        return CorpusDocument(
            doc_id=CorpusDocument.make_id(
                profile.faculty_id, work.openalex_id, DocumentType.PUBLICATION
            ),
            text="\n\n".join(sections),
            document_type=DocumentType.PUBLICATION,
            faculty_id=profile.faculty_id,
            work_id=work.openalex_id,
            institution_id=_primary_institution_id(profile.institutions),
            year=work.year,
            topics=topics,
            keywords=keywords,
            source_url=work.citation_url or work.provenance.source_url,
            doi=work.doi,
            field_origins=field_origins,
            is_stated=False,
            provenance=work.provenance,
        )

    def build(
        self, profiles: list[FacultyProfile], works: list[NormalizedWork]
    ) -> list[CorpusDocument]:
        """Build all corpus documents for consented profiles."""
        works_by_id = {work.openalex_id: work for work in works}
        documents: dict[str, CorpusDocument] = {}
        skipped_no_consent = 0
        missing_works = 0

        for profile in sorted(profiles, key=lambda p: p.faculty_id):
            if not profile.consented:
                skipped_no_consent += 1
                continue

            profile_chunk = self.build_profile_chunk(profile)
            if profile_chunk is not None:
                documents[profile_chunk.doc_id] = profile_chunk

            work_ids = sorted({p.work_id for p in profile.publications if p.work_id})
            for work_id in work_ids:
                work = works_by_id.get(work_id)
                if work is None:
                    # A linked publication missing from normalized works is a
                    # pipeline gap. Skip it loudly rather than emitting an
                    # uncitable document.
                    missing_works += 1
                    logger.warning(
                        "linked publication has no normalized work; skipping chunk",
                        extra={"faculty_id": profile.faculty_id, "work_id": work_id},
                    )
                    continue
                chunk = self.build_publication_chunk(profile, work)
                if chunk is not None:
                    documents[chunk.doc_id] = chunk

        ordered = [documents[doc_id] for doc_id in sorted(documents)]
        logger.info(
            "research corpus built",
            extra={
                "documents": len(ordered),
                "profiles": len(profiles),
                "skipped_no_consent": skipped_no_consent,
                "missing_works": missing_works,
                **corpus_stats(ordered),
            },
        )
        return ordered


def corpus_stats(documents: list[CorpusDocument]) -> dict[str, int]:
    """Counts by document type and stated/derived marking."""
    stats = {"documents": len(documents)}
    for doc_type in DocumentType:
        stats[f"{doc_type.value}_documents"] = sum(
            1 for doc in documents if doc.document_type is doc_type
        )
    stats["stated_documents"] = sum(1 for doc in documents if doc.is_stated)
    stats["derived_documents"] = sum(1 for doc in documents if not doc.is_stated)
    return stats


def build_corpus(
    profiles: list[FacultyProfile],
    works: list[NormalizedWork],
    settings: Settings | None = None,
    paths: DataPaths | None = None,
    *,
    store: bool = True,
) -> list[CorpusDocument]:
    """Build consented corpus documents and optionally persist them."""
    settings = settings or get_settings()
    paths = paths or build_paths(settings)

    documents = CorpusBuilder(settings).build(profiles, works)
    if store:
        CorpusStore(paths).write_documents(documents)
    return documents
