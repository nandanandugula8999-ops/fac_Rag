"""Existing and potential collaboration detection over the knowledge graph.

Shared authorship is the only evidence accepted for an EXISTING collaboration.
Topic overlap proposes POTENTIAL collaborations, graded by how the pair's
topic sets relate:

* overlap at or below `complementarity_threshold` -> complementary expertise:
  the two publish in different areas with a bridge between them
* overlap above `complementarity_threshold` but below `same_area_threshold` ->
  adjacent expertise: related areas, possible overlap in methods or problems
* overlap at or above `same_area_threshold` -> near-duplicates: not proposed,
  since introducing two people who do the same thing is rarely useful and the
  overlap itself is usually a data artifact (e.g. a mega-topic like
  "Artificial Intelligence")

Scores are normalized within each type so EXISTING and POTENTIAL pairs can be
shown side by side without implying they are equally certain.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from faculty_radar.config import Settings, get_logger, get_settings
from faculty_radar.graph.builder import faculty_node_id
from faculty_radar.graph.queries import GraphQueries
from faculty_radar.models import (
    CollaborationPair,
    CollaborationReport,
    CollaborationType,
    DocumentType,
    EvidenceItem,
    ExpertiseType,
    FacultyProfile,
    NormalizedWork,
    RankingSignal,
    Status,
)

logger = get_logger(__name__)


@dataclass
class CollaborationEngine:
    """Detects collaborations from graph structure and publication topics."""

    profiles: list[FacultyProfile]
    works: list[NormalizedWork]
    queries: GraphQueries
    settings: Settings | None = None
    by_profile: dict[str, FacultyProfile] = field(init=False)
    works_by_id: dict[str, NormalizedWork] = field(init=False)

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()
        self.by_profile = {p.faculty_id: p for p in self.profiles if p.consented}
        self.works_by_id = {w.openalex_id: w for w in self.works}

    def find_collaborations(
        self, faculty_id: str | None = None, *, top_k: int | None = None
    ) -> CollaborationReport:
        """Find existing and potential collaborations, optionally for one person."""
        settings = self.settings or get_settings()
        limit = settings.collaboration.max_pairs if top_k is None else top_k
        if limit <= 0:
            return CollaborationReport(query_faculty_id=faculty_id, pairs=[], status=Status.OK)
        if faculty_id is not None and faculty_id not in self.by_profile:
            return CollaborationReport(
                query_faculty_id=faculty_id, pairs=[], status=Status.INSUFFICIENT_EVIDENCE
            )

        people = sorted(self.by_profile)
        if faculty_id is not None:
            candidates = [(faculty_id, other) for other in people if other != faculty_id]
        else:
            candidates = [
                (left, right) for i, left in enumerate(people) for right in people[i + 1 :]
            ]

        existing: list[CollaborationPair] = []
        potential: list[CollaborationPair] = []
        for left, right in candidates:
            shared = self.queries.shared_works(faculty_node_id(left), faculty_node_id(right))
            shared_ids = sorted(node_id.split(":", 1)[1] for node_id in shared if ":" in node_id)
            if len(shared_ids) >= settings.collaboration.min_coauthored_works:
                existing.append(self._existing_pair(left, right, shared_ids, settings))
                continue
            pair = self._potential_pair(left, right, settings)
            if pair is not None:
                potential.append(pair)

        _normalize_scores(existing)
        _normalize_scores(potential)
        pairs = sorted([*existing, *potential], key=lambda p: (-p.score, p.faculty_a, p.faculty_b))[
            :limit
        ]
        report = CollaborationReport(query_faculty_id=faculty_id, pairs=pairs, status=Status.OK)
        logger.debug(
            "collaboration detection complete",
            extra={
                "faculty_id": faculty_id,
                "existing": len(existing),
                "potential": len(potential),
            },
        )
        return report

    # ------------------------------------------------------------------
    # Pair constructors
    # ------------------------------------------------------------------

    def _existing_pair(
        self, left: str, right: str, shared_ids: list[str], settings: Settings
    ) -> CollaborationPair:
        left_profile = self.by_profile[left]
        right_profile = self.by_profile[right]
        shared_topics = self._shared_topic_names(left, right)
        overlap = self._topic_overlap(left, right)
        years = [
            self.works_by_id[w].year
            for w in shared_ids
            if w in self.works_by_id and self.works_by_id[w].year is not None
        ]
        present_years = [w.year for w in self.works_by_id.values() if w.year is not None]
        present = max(present_years) if present_years else None
        latest = max(years) if years else None
        fresh = latest is not None and present is not None and latest >= present - 2
        evidence = [
            EvidenceItem(
                evidence_id=f"collab:{left}:{right}:{work_id}",
                faculty_id=left,
                work_id=work_id,
                doc_id=None,
                quote=self._work_quote(work_id),
                title=self._work_title(work_id),
                authors=[],
                year=self.works_by_id[work_id].year if work_id in self.works_by_id else None,
                venue=None,
                doi=self.works_by_id[work_id].doi if work_id in self.works_by_id else None,
                source_url=self._work_url(work_id),
                source_type=DocumentType.PUBLICATION,
                relevance=1.0,
                expertise_type=ExpertiseType.EVIDENCE_BASED,
            )
            for work_id in shared_ids
        ]
        notes = [f"co-authored {len(shared_ids)} work(s)"]
        if self._cross_institution(left, right):
            notes.append("collaboration spans institutional boundaries")
        return CollaborationPair(
            faculty_a=left,
            faculty_b=right,
            faculty_a_name=left_profile.name,
            faculty_b_name=right_profile.name,
            collaboration_type=CollaborationType.EXISTING,
            score=float(len(shared_ids)),
            shared_work_ids=shared_ids,
            shared_topics=shared_topics,
            topic_overlap=overlap,
            signals=[
                RankingSignal(
                    name="shared_works",
                    value=min(1.0, len(shared_ids) / 5),
                    weight=1.0,
                    contribution=len(shared_ids),
                    explanation=f"{len(shared_ids)} shared authored work(s)",
                ),
                RankingSignal(
                    name="latest_shared_year",
                    value=1.0 if fresh else 0.5,
                    weight=0.3,
                    contribution=0.3 if fresh else 0.15,
                    explanation=f"latest shared work in {latest}"
                    if latest is not None
                    else "shared works are undated",
                ),
            ],
            evidence=evidence,
            notes=notes,
        )

    def _potential_pair(
        self, left: str, right: str, settings: Settings
    ) -> CollaborationPair | None:
        overlap = self._topic_overlap(left, right)
        if overlap <= 0 or overlap >= settings.collaboration.same_area_threshold:
            return None
        left_profile = self.by_profile[left]
        right_profile = self.by_profile[right]
        shared_topics = self._shared_topic_names(left, right)
        if overlap <= settings.collaboration.complementarity_threshold:
            note = "complementary expertise: adjacent areas with a bridge between them"
        else:
            note = "adjacent expertise: related areas, possibly shared methods"
        notes = [note]
        if self._cross_institution(left, right):
            notes.append("potential collaboration spans institutional boundaries")
        evidence = [
            EvidenceItem(
                evidence_id=f"collab:{left}:{right}:topic:{topic}",
                faculty_id=left,
                work_id=None,
                doc_id=None,
                quote=f"Both {left_profile.name} and {right_profile.name} publish on {topic}.",
                title=None,
                authors=[],
                year=None,
                venue=None,
                doi=None,
                source_url=None,
                source_type=DocumentType.PUBLICATION,
                relevance=overlap,
                expertise_type=ExpertiseType.INFERRED,
            )
            for topic in shared_topics
        ]
        return CollaborationPair(
            faculty_a=left,
            faculty_b=right,
            faculty_a_name=left_profile.name,
            faculty_b_name=right_profile.name,
            collaboration_type=CollaborationType.POTENTIAL,
            score=overlap,
            shared_work_ids=[],
            shared_topics=shared_topics,
            topic_overlap=overlap,
            signals=[
                RankingSignal(
                    name="topic_overlap",
                    value=overlap,
                    weight=1.0,
                    contribution=overlap,
                    explanation=(
                        f"topic Jaccard overlap {overlap:.2f} "
                        f"on {len(shared_topics)} shared topic(s)"
                    ),
                ),
            ],
            evidence=evidence,
            notes=notes,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _person_topics(self, faculty_id: str) -> set[str]:
        return {topic.id for topic in self.queries.topics_for_faculty(faculty_node_id(faculty_id))}

    def _topic_overlap(self, left: str, right: str) -> float:
        left_topics = self._person_topics(left)
        right_topics = self._person_topics(right)
        if not left_topics or not right_topics:
            return 0.0
        return len(left_topics & right_topics) / len(left_topics | right_topics)

    def _shared_topic_names(self, left: str, right: str) -> list[str]:
        right_topics = self._person_topics(right)
        names = {
            node.label
            for node in self.queries.topics_for_faculty(faculty_node_id(left))
            if node.id in right_topics
        }
        return sorted(names)

    def _cross_institution(self, left: str, right: str) -> bool:
        left_institutions = {
            node.id for node in self.queries.institutions_for_faculty(faculty_node_id(left))
        }
        right_institutions = {
            node.id for node in self.queries.institutions_for_faculty(faculty_node_id(right))
        }
        return bool(left_institutions and right_institutions) and not (
            left_institutions & right_institutions
        )

    def _work_title(self, work_id: str) -> str | None:
        work = self.works_by_id.get(work_id)
        return work.title if work else None

    def _work_quote(self, work_id: str) -> str:
        title = self._work_title(work_id)
        return title or f"OpenAlex work {work_id}"

    def _work_url(self, work_id: str) -> str | None:
        work = self.works_by_id.get(work_id)
        if work is None:
            return None
        return work.citation_url or work.provenance.source_url


def _normalize_scores(pairs: list[CollaborationPair]) -> None:
    """Scale each type's scores to 0-1 so types stay comparable."""
    peak = max((p.score for p in pairs), default=0.0)
    if peak <= 0:
        return
    for pair in pairs:
        pair.score = pair.score / peak


def find_collaborations(
    profiles: list[FacultyProfile],
    works: list[NormalizedWork],
    queries: GraphQueries,
    settings: Settings | None = None,
    faculty_id: str | None = None,
    *,
    top_k: int | None = None,
) -> CollaborationReport:
    """Convenience entry point for collaboration discovery."""
    return CollaborationEngine(profiles, works, queries, settings).find_collaborations(
        faculty_id, top_k=top_k
    )
