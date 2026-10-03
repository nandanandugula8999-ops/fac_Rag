"""Typed application settings.

Every tunable in the engine is declared here exactly once and read through
`get_settings()`. Nothing else in the codebase calls `os.environ` directly,
which keeps configuration auditable and makes the whole system describable
from a single object.

Values are resolved with this precedence (highest wins):

1. Explicit constructor arguments
2. Process environment variables (prefix `FR_`, groups nested with `__`)
3. The `.env` file at the project root
4. The defaults declared on each settings class
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PREFIX = "FR_"
ENV_NESTED_DELIMITER = "__"

# src/faculty_radar/config/settings.py -> parents[3] is the repository root.
PACKAGE_ROOT = Path(__file__).resolve().parents[3]


class _Base(BaseSettings):
    """Shared behaviour for every settings group."""

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_nested_delimiter=ENV_NESTED_DELIMITER,
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


class AppSettings(_Base):
    """Identity and runtime mode of the engine."""

    name: str = "Faculty Research Discovery Assistant"
    slug: str = "faculty-radar"
    env: Literal["local", "dev", "staging", "prod"] = "local"
    debug: bool = False
    version: str = "0.1.0"

    @property
    def is_production(self) -> bool:
        return self.env == "prod"


class PathsSettings(_Base):
    """Filesystem layout.

    All directories are anchored at `root` so the entire data lake can be
    relocated (e.g. onto a large scratch disk) with one environment variable.
    """

    root: Path = PACKAGE_ROOT
    data: Path | None = Field(
        default=None,
        description="Overrides <root>/data when set.",
    )
    logs: Path | None = Field(
        default=None,
        description="Overrides <root>/logs when set.",
    )

    @model_validator(mode="after")
    def _materialize(self) -> PathsSettings:
        if self.data is None:
            self.data = self.root / "data"
        if self.logs is None:
            self.logs = self.root / "logs"
        return self

    @property
    def env_file(self) -> Path:
        return self.root / ".env"


class LoggingSettings(_Base):
    """How the engine reports what it is doing.

    `json` is the right choice for anything machine-parsed (CI, log shipping);
    `text` is easier to read while developing.
    """

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    format: Literal["json", "text"] = "text"
    file_enabled: bool = True
    file_name: str = "faculty_radar.log"
    console_enabled: bool = True
    # Promotes third-party loggers (httpx, urllib3) to WARNING to cut noise.
    silence_third_party: bool = True


class OpenAlexSettings(_Base):
    """Credentials and politeness rules for the OpenAlex API.

    OpenAlex grants a faster, more reliable "polite pool" to callers who
    identify themselves with a mailto address. `api_key` is optional and only
    needed for higher rate limits.
    """

    base_url: str = "https://api.openalex.org"
    mailto: str | None = Field(
        default=None,
        description="Contact email for the OpenAlex polite pool.",
    )
    api_key: str | None = None
    timeout_seconds: float = 30.0
    max_retries: int = 3
    backoff_seconds: float = 1.5
    # Cursor pagination page size; 200 is OpenAlex's documented maximum.
    page_size: int = 200
    requests_per_second: float = 10.0


class CrossrefSettings(_Base):
    """Crossref metadata verification/enrichment for discovered publications.

    Crossref is strictly secondary: OpenAlex finds candidates, Crossref only
    confirms their DOIs and fills gaps (missing titles, years, landing URLs).
    Everything here fails open - a dead Crossref degrades to OpenAlex-only
    discovery, never to an error - and `enabled=False` skips it entirely.
    """

    enabled: bool = True
    base_url: str = "https://api.crossref.org"
    mailto: str | None = Field(
        default=None,
        description="Contact email for the Crossref polite pool (50 req/s).",
    )
    timeout_seconds: float = 8.0
    # Concurrent verification workers; I/O-bound, so threads are appropriate.
    max_workers: int = 8


class ScopeSettings(_Base):
    """Which institution's faculty the engine is allowed to reason about.

    Discovery is intentionally scoped: the engine only indexes faculty that
    have consented to be discoverable, and only inside the institutions listed
    here.
    """

    institution_names: list[str] = Field(default_factory=list)
    # OpenAlex institution identifiers, e.g. "I185315811".
    institution_ids: list[str] = Field(default_factory=list)
    # Comma/plus separated topic queries used to seed ingestion.
    topic_seeds: list[str] = Field(default_factory=list)
    require_consent: bool = True


class IngestionSettings(_Base):
    """How much of the source graph to pull, and how hard."""

    # Authors fetched per institution.
    max_authors: int = 500
    # Works fetched per author.
    max_works_per_author: int = 200
    # Cap on total works ingested per institution.
    max_works_total: int = 20_000
    cache_ttl_hours: int = 24
    # Pause between requests, honouring OpenAlex's rate limit.
    min_request_interval_seconds: float = 0.1
    # Only keep works with a reconstructed abstract / title we can cite.
    require_abstract: bool = False


class EmbeddingSettings(_Base):
    """Embedding backend and dimension.

    `hashing` is a deterministic, dependency-free hashed n-gram projection. It
    is NOT a neural semantic model: it is fast, offline, reproducible, and good
    enough to exercise and test the entire retrieval pipeline. Switch to
    `sentence-transformers` or `openai` for true semantic retrieval.
    """

    provider: Literal["hashing", "sentence-transformers", "openai"] = "hashing"
    model: str = "hashing-v1"
    dimension: int = 512
    batch_size: int = 64
    # Reuse vectors already on disk for unchanged document text.
    cache_enabled: bool = True
    max_tokens: int = 8192


class RetrievalSettings(_Base):
    """Candidate generation: BM25, vector, and hybrid fusion."""

    top_k: int = 20
    # BM25 term-frequency saturation and length normalization.
    bm25_k1: float = 1.5
    bm25_b: float = 0.75
    # Hybrid fusion: lexical_weight + semantic_weight == 1.0.
    lexical_weight: float = 0.5
    # Reciprocal-rank-fusion constant. Larger = flatter fusion.
    rrf_k: int = 60


class RankingSettings(_Base):
    """Reranking of the fused candidate set."""

    top_k: int = 20
    # RRF is robust when lexical and semantic scores are on different scales.
    method: Literal["rrf", "weighted"] = "rrf"
    rrf_k: int = 60
    # Field weights used when a query is matched against document fields.
    title_weight: float = 3.0
    abstract_weight: float = 1.0
    topic_weight: float = 2.5
    keyword_weight: float = 1.5


class ExpertiseSettings(_Base):
    """Signal weights for the expertise engine.

    Weights are normalized internally, so only their *relative* size matters.
    They are exposed here so the ranking is reproducible, inspectable, and
    tunable per institution without touching code.
    """

    # Relative weights for each explainable signal.
    weight_explicit_topic: float = 1.0
    weight_topic_evidence: float = 0.9
    weight_semantic: float = 0.7
    weight_keyword: float = 0.6
    weight_recency: float = 0.3
    weight_consistency: float = 0.4
    weight_citations: float = 0.2

    # A result below this is not shown at all.
    min_score: float = 0.05
    # Evidence-based expertise needs at least this many supporting works.
    min_publications_for_evidence: int = 1
    # "Research consistency" requires this fraction of works to be on-topic.
    consistency_window: int = 10
    # Recency half-life in years.
    recency_half_life_years: float = 5.0


class CollaborationSettings(_Base):
    """Co-authorship and complementary-expertise thresholds."""

    min_coauthored_works: int = 1
    # Jaccard overlap on topic sets below this means "complementary".
    complementarity_threshold: float = 0.15
    # Above this, two faculty are near-duplicates in topic space.
    same_area_threshold: float = 0.5
    max_pairs: int = 200


class TrendSettings(_Base):
    """Time-window analysis thresholds."""

    # Windows used for growth / decline comparison, in years.
    recent_years: int = 2
    baseline_years: int = 5
    # A topic must have at least this many publications to be reported at all.
    min_publications: int = 2
    # Percentage growth needed before calling a topic "emerging".
    emerging_growth_ratio: float = 1.5
    # Minimum absolute recent count; blocks small-number noise.
    min_recent_publications: int = 2


class EvidenceSettings(_Base):
    """Evidence selection before generation."""

    max_items: int = 8
    # Per-source-type caps so one prolific faculty cannot crowd out others.
    max_per_faculty: int = 3
    max_per_document: int = 3
    min_relevance: float = 0.1


class LlmSettings(_Base):
    """LLM provider boundary.

    `extractive` is the default: a deterministic, offline summarizer that can
    only restate retrieved evidence. It exists so the RAG path is testable and
    demoable without an API key, and so the system degrades to evidence-only
    output rather than to invention.

    `groq` is the cloud provider (server-side GROQ_API_KEY via FR_GROQ__API_KEY).
    `ollama` is stubbed for later local use and raises a clear error until wired.
    """

    provider: Literal["extractive", "groq", "ollama", "openai"] = "extractive"
    model: str = "extractive-v1"
    api_key: str | None = None
    base_url: str = "https://api.openai.com/v1"
    temperature: float = 0.0
    max_output_tokens: int = 700
    timeout_seconds: float = 60.0
    max_retries: int = 2
    cache_enabled: bool = True


class GroqSettings(_Base):
    """Groq cloud provider (server-side only).

    Key MUST come from backend env FR_GROQ__API_KEY. Never expose it via
    VITE_GROQ_API_KEY / NEXT_PUBLIC_GROQ_API_KEY or any frontend bundle.
    Default model is a Llama model per spec.
    """

    api_key: str | None = None
    model: str = "llama-3.1-8b-instant"
    base_url: str = "https://api.groq.com/openai/v1"
    temperature: float = 0.0
    max_tokens: int = 1000
    timeout_seconds: float = 60.0


class RagSettings(_Base):
    """Context assembly."""

    max_context_chars: int = 6000
    max_faculty_considered: int = 10
    # An answer is only generated if retrieval found at least this much evidence.
    min_evidence_score: float = 0.1


class VerificationSettings(_Base):
    """Post-generation citation checking."""

    # Token overlap above which a claim is considered backed by a passage.
    support_threshold: float = 0.34
    # A numeric claim (year, count, citation number) must match exactly.
    require_numeric_match: bool = True
    # Drop claims below this support level instead of flagging them.
    drop_below: Literal["unsupported", "partially_supported", "never"] = "unsupported"


class EvaluationSettings(_Base):
    """Retrieval and intelligence metrics."""

    k_values: list[int] = Field(default_factory=lambda: [1, 5, 10])
    # Report a metric as "not applicable" below this many judged items rather
    # than publishing a misleading number.
    min_graded_items: int = 3


class Settings(_Base):
    """Root settings object, the single entry point for configuration."""

    app: AppSettings = Field(default_factory=AppSettings)
    paths: PathsSettings = Field(default_factory=PathsSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    openalex: OpenAlexSettings = Field(default_factory=OpenAlexSettings)
    crossref: CrossrefSettings = Field(default_factory=CrossrefSettings)
    scope: ScopeSettings = Field(default_factory=ScopeSettings)
    ingestion: IngestionSettings = Field(default_factory=IngestionSettings)
    embeddings: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    ranking: RankingSettings = Field(default_factory=RankingSettings)
    expertise: ExpertiseSettings = Field(default_factory=ExpertiseSettings)
    collaboration: CollaborationSettings = Field(default_factory=CollaborationSettings)
    trends: TrendSettings = Field(default_factory=TrendSettings)
    evidence: EvidenceSettings = Field(default_factory=EvidenceSettings)
    llm: LlmSettings = Field(default_factory=LlmSettings)
    groq: GroqSettings = Field(default_factory=GroqSettings)
    rag: RagSettings = Field(default_factory=RagSettings)
    verification: VerificationSettings = Field(default_factory=VerificationSettings)
    evaluation: EvaluationSettings = Field(default_factory=EvaluationSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Cached so that the `.env` file is parsed once and every component agrees
    on the same configuration. Tests can call `get_settings.cache_clear()`.
    """
    return Settings()
