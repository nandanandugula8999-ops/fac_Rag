# Faculty Research Discovery Assistant

A research intelligence engine that finds faculty by research topic, and can
show its work.

The goal is not a chatbot over faculty data. It is a pipeline that produces a
**ranked, filterable, evidence-backed** answer to *"who at this institution
knows about X?"* — where every result states whether the expertise was
**explicitly declared** by the faculty member or **inferred** from publication
content, and every claim points back to a real publication with a resolvable
citation.

---

## Status

**Stage 1 of 16 — foundation only.** Configuration, logging, environment
handling, data directory layout, and a diagnostic CLI.

Nothing is ingested, indexed, or retrieved yet. That is deliberate: the
foundation is the part that is expensive to retrofit, so it gets built and
verified first.

| # | Stage | Package | Status |
|---|-------|---------|--------|
| 1 | Ingestion | `ingestion/` | planned |
| 2 | Cleaning + normalization | `normalization/` | planned |
| 3 | Researcher entity resolution | `resolution/` | planned |
| 4 | Faculty ↔ publication linking | `linking/` | planned |
| 5 | Knowledge graph | `graph/` | planned |
| 6 | Research corpus | `corpus/` | planned |
| 7 | Embeddings + vector index | `embeddings/` | planned |
| 8 | Hybrid retrieval (BM25 + semantic) | `retrieval/` | planned |
| 9 | Reranking | `ranking/` | planned |
| 10 | Expertise engine | `expertise/` | planned |
| 11 | Collaboration engine | `collaboration/` | deferred |
| 12 | Research trend engine | `trends/` | deferred |
| 13 | RAG | `rag/` | planned |
| 14 | LLM access | `llm/` | planned |
| 15 | Evidence + citation verification | `verification/` | planned |
| 16 | API | `api/` | planned |

The `collaboration/` and `trends/` packages exist as documented stubs so the
graph layer is built with the edges they will need. They are intentionally
empty of logic.

---

## Why this architecture

Three requirements drove the design, and each one rules out the obvious
shortcut:

**"Distinguish explicitly stated expertise from inferred similarity."**
A single similarity score cannot express this. So corpus text is tagged by
provenance at construction time (`corpus/`), retrievers report which signal
produced a hit (`retrieval/`), and the expertise engine keeps the two signals
in separate fields (`expertise/`) instead of summing them into one number.

**"Handle duplicate or ambiguous researcher names."**
This is an entity resolution problem, not a retrieval problem. It is stage 3,
it runs *before* any ranking happens, and every merge keeps its supporting
evidence. A wrong identity merge silently corrupts every downstream result,
which is why it gets its own stage rather than being handled as a lookup tweak.

**"Provide supporting publications and citations."**
Evidence must be a first-class output of every stage that touches relevance,
not something reconstructed from a prompt at the end. Passages keep their DOI
and source URL from `linking/` onward, and `verification/` re-checks them
after generation rather than trusting the prompt to have done so.

---

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -e ".[dev]"

fr env --create     # write .env from .env.example
fr doctor           # validate configuration
fr paths --ensure   # create the data directory layout
```

Requires Python 3.11+.

---

## Configuration

Configuration is declared once, in
`src/faculty_radar/config/settings.py`, as typed Pydantic models. No other
module reads `os.environ` directly, so the entire system's behaviour is
describable from a single object and validated at startup rather than at the
moment something fails three stages deep.

**Precedence** — explicit arguments beat environment variables, which beat
`.env`, which beats the declared defaults. The engine boots with no `.env` at
all; it just runs on defaults and `fr doctor` tells you what to fix.

**Naming** — `FR_<GROUP>__<FIELD>`, with `__` separating nested groups:

```
FR_LOGGING__LEVEL=DEBUG          -> settings.logging.level
FR_OPENALEX__MAILTO=a@b.edu      -> settings.openalex.mailto
FR_SCOPE__INSTITUTION_IDS=[...]   -> settings.scope.institution_ids
```

**Settings groups** — `app` (identity, environment, debug mode), `paths`
(data lake location, relocatable via one variable), `logging` (level, format,
sinks), `openalex` (credentials and rate limits), `scope` (which institutions
and topics are in bounds, and the consent gate).

Inspect what resolved, with secrets redacted:

```powershell
fr env
```

---

## Logging

Standard-library `logging` with a small custom JSON formatter rather than a
third-party logging dependency — the stdlib already covers handlers, levels,
and propagation, and structured output is a formatter, not a package.

Two sinks: a readable console for development, and a rotating JSON Lines file
in `logs/` for analysis. File logs stay JSON even when the console is
human-readable, so pipeline runs can be inspected later without re-running
anything.

```powershell
fr --log-level DEBUG --log-format json paths
```

Emit structured fields from any module:

```python
from faculty_radar.config import get_logger

logger = get_logger(__name__)
logger.info("authors fetched", extra={"count": 42, "cursor": "abc"})
```

Modules get a logger with `get_logger(__name__)`. Only the CLI calls
`configure_logging()`, once, at startup.

---

## Project structure

```
faculty-radar/
├── pyproject.toml            Package metadata, dependencies, lint/test config
├── .env.example              Documented environment template
├── README.md
│
├── src/faculty_radar/
│   ├── __init__.py           Public API surface for the package
│   ├── cli.py                `fr` entrypoint: doctor / paths / env
│   ├── paths.py              Single source of truth for the data layout
│   ├── config/               ── FOUNDATION ──
│   │   ├── settings.py       Typed settings; the only os.environ reader
│   │   └── logging.py        Logging setup, text + JSON formatters
│   │
│   ├── ingestion/            ── PIPELINE ──
│   ├── normalization/        Cleaning, vocab + identifier normalization
│   ├── resolution/           Researcher entity resolution, homonym handling
│   ├── linking/              Faculty ↔ publication linking with confidence
│   ├── graph/                Research knowledge graph
│   ├── corpus/               Chunked retrievable text with provenance
│   ├── embeddings/           Embeddings + vector index
│   ├── retrieval/            BM25, semantic, and hybrid retrieval
│   ├── ranking/              Reranking of the candidate set
│   ├── expertise/            Stated vs inferred expertise, ranked faculty
│   ├── collaboration/        (deferred) co-authorship networks
│   ├── trends/               (deferred) topic trajectories
│   ├── rag/                  Grounded context assembly
│   ├── llm/                  Provider boundary, prompts, caching
│   ├── verification/         Evidence + citation checking
│   └── api/                  Public API surface
│
├── data/                     ── DATA LAKE ──
│   ├── raw/                  Immutable source snapshots (append-only)
│   ├── interim/              Normalized, not yet entity-resolved
│   ├── processed/            Entity-resolved, publication-linked records
│   ├── corpus/               Chunked text awaiting embedding
│   ├── vectors/              Vector index files
│   ├── graph/                Knowledge-graph nodes and edges
│   ├── cache/                Disposable HTTP and LLM response cache
│   └── exports/              CSV/JSON for API and CLI consumers
│
├── logs/                     Rotating JSON application logs
├── tests/                    Pytest suite
├── scripts/                  One-off operational and backfill scripts
└── docs/                     Architecture notes and pipeline stage notes
```

### Why `src/` layout

Forces the package to be imported rather than accidentally picked up from the
working directory, so tests exercise the installed package the same way
production will. It also keeps the repository root clean — nothing to import
means nothing to shadow.

### Why each pipeline stage is its own package

The pipeline is a sequence of transformations with different failure modes,
different rates of change, and different owners. Separating them means:

- a stage can be rebuilt from the previous stage's output without rerunning
  everything upstream
- a bug in reranking cannot corrupt ingested raw data
- stages 11 and 12 can be deferred without leaving broken imports
- contracts between stages (schemas, provenance) become explicit rather than
  implicit in function signatures

Each package carries a docstring stating what it must do **and what it must
not do**. The negative constraints are the ones that matter: `resolution/`
must not lose merge evidence, `raw/` must never be rewritten, `expertise/`
must not merge stated and inferred into a single score.

### Why `data/` is a medallion layout

`raw → interim → processed → corpus/vectors` mirrors how far a record has been
enriched. Each directory has exactly one writing stage, which means a stage can
be rewritten without reasoning about who else touches its files, and the whole
lake can be deleted and rebuilt from `raw/` alone.

`raw/` is treated as immutable. Cleaning happens in `interim/`. This is what
makes "we can re-run normalization with different rules" a safe thing to say.

---

## Dependency policy

Stage 1 runtime dependencies are **pydantic** and **pydantic-settings**, and
nothing else. Both come from the same author and install together, so this is
two libraries, not an ecosystem.

Not yet added, and not added speculatively: HTTP client, database driver,
vector store, embedding model, ranker, web framework. Each will be chosen when
its stage is built, against what that stage actually needs. A chatbot or simple
RAG application would have pulled in an LLM client, a vector database, and a web
framework on day one — all of which are downstream of decisions that this
project has not made yet.

Development dependencies are `pytest` and `ruff`.

---

## Next stage

**Stage 2 — ingestion.** The first stage that writes real data.

- `ingestion/openalex.py`: paginated OpenAlex client with rate limiting,
  retries, and request logging
- raw snapshots to `data/raw/openalex/` as JSON Lines, with fetch metadata
- cache HTTP responses in `data/cache/` so re-runs are free
- `fr ingest` wired into the CLI, driven by `scope.institution_ids`

The contract for this stage is that nothing in `raw/` is ever modified, and
every record can be traced back to the URL and timestamp that produced it.
