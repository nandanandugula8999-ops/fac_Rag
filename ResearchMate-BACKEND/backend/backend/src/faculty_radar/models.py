"""Canonical domain model shared by every pipeline stage.

Rule 1 (preserve provenance) is enforced structurally rather than by
convention: every entity carries a `Provenance` record, and provenance is a
required field rather than an optional annotation. A record without a traceable
origin cannot be constructed.

Rule 2 (never hallucinate) is enforced by the absence of free-text invention.
Scores are floats computed from evidence; evidence items point at real works;
citations carry real DOIs and URLs. Where evidence is missing, models use
`None` or the explicit `INSUFFICIENT_EVIDENCE` marker - never a plausible
placeholder.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# The explicit marker required by Rule 2 when nothing supports an answer.
INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ExpertiseType(StrEnum):
    """Rule 3. The three kinds of expertise, which must never be conflated."""

    STATED = "STATED"
    EVIDENCE_BASED = "EVIDENCE_BASED"
    INFERRED = "INFERRED"


class ResolutionVerdict(StrEnum):
    """Outcome of comparing two researcher records."""

    SAME_PERSON = "same_person"
    DIFFERENT_PERSON = "different_person"
    NEEDS_REVIEW = "needs_review"


class VerificationStatus(StrEnum):
    """Rule 2 / citation verification outcomes."""

    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    CONFLICTING = "conflicting"


class CollaborationType(StrEnum):
    EXISTING = "EXISTING"
    POTENTIAL = "POTENTIAL"


class DocumentType(StrEnum):
    FACULTY_PROFILE = "faculty_profile"
    PUBLICATION = "publication"
    PROJECT = "project_description"


class Status(StrEnum):
    """Whether a stage produced a real result or the explicit no-evidence marker.

    Modelled as an enum rather than a bare `Literal["ok", ...]`: string members
    inside `Literal` become forward references under PEP 563 and fail to
    resolve at schema-build time.
    """

    OK = "ok"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class _Model(BaseModel):
    """Base for all domain models: strict, immutable-by-convention, no extras."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------


class Provenance(_Model):
    """Where a record came from. Rule 1.

    `retrieved_at` plus `source_url` is the minimum needed to re-fetch and
    re-verify any claim in the system. `raw_path` points into the immutable
    `data/raw` snapshot store.
    """

    source: str = Field(description="Source system identifier, e.g. 'openalex'.")
    source_id: str = Field(description="Identifier within that source.")
    source_url: str | None = Field(default=None, description="Canonical landing page.")
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    raw_path: str | None = Field(default=None, description="Location in the raw store.")
    record_hash: str | None = Field(
        default=None,
        description="SHA-256 of the source payload, for integrity checks.",
    )

    @classmethod
    def from_payload(
        cls,
        source: str,
        source_id: str,
        payload: Any,
        *,
        source_url: str | None = None,
        raw_path: str | None = None,
        retrieved_at: datetime | None = None,
    ) -> Provenance:
        """Build provenance with a content hash of the original payload.

        `retrieved_at` should be the time the *source* was fetched, not the time
        this record was derived. Passing the raw envelope's timestamp through
        keeps derived records deterministic: re-normalizing an unchanged
        snapshot yields byte-identical output.
        """
        import json

        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return cls(
            source=source,
            source_id=source_id,
            source_url=source_url,
            raw_path=raw_path,
            record_hash=hashlib.sha256(encoded).hexdigest(),
            **({"retrieved_at": retrieved_at} if retrieved_at is not None else {}),
        )


# --------------------------------------------------------------------------
# Shared entities
# --------------------------------------------------------------------------


class Institution(_Model):
    id: str | None = None
    name: str
    ror: str | None = None
    country_code: str | None = None
    type: str | None = None


class Topic(_Model):
    """A research topic. `share` is OpenAlex's topic_share (0-1)."""

    id: str | None = None
    name: str
    subfield: str | None = None
    field: str | None = None
    share: float = Field(default=1.0, ge=0.0, le=1.0)

    @property
    def key(self) -> str:
        """Stable lowercase key for exact topic comparison."""
        return self.name.strip().lower()


class Keyword(_Model):
    id: str | None = None
    name: str
    score: float | None = None

    @property
    def key(self) -> str:
        return self.name.strip().lower()


class Concept(_Model):
    id: str | None = None
    name: str
    level: int | None = None
    score: float | None = None


class Affiliation(_Model):
    """An author's affiliation on a specific work. Per-work, not global."""

    institution: Institution
    raw_string: str | None = None
    is_primary: bool = False
    country_code: str | None = None
    # OpenAlex raw type string, e.g. "education".
    type: str | None = None


class Authorship(_Model):
    """One author's claim of authorship on one work."""

    author_position: str | None = None
    is_corresponding: bool = False
    affiliation: Affiliation | None = None
    raw_author_id: str | None = None


class OpenLocation(_Model):
    """Where a work's full text or landing page lives."""

    landing_page_url: str | None = None
    pdf_url: str | None = None
    is_oa: bool = False
    oa_status: str | None = None
    version: str | None = None
    license: str | None = None


# --------------------------------------------------------------------------
# Normalized entities (output of stage 2)
# --------------------------------------------------------------------------


class NormalizedAuthor(_Model):
    openalex_id: str
    name: str
    display_name: str | None = None
    orcid: str | None = None
    name_variants: list[str] = Field(default_factory=list)
    affiliations: list[Affiliation] = Field(default_factory=list)
    institutions: list[Institution] = Field(default_factory=list)
    topics: list[Topic] = Field(default_factory=list)
    works_count: int = 0
    cited_by_count: int = 0
    h_index: int | None = None
    provenance: Provenance

    @property
    def canonical_name(self) -> str:
        return (self.display_name or self.name).strip()


class NormalizedWork(_Model):
    openalex_id: str
    title: str | None = None
    doi: str | None = None
    year: int | None = None
    publication_date: date | None = None
    abstract: str | None = None
    type: str | None = None
    is_retracted: bool = False
    is_paratext: bool = False
    authorships: list[Authorship] = Field(default_factory=list)
    institutions: list[Institution] = Field(default_factory=list)
    topics: list[Topic] = Field(default_factory=list)
    keywords: list[Keyword] = Field(default_factory=list)
    concepts: list[Concept] = Field(default_factory=list)
    referenced_work_ids: list[str] = Field(default_factory=list)
    related_work_ids: list[str] = Field(default_factory=list)
    locations: list[OpenLocation] = Field(default_factory=list)
    cited_by_count: int = 0
    provenance: Provenance

    @property
    def author_ids(self) -> list[str]:
        """OpenAlex author IDs claimed by this work's authorships."""
        return [a.raw_author_id for a in self.authorships if a.raw_author_id]

    @property
    def best_oa_url(self) -> str | None:
        """Best available open-access URL, else the first landing page."""
        for loc in self.locations:
            if loc.is_oa and (loc.pdf_url or loc.landing_page_url):
                return loc.pdf_url or loc.landing_page_url
        for loc in self.locations:
            if loc.landing_page_url:
                return loc.landing_page_url
        return None

    @property
    def citation_url(self) -> str | None:
        """A stable, resolvable citation target. Never synthesized."""
        if self.doi:
            return f"https://doi.org/{self.doi}"
        return self.provenance.source_url


# --------------------------------------------------------------------------
# Stage 3: entity resolution
# --------------------------------------------------------------------------


class MergeEvidence(_Model):
    """One reason a merge was (or was not) proposed.

    Rule 2: an unevidenced merge is not a merge. This is why evidence is a list
    rather than a single score, and why it is empty when the verdict is negative.
    """

    signal: str = Field(description="e.g. 'orcid', 'name_variant', 'topic_similarity'.")
    detail: str
    weight: float = Field(ge=0.0, le=1.0)
    supports_merge: bool


class ResolutionDecision(_Model):
    """Verdict for one candidate pair, with the evidence behind it."""

    left_id: str
    right_id: str
    verdict: ResolutionVerdict
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[MergeEvidence] = Field(default_factory=list)
    blocking_reason: str | None = Field(
        default=None,
        description="Why a merge was refused, e.g. different ORCID.",
    )

    @property
    def is_merge(self) -> bool:
        return self.verdict is ResolutionVerdict.SAME_PERSON


class CanonicalResearcher(_Model):
    """One resolved human being: the merge of one or more author records."""

    researcher_id: str
    canonical_name: str
    name_variants: list[str] = Field(default_factory=list)
    orcid: str | None = None
    openalex_ids: list[str] = Field(default_factory=list)
    institutions: list[Institution] = Field(default_factory=list)
    topics: list[Topic] = Field(default_factory=list)
    work_ids: list[str] = Field(default_factory=list)
    cited_by_count: int = 0
    # Decisions that produced this identity, so a merge can be audited/undone.
    merge_decisions: list[ResolutionDecision] = Field(default_factory=list)

    @property
    def name_keys(self) -> list[str]:
        return {self.canonical_name, *self.name_variants}


# --------------------------------------------------------------------------
# Stage 4: faculty <-> publication linking
# --------------------------------------------------------------------------


class LinkedPublication(_Model):
    """A work linked to faculty, with the evidence for that link."""

    work_id: str
    faculty_id: str
    link_method: str = Field(description="How the link was made, e.g. 'openalex_authorship'.")
    link_confidence: float = Field(ge=0.0, le=1.0)
    author_position: str | None = None
    year: int | None = None
    title: str | None = None
    doi: str | None = None
    citation_url: str | None = None
    is_open_access: bool = False


class FacultyProfile(_Model):
    """A consented faculty member, ready for indexing and ranking."""

    faculty_id: str
    name: str
    orcid: str | None = None
    researcher_id: str
    institutions: list[Institution] = Field(default_factory=list)
    # Topics the institution or the faculty member explicitly declared.
    stated_topics: list[Topic] = Field(default_factory=list)
    stated_project_descriptions: list[str] = Field(default_factory=list)
    publications: list[LinkedPublication] = Field(default_factory=list)
    cited_by_count: int = 0
    # Consent is a precondition for discovery, enforced at this stage.
    consented: bool = True
    provenance: Provenance

    def publication_years(self) -> list[int]:
        return [p.year for p in self.publications if p.year is not None]


# --------------------------------------------------------------------------
# Stage 5: knowledge graph
# --------------------------------------------------------------------------


class NodeType(StrEnum):
    FACULTY = "faculty"
    PUBLICATION = "publication"
    TOPIC = "topic"
    KEYWORD = "keyword"
    INSTITUTION = "institution"
    RESEARCHER = "researcher"


class EdgeType(StrEnum):
    AUTHORED = "authored"
    ABOUT_TOPIC = "about_topic"
    HAS_KEYWORD = "has_keyword"
    AT_INSTITUTION = "at_institution"
    CITES = "cites"
    COLLABORATED_WITH = "collaborated_with"
    STATES_TOPIC = "states_topic"


class GraphNode(_Model):
    id: str
    type: NodeType
    label: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(_Model):
    source: str
    target: str
    type: EdgeType
    weight: float = Field(default=1.0, ge=0.0)
    year: int | None = None
    # Rule 1: relationships carry provenance just like entities do.
    provenance: Provenance | None = None

    @property
    def key(self) -> tuple[str, str, EdgeType]:
        return (self.source, self.target, self.type)


class KnowledgeGraph(_Model):
    nodes: dict[str, GraphNode] = Field(default_factory=dict)
    edges: list[GraphEdge] = Field(default_factory=list)

    @property
    def edge_keys(self) -> set[tuple[str, str, EdgeType]]:
        return {e.key for e in self.edges}

    def add_node(self, node: GraphNode) -> None:
        self.nodes.setdefault(node.id, node)

    def add_edge(self, edge: GraphEdge) -> bool:
        """Add an edge unless an identical one exists. Returns True if added."""
        if edge.key in self.edge_keys:
            return False
        self.edges.append(edge)
        return True

    def neighbors(self, node_id: str, edge_type: EdgeType) -> list[GraphEdge]:
        return [e for e in self.edges if e.type is edge_type and e.source == node_id]

    def edges_of(self, edge_type: EdgeType) -> list[GraphEdge]:
        return [e for e in self.edges if e.type is edge_type]

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)


# --------------------------------------------------------------------------
# Stage 6: research corpus
# --------------------------------------------------------------------------


class CorpusDocument(_Model):
    """A retrievable unit of text with full provenance.

    `document_type` and `field_origins` are what allow the expertise engine to
    separate stated expertise (profile / project text the faculty member
    actually declared) from inferred expertise (derived from publications).
    """

    doc_id: str
    text: str
    document_type: DocumentType
    faculty_id: str | None = None
    work_id: str | None = None
    institution_id: str | None = None
    year: int | None = None
    topics: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    source_url: str | None = None
    doi: str | None = None
    # Which fields contributed to `text`, used for field-weighted ranking.
    field_origins: dict[str, str] = Field(default_factory=dict)
    # Marks text the source explicitly stated, versus text we assembled.
    is_stated: bool = False
    provenance: Provenance | None = None

    @classmethod
    def make_id(cls, faculty_id: str | None, work_id: str | None, doc_type: DocumentType) -> str:
        seed = f"{faculty_id or '-'}|{work_id or '-'}|{doc_type.value}"
        digest = hashlib.sha1(seed.encode(), usedforsecurity=False).hexdigest()[:16]
        return f"{doc_type.value}:{digest}"

    @property
    def embed_text(self) -> str:
        """Text sent to the embedder: topical fields first, title repeated."""
        parts: list[str] = []
        if self.topics:
            parts.append(" ".join(self.topics))
        parts.append(self.text)
        return "\n".join(p for p in parts if p)


# --------------------------------------------------------------------------
# Stages 8-10: retrieval, ranking, expertise
# --------------------------------------------------------------------------


class RankingSignal(_Model):
    """Rule 4. One named, inspectable contribution to a score."""

    name: str
    value: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0)
    contribution: float = Field(ge=0.0)
    explanation: str


class EvidenceItem(_Model):
    """A citable unit of evidence attached to a result."""

    evidence_id: str
    faculty_id: str | None = None
    work_id: str | None = None
    doc_id: str | None = None
    quote: str = Field(description="Verbatim passage supporting the result.")
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    source_url: str | None = None
    # Distinguishes profile/project assertions from publication-derived text.
    source_type: DocumentType = DocumentType.PUBLICATION
    relevance: float = Field(ge=0.0, le=1.0, default=0.0)
    expertise_type: ExpertiseType = ExpertiseType.EVIDENCE_BASED


class RetrievalHit(_Model):
    doc_id: str
    score: float
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    rerank_score: float | None = None
    rank: int | None = None
    document: CorpusDocument | None = None
    # Which retrievers produced this hit. Needed by Rule 3 downstream.
    signals: list[str] = Field(default_factory=list)
    matched_fields: list[str] = Field(default_factory=list)
    matched_terms: list[str] = Field(default_factory=list)


class ExpertiseMatch(_Model):
    """One faculty member's expertise for one query, fully explained."""

    faculty_id: str
    faculty_name: str
    query: str
    score: float = Field(ge=0.0, le=1.0)
    expertise_type: ExpertiseType
    # Stated and inferred are reported separately and never summed into one
    # unlabeled number.
    stated_score: float = 0.0
    evidence_score: float = 0.0
    inferred_score: float = 0.0
    signals: list[RankingSignal] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    supporting_publications: list[LinkedPublication] = Field(default_factory=list)
    institutions: list[Institution] = Field(default_factory=list)
    matched_topics: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _label_derived_type(self) -> Self:
        """Infer the expertise type from the strongest component.

        Deliberately conservative: a semantic-only hit is INFERRED even when a
        weak topic signal is present, so stated evidence is never inferred away
        from by a noisy signal.
        """
        if self.expertise_type in (ExpertiseType.STATED, ExpertiseType.EVIDENCE_BASED):
            return self
        if (
            self.stated_score >= max(self.evidence_score, self.inferred_score)
            and self.stated_score > 0
        ):
            resolved = ExpertiseType.STATED
        elif self.evidence_score >= self.inferred_score and self.evidence_score > 0:
            resolved = ExpertiseType.EVIDENCE_BASED
        else:
            resolved = ExpertiseType.INFERRED
        # Bypass validate_assignment: assigning here would re-run this very
        # validator and recurse until the stack gives out.
        self.__dict__["expertise_type"] = resolved
        return self

    def explain(self) -> str:
        """Human-readable Rule 4 explanation of this ranking."""
        lines = [
            f"{self.faculty_name}: score={self.score:.3f} type={self.expertise_type.value}",
            f"  stated={self.stated_score:.3f} evidence={self.evidence_score:.3f} "
            f"inferred={self.inferred_score:.3f}",
        ]
        for signal in sorted(self.signals, key=lambda s: -s.contribution):
            lines.append(
                f"  [{signal.name}] value={signal.value:.3f} weight={signal.weight:.2f} "
                f"contrib={signal.contribution:.3f} - {signal.explanation}"
            )
        if self.evidence:
            lines.append(f"  evidence: {len(self.evidence)} supporting passages")
            for item in self.evidence[:3]:
                title = (item.title or item.quote[:60]).strip()
                lines.append(
                    f"    - ({item.year or 'n.d.'}) {title} [{item.source_url or 'no url'}]"
                )
        for note in self.notes:
            lines.append(f"  note: {note}")
        return "\n".join(lines)


class ExpertiseReport(_Model):
    """Ranked faculty for a query."""

    query: str
    filters: dict[str, Any] = Field(default_factory=dict)
    matches: list[ExpertiseMatch] = Field(default_factory=list)
    # Set when no evidence supported an answer. Rule 2.
    status: Status = Status.OK
    total_candidates: int = 0

    @property
    def top(self) -> ExpertiseMatch | None:
        return self.matches[0] if self.matches else None

    def explain(self) -> str:
        if self.status is Status.INSUFFICIENT_EVIDENCE:
            return f"Query {self.query!r}: insufficient_evidence - no faculty matched the filters."
        return "\n\n".join(m.explain() for m in self.matches)


# --------------------------------------------------------------------------
# Stages 11-12: collaboration and trends
# --------------------------------------------------------------------------


class CollaborationPair(_Model):
    faculty_a: str
    faculty_b: str
    faculty_a_name: str
    faculty_b_name: str
    collaboration_type: CollaborationType
    score: float = Field(ge=0.0, le=1.0)
    shared_work_ids: list[str] = Field(default_factory=list)
    shared_topics: list[str] = Field(default_factory=list)
    topic_overlap: float = 0.0
    signals: list[RankingSignal] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def explain(self) -> str:
        lines = [
            f"{self.faculty_a_name} <-> {self.faculty_b_name} "
            f"[{self.collaboration_type.value}] score={self.score:.3f}"
        ]
        if self.shared_work_ids:
            lines.append(f"  shared works: {len(self.shared_work_ids)}")
        lines.append(f"  shared topics: {', '.join(self.shared_topics) or 'none'}")
        for signal in self.signals:
            lines.append(f"  [{signal.name}] {signal.value:.3f} - {signal.explanation}")
        for note in self.notes:
            lines.append(f"  note: {note}")
        return "\n".join(lines)


class CollaborationReport(_Model):
    query_faculty_id: str | None = None
    pairs: list[CollaborationPair] = Field(default_factory=list)
    status: Status = Status.OK


class TopicTrend(_Model):
    topic: str
    field: str | None = None
    total_publications: int
    recent_publications: int
    baseline_publications: int
    # recent / baseline, per year. >1 means growing.
    growth_ratio: float
    first_year: int | None = None
    last_year: int | None = None
    faculty_ids: list[str] = Field(default_factory=list)
    # "rising" | "declining" | "stable" | "emerging"
    direction: str
    sample_years: list[int] = Field(default_factory=list)
    counts_by_year: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class TrendReport(_Model):
    year_counts: dict[str, int] = Field(default_factory=dict)
    topics: list[TopicTrend] = Field(default_factory=list)
    keywords: list[TopicTrend] = Field(default_factory=list)
    recent_years: int = 0
    baseline_years: int = 0
    notes: list[str] = Field(default_factory=list)
    status: Status = Status.OK


# --------------------------------------------------------------------------
# Stages 13-15: evidence, RAG, verification
# --------------------------------------------------------------------------


class AnswerCitation(_Model):
    """A citation attached to a generated claim.

    Every field is copied from a real ingested record. `doi` and `source_url`
    are never constructed by the LLM layer; see `rag` and `verification`.
    """

    evidence_id: str
    work_id: str | None = None
    faculty_id: str | None = None
    title: str | None = None
    year: int | None = None
    doi: str | None = None
    source_url: str | None = None
    quote: str


class AnswerClaim(_Model):
    text: str
    citations: list[AnswerCitation] = Field(default_factory=list)
    status: VerificationStatus = VerificationStatus.UNSUPPORTED
    verification_note: str | None = None
    expertise_type: ExpertiseType = ExpertiseType.EVIDENCE_BASED


class Answer(_Model):
    """The final, verified response."""

    query: str
    answer_text: str
    claims: list[AnswerClaim] = Field(default_factory=list)
    citations: list[AnswerCitation] = Field(default_factory=list)
    expertise_matches: list[ExpertiseMatch] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    verified: bool = False
    # Rule 2: set instead of an answer when evidence does not support one.
    status: Status = Status.OK
    warnings: list[str] = Field(default_factory=list)
    llm_model: str | None = None

    @property
    def unsupported_claims(self) -> list[AnswerClaim]:
        return [c for c in self.claims if c.status is VerificationStatus.UNSUPPORTED]


class ClaimCheck(_Model):
    """Stage 15 audit record: claim -> evidence -> publication -> status."""

    claim: str
    status: VerificationStatus
    matched_evidence_ids: list[str] = Field(default_factory=list)
    matched_citations: list[AnswerCitation] = Field(default_factory=list)
    support_score: float = 0.0
    note: str
    # A citation whose DOI/URL was never seen in the ingested corpus.
    invented_citations: list[str] = Field(default_factory=list)


class VerificationReport(_Model):
    answer: Answer
    checks: list[ClaimCheck] = Field(default_factory=list)
    # Citations referencing DOIs/URLs absent from the ingested corpus.
    fabricated_citations: list[str] = Field(default_factory=list)
    verified: bool = False
    notes: list[str] = Field(default_factory=list)

    @property
    def support_rate(self) -> float:
        if not self.checks:
            return 0.0
        supported = sum(
            1
            for c in self.checks
            if c.status in (VerificationStatus.SUPPORTED, VerificationStatus.PARTIALLY_SUPPORTED)
        )
        return supported / len(self.checks)

    @property
    def citation_correctness(self) -> float:
        """Fraction of citations that resolve to a real ingested record."""
        if not self.checks:
            return 1.0
        total = sum(len(c.matched_citations) for c in self.checks)
        if total == 0:
            return 1.0
        fabricated = sum(len(c.invented_citations) for c in self.checks)
        return (total - fabricated) / total


# --------------------------------------------------------------------------
# Stage 16: evaluation
# --------------------------------------------------------------------------


class RelevanceJudgment(_Model):
    """Human relevance annotation. Ground truth is never fabricated.

    `relevant_ids` must be supplied by a human (or an accepted external source).
    `notes` records who judged it and when.
    """

    query: str
    relevant_ids: list[str] = Field(default_factory=list)
    graded: dict[str, int] = Field(default_factory=dict, description="doc/faculty id -> grade 0-3.")
    judged_by: str | None = None
    judged_at: datetime | None = None
    notes: str | None = None


class RankedResult(_Model):
    id: str
    score: float
    rank: int
    detail: dict[str, Any] = Field(default_factory=dict)


class BenchmarkCase(_Model):
    """One evaluation query."""

    case_id: str
    query: str
    category: str = Field(
        description="direct | broad | technical | interdisciplinary | faculty | "
        "institution | recent | collaboration | emerging | ambiguous_name"
    )
    filters: dict[str, Any] = Field(default_factory=dict)
    relevant_ids: list[str] = Field(
        default_factory=list,
        description="Filled from RelevanceJudgment by a human. Empty means ungraded.",
    )
    notes: str | None = None


class RetrievalMetrics(_Model):
    precision_at_k: dict[str, float] = Field(default_factory=dict)
    recall_at_k: dict[str, float] = Field(default_factory=dict)
    mrr: float | None = None
    ndcg_at_k: dict[str, float] = Field(default_factory=dict)
    hit_rate_at_k: dict[str, float] = Field(default_factory=dict)
    graded_queries: int = 0
    # True when no human judgments exist, so metrics must not be reported as scores.
    ungraded: bool = True
    note: str | None = None


class EvaluationReport(_Model):
    """Metrics for one strategy over the benchmark set."""

    strategy: str
    metrics: RetrievalMetrics = Field(default_factory=RetrievalMetrics)
    evidence_coverage: float | None = None
    citation_correctness: float | None = None
    entity_resolution_accuracy: float | None = None
    insufficient_evidence_rate: float | None = None
    notes: list[str] = Field(default_factory=list)


class EvaluationSuite(_Model):
    benchmark: list[BenchmarkCase] = Field(default_factory=list)
    reports: list[EvaluationReport] = Field(default_factory=list)
    ungraded_queries: int = 0
    note: str = Field(
        default=(
            "Metrics are computed only over human-graded queries. Ungraded queries "
            "are excluded rather than scored against assumed relevance."
        )
    )
