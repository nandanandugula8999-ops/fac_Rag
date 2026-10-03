"""Individual evidence signals for entity resolution.

Each function answers one narrow question and returns a score in [0, 1] plus a
short human-readable detail string. Keeping them separate is what makes the
merge logic auditable: a reviewer can see exactly which signal fired, and the
resolver in the next module decides only how to weigh them.

No fuzzy-matching library. Every comparison here is deterministic and
explainable, because a merge that cannot be explained cannot be undone.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from faculty_radar.models import NormalizedAuthor, NormalizedWork
from faculty_radar.normalization.text import canonical_key, name_tokens

# Weights used when combining signals into an overall match score. Declared here
# so that the resolver has no magic numbers of its own.
SIGNAL_WEIGHTS: dict[str, float] = {
    "orcid": 0.95,
    "publication_overlap": 0.90,
    "institution": 0.55,
    "name": 0.45,
    "topic": 0.20,
}


@dataclass
class Signal:
    """One piece of evidence, scored and explained."""

    name: str
    score: float
    detail: str
    supports_merge: bool

    @property
    def weight(self) -> float:
        return SIGNAL_WEIGHTS.get(self.name, 0.0)


@dataclass
class MatchSignals:
    """All evidence for one candidate pair."""

    left: NormalizedAuthor
    right: NormalizedAuthor
    signals: list[Signal] = field(default_factory=list)
    #: A signal that proves the records are different people. Overrides all scores.
    blocking_reason: str | None = None
    shared_work_ids: list[str] = field(default_factory=list)
    shared_topics: list[str] = field(default_factory=list)

    @property
    def combined_score(self) -> float:
        """Weighted mean of supporting signals, in [0, 1]."""
        if not self.signals:
            return 0.0
        total_weight = sum(s.weight for s in self.signals)
        if total_weight == 0:
            return 0.0
        return round(sum(s.score * s.weight for s in self.signals) / total_weight, 4)

    @property
    def supporting_signals(self) -> list[Signal]:
        return [s for s in self.signals if s.supports_merge]

    def to_evidence(self) -> list:
        """Convert to the Rule-1/Rule-4 evidence list stored on a decision."""
        from faculty_radar.models import MergeEvidence

        return [
            MergeEvidence(
                signal=s.name,
                detail=s.detail,
                weight=s.weight,
                supports_merge=s.supports_merge,
            )
            for s in self.signals
        ]


# --------------------------------------------------------------------------
# ORCID - the only identifier that is decisive on its own
# --------------------------------------------------------------------------


def orcid_compatibility(left: NormalizedAuthor, right: NormalizedAuthor) -> Signal:
    """Compare ORCIDs.

    Matching ORCIDs are near-conclusive. Differing ORCIDs are *proof* of two
    different people: an ORCID is a unique personal identifier, so two records
    cannot belong to one person while carrying different ones.
    """
    left_orcid, right_orcid = left.orcid, right.orcid

    if left_orcid and right_orcid:
        if left_orcid == right_orcid:
            return Signal("orcid", 1.0, f"both records carry ORCID {left_orcid}", True)
        return Signal("orcid", 0.0, f"conflicting ORCIDs: {left_orcid} vs {right_orcid}", False)

    if left_orcid or right_orcid:
        present = left_orcid or right_orcid
        missing = right if left_orcid else left
        return Signal(
            "orcid",
            0.0,
            f"{missing.openalex_id} has no ORCID while the other has {present}",
            False,
        )

    return Signal("orcid", 0.0, "neither record carries an ORCID", False)


# --------------------------------------------------------------------------
# Institution affiliation
# --------------------------------------------------------------------------


def institution_overlap(left: NormalizedAuthor, right: NormalizedAuthor) -> Signal:
    """Fraction of shared institutions.

    A shared institution is weak evidence for identity: thousands of people
    share one. It is strong evidence *against* it when combined with an
    identical name and different institutions, which is the classic homonym.
    """
    left_ids = {i.id for i in left.institutions if i.id}
    right_ids = {i.id for i in right.institutions if i.id}
    left_names = {canonical_key(i.name) for i in left.institutions}
    right_names = {canonical_key(i.name) for i in right.institutions}

    shared_ids = left_ids & right_ids
    shared_names = (left_names & right_names) - {""}
    union_names = (left_names | right_names) - {""}

    if not left_ids or not right_ids:
        return Signal("institution", 0.0, "at least one record has no known institution", False)

    if shared_ids:
        return Signal("institution", 1.0, f"share institution {sorted(shared_ids)[0]}", True)

    if shared_names:
        return Signal("institution", 1.0, f"share institution name {sorted(shared_names)[0]}", True)

    score = round(len(union_names - (left_names & right_names)) / max(len(union_names), 1), 3)
    overlap = len(union_names - (left_names & right_names))
    return Signal(
        "institution",
        1.0 - score if union_names else 0.0,
        f"different institutions: {left_names or '?'} vs {right_names or '?'} ({overlap} distinct)",
        False,
    )


# --------------------------------------------------------------------------
# Names
# --------------------------------------------------------------------------


def _initials_match(left_token: str, right_token: str) -> bool:
    """True when a single-letter initial matches the other token's first letter."""
    if len(left_token) == 1:
        return left_token == right_token[0]
    if len(right_token) == 1:
        return right_token == left_token[0]
    return False


def name_similarity(left: NormalizedAuthor, right: NormalizedAuthor) -> Signal:
    """Compare names, including the common 'W. Zhang' vs 'Wei Zhang' pattern.

    This signal never supports a merge by itself. It is a *filter* that can rule
    out pairs outright and can corroborate other evidence, which the resolver
    enforces.
    """
    left_key = canonical_key(left.canonical_name)
    right_key = canonical_key(right.canonical_name)
    if not left_key or not right_key:
        return Signal("name", 0.0, "at least one record has no name", False)

    if left_key == right_key:
        return Signal("name", 1.0, f"identical normalized name '{left_key}'", True)

    left_tokens = name_tokens(left.canonical_name)
    right_tokens = name_tokens(right.canonical_name)

    # Compare against declared name variants too: "W. Zhang" often appears only
    # as an alternative on one of the two records.
    for variant in [*left.name_variants, *right.name_variants]:
        if canonical_key(variant) in (left_key, right_key):
            other = right_key if canonical_key(variant) == left_key else left_key
            return Signal("name", 0.97, f"'{variant}' matches '{other}' via name variants", True)

    # Initials-compatible: same token count, one side initialed.
    if len(left_tokens) == len(right_tokens) and left_tokens:
        pairs = zip(left_tokens, right_tokens, strict=True)
        if all(a == b or _initials_match(a, b) for a, b in pairs):
            joined = ", ".join(left_tokens)
            return Signal("name", 0.85, f"initials-compatible: '{joined}' vs '{right_key}'", True)

    shared = set(left_tokens) & set(right_tokens)
    union = set(left_tokens) | set(right_tokens)
    jaccard = len(shared) / len(union) if union else 0.0
    same_surname = bool(left_tokens and right_tokens and left_tokens[-1] == right_tokens[-1])
    if same_surname and jaccard >= 0.34:
        return Signal(
            "name",
            round(jaccard, 3),
            f"same surname, {len(shared)}/{len(union)} name tokens shared",
            True,
        )
    return Signal("name", round(jaccard, 3), f"name tokens overlap {jaccard:.2f}", False)


# --------------------------------------------------------------------------
# Publications and topics
# --------------------------------------------------------------------------


def publication_overlap(
    left: NormalizedAuthor,
    right: NormalizedAuthor,
    works_by_author: dict[str, list[NormalizedWork]] | None = None,
) -> tuple[Signal, list[str]]:
    """Jaccard overlap of the two authors' publication sets.

    Shared publications are strong identity evidence: two different people
    rarely share authorship of the same paper, whereas split profiles of one
    person routinely miss half their work.
    """
    works_by_author = works_by_author or {}
    left_ids = {w.openalex_id for w in works_by_author.get(left.openalex_id, []) if w.openalex_id}
    right_ids = {w.openalex_id for w in works_by_author.get(right.openalex_id, []) if w.openalex_id}

    if not left_ids or not right_ids:
        return (
            Signal("publication_overlap", 0.0, "publication sets unavailable for one side", False),
            [],
        )

    shared = sorted(left_ids & right_ids)
    union = left_ids | right_ids
    jaccard = len(shared) / len(union)
    detail = f"{len(shared)} shared of {len(union)} distinct publications"
    # Even one shared paper is meaningful; the Jaccard keeps it honest when the
    # two records have very different publication counts.
    return Signal("publication_overlap", round(jaccard, 3), detail, bool(shared)), shared


def topic_similarity(left: NormalizedAuthor, right: NormalizedAuthor) -> tuple[Signal, list[str]]:
    """Jaccard overlap of topic sets.

    Deliberately weak. Two researchers in one field share topics; this signal
    corroborates a merge proposed on stronger evidence and must never propose
    one by itself.
    """
    left_topics = {t.key for t in left.topics if t.key}
    right_topics = {t.key for t in right.topics if t.key}
    if not left_topics or not right_topics:
        return Signal("topic", 0.0, "one or both records have no topics", False), []

    shared = sorted(left_topics & right_topics)
    union = left_topics | right_topics
    jaccard = len(shared) / len(union)
    return (
        Signal(
            "topic",
            round(jaccard, 3),
            f"{len(shared)} shared of {len(union)} topics",
            bool(shared),
        ),
        shared,
    )


def compute_signals(
    left: NormalizedAuthor,
    right: NormalizedAuthor,
    works_by_author: dict[str, list[NormalizedWork]] | None = None,
) -> MatchSignals:
    """Collect every signal for one candidate pair."""
    signals = MatchSignals(left=left, right=right)

    orcid = orcid_compatibility(left, right)
    signals.signals.append(orcid)

    # Two different ORCIDs mean two different people. Nothing else can override
    # this, so it short-circuits before weaker signals are computed.
    if orcid.name == "orcid" and not orcid.supports_merge and left.orcid and right.orcid:
        signals.blocking_reason = orcid.detail
        return signals

    signals.signals.append(name_similarity(left, right))
    signals.signals.append(institution_overlap(left, right))

    pub_signal, shared_works = publication_overlap(left, right, works_by_author)
    signals.signals.append(pub_signal)
    signals.shared_work_ids = shared_works

    topic_signal, shared_topics = topic_similarity(left, right)
    signals.signals.append(topic_signal)
    signals.shared_topics = shared_topics

    return signals
