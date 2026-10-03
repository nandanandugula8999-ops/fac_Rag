"""Data directory layout.

A single source of truth for where every artifact lives. Pipeline stages
import `paths()` instead of joining strings, so relocating the data lake is a
configuration change rather than a refactor.

The layout follows a medallion-style progression: each directory is owned by
exactly one pipeline stage and holds only that stage's output.

    raw/         ingestion         immutable API snapshots, never rewritten
    interim/     normalization     cleaned + normalized records, not yet linked
    processed/   linking           entity-resolved, publication-linked records
    corpus/      corpus            chunked text destined for embeddings
    vectors/     embeddings        vector index files
    graph/       graph             knowledge-graph nodes and edges
    cache/       any stage         disposable HTTP / LLM response cache
    exports/     any stage         human- and API-facing CSV/JSON outputs
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from faculty_radar.config.settings import Settings, get_settings


@dataclass(frozen=True, slots=True)
class DataPaths:
    """Absolute paths to every directory in the data lake."""

    root: Path
    raw: Path
    interim: Path
    processed: Path
    corpus: Path
    vectors: Path
    graph: Path
    cache: Path
    exports: Path
    logs: Path

    @property
    def all_dirs(self) -> tuple[Path, ...]:
        return (
            self.raw,
            self.interim,
            self.processed,
            self.corpus,
            self.vectors,
            self.graph,
            self.cache,
            self.exports,
            self.logs,
        )

    def sub(self, base: Path, *parts: str) -> Path:
        """Build a path inside a base directory, e.g. `paths.sub(paths.raw, 'authors')`."""
        return base.joinpath(*parts)

    def ensure(self) -> DataPaths:
        """Create every directory if missing. Safe to call repeatedly."""
        for directory in (*self.all_dirs, self.root):
            directory.mkdir(parents=True, exist_ok=True)
        return self

    def describe(self) -> list[tuple[str, str, Path]]:
        """Return (label, purpose, path) rows for `fr paths` and the README."""
        return [
            ("raw", "immutable source snapshots", self.raw),
            ("interim", "normalized, unlinked records", self.interim),
            ("processed", "entity-resolved, publication-linked records", self.processed),
            ("corpus", "chunked text for embedding", self.corpus),
            ("vectors", "vector index files", self.vectors),
            ("graph", "knowledge-graph nodes and edges", self.graph),
            ("cache", "disposable HTTP and LLM cache", self.cache),
            ("exports", "CSV/JSON outputs for API and CLI", self.exports),
            ("logs", "application logs", self.logs),
        ]


def build_paths(settings: Settings | None = None) -> DataPaths:
    """Construct `DataPaths` from settings without touching the filesystem."""
    settings = settings or get_settings()
    data = settings.paths.data
    logs = settings.paths.logs
    assert data is not None and logs is not None  # guaranteed by PathsSettings

    return DataPaths(
        root=settings.paths.root,
        raw=data / "raw",
        interim=data / "interim",
        processed=data / "processed",
        corpus=data / "corpus",
        vectors=data / "vectors",
        graph=data / "graph",
        cache=data / "cache",
        exports=data / "exports",
        logs=logs,
    )


@lru_cache(maxsize=1)
def paths() -> DataPaths:
    """Return the process-wide paths singleton."""
    return build_paths()
