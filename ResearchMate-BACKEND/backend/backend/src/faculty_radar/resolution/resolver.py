"""Signal combination, verdicts, and clustering.

The central rule of this module:

    Two author records are NEVER merged on a name match alone.

A name match produces `needs_review`, never `same_person`. The reasons:

  * identical names are common enough to be uninformative - "Wei Zhang" exists
    at thousands of institutions
  * a wrong merge is silently destructive. It pools two people's publications,
    invents an expertise profile that neither person has, and produces a
    ranking that looks confident and is entirely fictional
  * a missed merge is recoverable by re-running the stage with looser thresholds

Because the asymmetry is that large, the thresholds below are deliberately
conservative and every decision carries the evidence that produced it.

Merging is done with union-find over `same_person` verdicts only.
`needs_review` pairs are surfaced for a human and never merged automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

from faculty_radar.config import Settings, get_logger, get_settings
from faculty_radar.models import (
    CanonicalResearcher,
    MergeEvidence,
    NormalizedAuthor,
    NormalizedWork,
    ResolutionDecision,
    ResolutionVerdict,
)
from faculty_radar.normalization.text import name_tokens
from faculty_radar.paths import DataPaths, build_paths
from faculty_radar.resolution.matching import compute_signals

logger = get_logger(__name__)


class _UnionFind:
    """Minimal disjoint-set forest, so a chain of merges collapses correctly."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, item: str) -> str:
        self.parent.setdefault(item, item)
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        # Path compression keeps repeated find() calls near-constant time.
        while self.parent[item] != root:
            self.parent[item], item = root, self.parent[item]
        return root

    def union(self, a: str, b: str) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self.parent[root_b] = root_a


@dataclass
class ResolutionReport:
    """What resolution did, and what a human still needs to look at."""

    researchers: list[CanonicalResearcher] = field(default_factory=list)
    decisions: list[ResolutionDecision] = field(default_factory=list)
    needs_review: list[ResolutionDecision] = field(default_factory=list)
    pairs_compared: int = 0

    @property
    def merged_count(self) -> int:
        return sum(1 for d in self.decisions if d.is_merge)

    @property
    def distinct_count(self) -> int:
        return sum(1 for d in self.decisions if d.verdict is ResolutionVerdict.DIFFERENT_PERSON)

    def stats(self) -> dict[str, int]:
        return {
            "researchers": len(self.researchers),
            "pairs_compared": self.pairs_compared,
            "merged": self.merged_count,
            "different": self.distinct_count,
            "needs_review": len(self.needs_review),
        }


class ResearcherResolver:
    """Compares author records and groups them into canonical researchers."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        merge_threshold: float = 0.62,
        auto_merge_threshold: float = 0.82,
    ) -> None:
        settings = settings or get_settings()
        self.settings = settings
        # A decision below `merge_threshold` is a rejection; between the two
        # thresholds it is queued for human review; above the higher one it is
        # merged without asking.
        self.merge_threshold = merge_threshold
        self.auto_merge_threshold = auto_merge_threshold

    # ------------------------------------------------------------- verdicts

    def decide(
        self,
        signals,
        works_by_author: dict[str, list[NormalizedWork]] | None = None,
    ) -> ResolutionDecision:
        """Turn a signal bundle into a verdict with evidence and confidence."""
        left_id, right_id = signals.left.openalex_id, signals.right.openalex_id
        by_name = {s.name: s for s in signals.signals}

        # 1. Same OpenAlex id is the same record by definition.
        if left_id == right_id:
            return ResolutionDecision(
                left_id=left_id,
                right_id=right_id,
                verdict=ResolutionVerdict.SAME_PERSON,
                confidence=1.0,
                evidence=[
                    MergeEvidence(
                        signal="openalex_id",
                        detail="identical source id",
                        weight=1.0,
                        supports_merge=True,
                    )
                ],
            )

        # 2. Conflicting ORCIDs are decisive proof of two different people.
        if signals.blocking_reason:
            return ResolutionDecision(
                left_id=left_id,
                right_id=right_id,
                verdict=ResolutionVerdict.DIFFERENT_PERSON,
                confidence=1.0,
                evidence=signals.to_evidence(),
                blocking_reason=signals.blocking_reason,
            )

        # 3. A unique matching ORCID is decisive in the other direction.
        if by_name.get("orcid") and by_name["orcid"].supports_merge:
            return ResolutionDecision(
                left_id=left_id,
                right_id=right_id,
                verdict=ResolutionVerdict.SAME_PERSON,
                confidence=0.97,
                evidence=signals.to_evidence(),
            )

        name = by_name.get("name")
        pub = by_name.get("publication_overlap")
        institution = by_name.get("institution")

        name_matches = bool(name and name.supports_merge)
        pub_matches = bool(pub and pub.supports_merge)
        institution_matches = bool(institution and institution.supports_merge)

        # 4. Different names, no shared work: different people.
        if not name_matches and not pub_matches:
            return ResolutionDecision(
                left_id=left_id,
                right_id=right_id,
                verdict=ResolutionVerdict.DIFFERENT_PERSON,
                confidence=0.6,
                evidence=signals.to_evidence(),
                blocking_reason="names do not match and no shared publications",
            )

        # 5. THE LOAD-BEARING RULE: a name match alone is never sufficient.
        if name_matches and not pub_matches:
            topic_signal = by_name.get("topic")
            corroborating = institution_matches or bool(
                topic_signal and topic_signal.supports_merge
            )
            confidence = signals.combined_score
            if corroborating and confidence >= self.merge_threshold:
                return ResolutionDecision(
                    left_id=left_id,
                    right_id=right_id,
                    verdict=ResolutionVerdict.SAME_PERSON,
                    confidence=confidence,
                    evidence=signals.to_evidence(),
                )
            # Same name, no corroboration. Almost always two different people,
            # so this is queued for a human rather than guessed at.
            return ResolutionDecision(
                left_id=left_id,
                right_id=right_id,
                verdict=ResolutionVerdict.NEEDS_REVIEW,
                confidence=confidence,
                evidence=signals.to_evidence(),
                blocking_reason=(
                    "name matches but no corroborating evidence "
                    "(no shared publications"
                    + ("" if institution_matches else ", different institutions")
                    + ")"
                ),
            )

        # 6. Shared publications outweigh any name difference: profiles of one
        #    person often carry a misspelt or truncated name.
        if pub_matches:
            confidence = min(0.99, 0.7 + 0.3 * (pub.score if pub else 0.0))
            return ResolutionDecision(
                left_id=left_id,
                right_id=right_id,
                verdict=ResolutionVerdict.SAME_PERSON,
                confidence=confidence,
                evidence=signals.to_evidence(),
            )

        return ResolutionDecision(
            left_id=left_id,
            right_id=right_id,
            verdict=ResolutionVerdict.DIFFERENT_PERSON,
            confidence=0.5,
            evidence=signals.to_evidence(),
            blocking_reason="insufficient evidence to merge",
        )

    def compare(
        self,
        authors: list[NormalizedAuthor],
        works_by_author: dict[str, list[NormalizedWork]] | None = None,
    ) -> tuple[list[ResolutionDecision], int]:
        """Decide every candidate pair.

        Candidate generation uses *token* blocking rather than last-token
        surname blocking. Surname blocking alone is blind to the most common
        real variants - "Zhang Wei" and "Zhang W." are listed surname-first, so
        their final token is "wei" or "w", and those records would never be
        compared against "Wei Zhang" at all. Blocking on any shared name token
        keeps the candidate set small while covering both name orders.

        Returns the decisions and the number of pairs actually compared.
        """
        by_id = {a.openalex_id: a for a in authors}

        # Index every substantive name token to the authors carrying it.
        token_index: dict[str, list[str]] = {}
        for author in authors:
            for token in self._significant_tokens(author):
                token_index.setdefault(token, []).append(author.openalex_id)

        candidate_pairs: set[tuple[str, str]] = set()
        for author_ids in token_index.values():
            if len(author_ids) < 2:
                continue
            for left_id, right_id in combinations(sorted(set(author_ids)), 2):
                candidate_pairs.add((left_id, right_id))

        decisions: list[ResolutionDecision] = []
        for left_id, right_id in sorted(candidate_pairs):
            left, right = by_id[left_id], by_id[right_id]
            signals = compute_signals(left, right, works_by_author)
            decisions.append(self.decide(signals, works_by_author))
        return decisions, len(candidate_pairs)

    @staticmethod
    def _significant_tokens(author: NormalizedAuthor) -> set[str]:
        """Name tokens worth blocking on.

        Single letters are excluded: the initial "W." appears in thousands of
        names and would make every record a candidate for every other.
        """
        tokens: set[str] = set()
        for name in (author.canonical_name, *author.name_variants):
            for token in name_tokens(name):
                if len(token) >= 2:
                    tokens.add(token)
        return tokens

    # ------------------------------------------------------------ clustering

    def cluster(
        self,
        authors: list[NormalizedAuthor],
        works_by_author: dict[str, list[NormalizedWork]] | None,
    ) -> tuple[list[CanonicalResearcher], list[ResolutionDecision], list[ResolutionDecision], int]:
        """Group author records into canonical researchers.

        Returns (researchers, decisions, needs_review, pairs_compared).

        The post-merge ORCID check is a safety net: if union-find ever links two
        records that both carry an ORCID, those must be different people, so the
        merge is dropped and the pair is escalated instead of silently kept.
        """
        decisions, compared = self.compare(authors, works_by_author)
        merges = [d for d in decisions if d.is_merge]

        union = _UnionFind()
        for author in authors:
            union.find(author.openalex_id)

        for decision in merges:
            union.union(decision.left_id, decision.right_id)

        groups: dict[str, list[NormalizedAuthor]] = {}
        for author in authors:
            groups.setdefault(union.find(author.openalex_id), []).append(author)

        needs_review: list[ResolutionDecision] = []
        accepted: list[ResolutionDecision] = []
        for decision in decisions:
            if decision.verdict is ResolutionVerdict.NEEDS_REVIEW:
                needs_review.append(decision)
            elif not decision.is_merge:
                accepted.append(decision)

        researchers: list[CanonicalResearcher] = []
        for root, members in groups.items():
            orcids = [m.orcid for m in members if m.orcid]
            if len(set(orcids)) > 1:
                # Safety net: never emit an identity holding two ORCIDs.
                for left, right in combinations(members, 2):
                    if left.orcid and right.orcid and left.orcid != right.orcid:
                        needs_review.append(
                            ResolutionDecision(
                                left_id=left.openalex_id,
                                right_id=right.openalex_id,
                                verdict=ResolutionVerdict.NEEDS_REVIEW,
                                confidence=0.0,
                                evidence=[
                                    MergeEvidence(
                                        signal="post_merge_check",
                                        detail=f"cluster {root} holds conflicting ORCIDs",
                                        weight=1.0,
                                        supports_merge=False,
                                    )
                                ],
                                blocking_reason="cluster would contain two ORCIDs",
                            )
                        )
                continue
            researchers.append(self._build_researcher(root, members, works_by_author))

        accepted = [d for d in accepted if d.left_id not in {n.left_id for n in needs_review}]
        return researchers, accepted, needs_review, compared

    def _build_researcher(
        self,
        researcher_id: str,
        members: list[NormalizedAuthor],
        works_by_author: dict[str, list[NormalizedWork]] | None,
    ) -> CanonicalResearcher:
        """Assemble a canonical identity from its constituent author records."""
        works_by_author = works_by_author or {}
        ordered = sorted(members, key=lambda a: (-a.cited_by_count, a.openalex_id))

        name = max(
            (m.display_name or m.canonical_name for m in ordered),
            key=len,
        )
        variants: list[str] = []
        for member in ordered:
            for candidate in (member.canonical_name, *member.name_variants):
                differing = candidate.casefold() != name.casefold()
                if candidate and differing and candidate not in variants:
                    variants.append(candidate)

        institutions: dict[str, object] = {}
        topics: dict[str, object] = {}
        work_ids: list[str] = []
        for member in ordered:
            for institution in member.institutions:
                institutions.setdefault(institution.id or institution.name, institution)
            for topic in member.topics:
                topics.setdefault(topic.key, topic)
            work_ids.extend(w.openalex_id for w in works_by_author.get(member.openalex_id, []))

        return CanonicalResearcher(
            researcher_id=researcher_id,
            canonical_name=name,
            name_variants=variants,
            orcid=next((m.orcid for m in ordered if m.orcid), None),
            openalex_ids=[m.openalex_id for m in ordered],
            institutions=list(institutions.values()),
            topics=list(topics.values()),
            work_ids=sorted({w for w in work_ids if w}),
            cited_by_count=sum(m.cited_by_count for m in ordered),
        )


def resolve_researchers(
    authors: list[NormalizedAuthor],
    works: list[NormalizedWork] | None = None,
    settings: Settings | None = None,
    paths: DataPaths | None = None,
    *,
    store: bool = True,
) -> ResolutionReport:
    """Resolve every author record into canonical researcher identities."""
    settings = settings or get_settings()
    paths = paths or build_paths(settings)

    works_by_author: dict[str, list[NormalizedWork]] = {}
    for work in works or []:
        for author_id in work.author_ids:
            works_by_author.setdefault(author_id, []).append(work)

    resolver = ResearcherResolver(settings)
    researchers, decisions, needs_review, compared = resolver.cluster(authors, works_by_author)

    report = ResolutionReport(
        researchers=researchers,
        decisions=decisions,
        needs_review=needs_review,
        pairs_compared=compared,
    )

    if store:
        from faculty_radar.resolution.store import ResolvedStore

        ResolvedStore(paths).write(report)

    logger.info("entity resolution complete", extra=report.stats())
    return report
