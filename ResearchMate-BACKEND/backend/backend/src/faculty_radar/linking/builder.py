"""Building faculty profiles with linked publications.

A `FacultyProfile` is the unit the rest of the engine reasons about. Two things
about it matter:

  * every publication edge carries `link_method` and `link_confidence`, so a
    reader can tell an authorship claim from OpenAlex (high confidence) apart
    from a name-based guess (low confidence)
  * STATED expertise comes only from the consent registry, never from the
    derived topic list. OpenAlex author topics are computed from a person's
    publications, so presenting them as self-declared would misreport them.
"""

from __future__ import annotations

from faculty_radar.config import Settings, get_logger, get_settings
from faculty_radar.linking.consent import ConsentRegistry, load_consent_registry
from faculty_radar.models import (
    CanonicalResearcher,
    FacultyProfile,
    Institution,
    LinkedPublication,
    NormalizedAuthor,
    NormalizedWork,
    Provenance,
)
from faculty_radar.paths import DataPaths, build_paths

logger = get_logger(__name__)

# How each publication reached a faculty profile, and how much to trust it.
LINK_METHODS: dict[str, float] = {
    # OpenAlex asserted this author wrote this work. Strongest available.
    "openalex_authorship": 1.0,
    # Matched on the ORCID attached to the authorship.
    "orcid_authorship": 0.98,
    # Matched through a researcher identity that was already resolved.
    "resolved_researcher": 0.90,
    # Matched on name only. Recorded, flagged, and never used silently.
    "name_match_unverified": 0.45,
}


class FacultyLinker:
    """Turns resolved researchers and works into consented faculty profiles."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        consent: ConsentRegistry | None = None,
        min_link_confidence: float = 0.5,
    ) -> None:
        self.settings = settings or get_settings()
        self.consent = consent if consent is not None else load_consent_registry(self.settings)
        # Below this, a link is recorded as dropped rather than silently trusted.
        self.min_link_confidence = min_link_confidence

    def build_profile(
        self,
        researcher: CanonicalResearcher,
        authors_by_id: dict[str, NormalizedAuthor],
        works_by_id: dict[str, NormalizedWork],
    ) -> FacultyProfile | None:
        """Build one profile, or None when consent is absent.

        Returning None is the whole consent mechanism: an absent profile cannot
        be indexed, retrieved, ranked, or cited.
        """
        if not self.consent.is_consented(researcher.researcher_id):
            return None

        publications = self._linked_publications(researcher, authors_by_id, works_by_id)
        stated_topics = self.consent.stated_topics(researcher.researcher_id)

        return FacultyProfile(
            faculty_id=researcher.researcher_id,
            name=researcher.canonical_name,
            orcid=researcher.orcid,
            researcher_id=researcher.researcher_id,
            institutions=researcher.institutions,
            stated_topics=stated_topics,
            stated_project_descriptions=self.consent.project_descriptions(researcher.researcher_id),
            publications=publications,
            cited_by_count=researcher.cited_by_count,
            consented=True,
            provenance=Provenance(
                source="openalex+consent_registry",
                source_id=researcher.researcher_id,
                source_url=f"https://openalex.org/{researcher.researcher_id}",
            ),
        )

    def _linked_publications(
        self,
        researcher: CanonicalResearcher,
        authors_by_id: dict[str, NormalizedAuthor],
        works_by_id: dict[str, NormalizedWork],
    ) -> list[LinkedPublication]:
        """Link each work the researcher authored, recording how the link was made."""
        member_ids = set(researcher.openalex_ids)
        linked: list[LinkedPublication] = []

        for work_id in researcher.work_ids:
            work = works_by_id.get(work_id)
            if work is None:
                continue
            match = self._match_authorship(work, researcher, member_ids, authors_by_id)
            if match is None:
                continue
            authorship, method = match
            confidence = LINK_METHODS[method]
            if confidence < self.min_link_confidence:
                logger.debug(
                    "dropping low-confidence faculty-publication link",
                    extra={
                        "faculty_id": researcher.researcher_id,
                        "work_id": work_id,
                        "method": method,
                    },
                )
                continue
            linked.append(
                LinkedPublication(
                    work_id=work.openalex_id,
                    faculty_id=researcher.researcher_id,
                    link_method=method,
                    link_confidence=confidence,
                    author_position=authorship.author_position,
                    year=work.year,
                    title=work.title,
                    doi=work.doi,
                    citation_url=work.citation_url,
                    is_open_access=bool(work.best_oa_url),
                )
            )

        # Newest first: recency signals and trend analysis both depend on it.
        return sorted(
            linked,
            key=lambda p: (-(p.year or 0), p.work_id),
        )

    def _match_authorship(
        self,
        work: NormalizedWork,
        researcher: CanonicalResearcher,
        member_ids: set[str],
        authors_by_id: dict[str, NormalizedAuthor],
    ):
        """Find the authorship connecting this work to this researcher."""
        for authorship in work.authorships:
            author_id = authorship.raw_author_id
            if not author_id:
                continue
            if author_id in member_ids:
                return authorship, "openalex_authorship"
            member = authors_by_id.get(author_id)
            if member and researcher.orcid and member.orcid == researcher.orcid:
                return authorship, "orcid_authorship"
        return None


def link_faculty(
    researchers: list[CanonicalResearcher],
    authors: list[NormalizedAuthor],
    works: list[NormalizedWork],
    settings: Settings | None = None,
    paths: DataPaths | None = None,
    *,
    consent: ConsentRegistry | None = None,
    store: bool = True,
) -> list[FacultyProfile]:
    """Link consented faculty to their publications and return the profiles."""
    settings = settings or get_settings()
    paths = paths or build_paths(settings)

    authors_by_id = {a.openalex_id: a for a in authors}
    works_by_id = {w.openalex_id: w for w in works}
    linker = FacultyLinker(settings, consent=consent)

    profiles: list[FacultyProfile] = []
    skipped = 0
    for researcher in researchers:
        profile = linker.build_profile(researcher, authors_by_id, works_by_id)
        if profile is None:
            skipped += 1
            continue
        profiles.append(profile)

    profiles.sort(key=lambda p: (-len(p.publications), p.faculty_id))
    logger.info(
        "faculty linking complete",
        extra={
            "profiles": len(profiles),
            "skipped_no_consent": skipped,
            "publications_linked": sum(len(p.publications) for p in profiles),
        },
    )

    if store:
        from faculty_radar.linking.store import FacultyStore

        FacultyStore(paths).write_profiles(profiles)
        FacultyStore(paths).write_institutions(_institution_summary(profiles))
    return profiles


def _institution_summary(profiles: list[FacultyProfile]) -> dict[str, Institution]:
    seen: dict[str, Institution] = {}
    for profile in profiles:
        for institution in profile.institutions:
            seen.setdefault(institution.id or institution.name, institution)
    return seen
