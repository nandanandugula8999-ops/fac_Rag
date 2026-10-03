"""Researcher entity resolution.

Stage 3 of the pipeline, and the reason duplicate-name handling is a
first-class feature rather than an afterthought.

Responsibilities:
  * cluster author records that refer to the same human being
  * disambiguate homonyms - "Wei Zhang" at two institutions is two people
  * merge papers under canonical researcher identities in `paths.processed`

Signals to combine: ORCID, institutional email domain, affiliation history,
co-author graph, topic signature, and name similarity. Every merge decision
must keep its supporting evidence so it can be reviewed and undone; a wrong
merge silently corrupts every downstream ranking.

The load-bearing rule: **two records are never merged on a name match alone.**
An exact name match is necessary but not sufficient, so it produces
`needs_review` rather than `same_person`. Submodules:

  matching  - individual evidence signals, each independently testable
  resolver  - signal combination into a verdict, plus clustering
"""

from faculty_radar.resolution.matching import (
    MatchSignals,
    institution_overlap,
    name_similarity,
    orcid_compatibility,
    publication_overlap,
    topic_similarity,
)
from faculty_radar.resolution.resolver import (
    ResearcherResolver,
    ResolutionReport,
    resolve_researchers,
)
from faculty_radar.resolution.store import ResolvedStore

__all__ = [
    "MatchSignals",
    "ResearcherResolver",
    "ResolutionReport",
    "ResolvedStore",
    "institution_overlap",
    "name_similarity",
    "orcid_compatibility",
    "publication_overlap",
    "resolve_researchers",
    "topic_similarity",
]
