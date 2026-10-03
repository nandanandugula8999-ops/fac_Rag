"""Interim store and normalization orchestration.

Writes normalized records to `data/interim/`. The store is *not* append-only in
the way `raw/` is: normalized output is a derived artifact that should be
regenerated whenever rules change, so each run rewrites the file atomically.
`raw/` remains the immutable record of what the source actually said.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from faculty_radar.config import Settings, get_logger, get_settings
from faculty_radar.ingestion.store import RawStore
from faculty_radar.models import NormalizedAuthor, NormalizedWork
from faculty_radar.normalization.authors import normalize_author
from faculty_radar.normalization.works import normalize_work
from faculty_radar.paths import DataPaths, build_paths

logger = get_logger(__name__)


@dataclass
class NormalizationResult:
    authors_in: int = 0
    authors_out: int = 0
    works_in: int = 0
    works_out: int = 0
    works_without_abstract: int = 0
    works_without_title: int = 0
    authors_dropped: list[str] = field(default_factory=list)
    works_dropped: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "authors_in": self.authors_in,
            "authors_out": self.authors_out,
            "works_in": self.works_in,
            "works_out": self.works_out,
            "works_without_abstract": self.works_without_abstract,
            "works_without_title": self.works_without_title,
        }


class InterimStore:
    """Normalized records under `data/interim/`, rewritten atomically per run."""

    def __init__(self, paths: DataPaths | None = None) -> None:
        self.paths = (paths or build_paths()).ensure()

    def _path(self, name: str) -> Path:
        return self.paths.interim / f"{name}.jsonl"

    def write(self, name: str, records: list[dict[str, Any]]) -> Path:
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, default=str) + "\n")
        # Atomic replace: a crashed run leaves the previous good file in place.
        tmp.replace(path)
        return path

    def read(self, name: str) -> list[dict[str, Any]]:
        path = self._path(name)
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return records

    def load_authors(self) -> list[NormalizedAuthor]:
        return [NormalizedAuthor.model_validate(r) for r in self.read("authors")]

    def load_works(self) -> list[NormalizedWork]:
        return [NormalizedWork.model_validate(r) for r in self.read("works")]


def _retrieved_at(envelope: dict[str, Any]) -> datetime | None:
    """Parse the fetch timestamp the raw store recorded for this record."""
    raw_value = envelope.get("retrieved_at")
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(str(raw_value))
    except ValueError:
        return None


def normalize_all(
    raw: RawStore | None = None,
    settings: Settings | None = None,
    paths: DataPaths | None = None,
    *,
    store: InterimStore | None = None,
) -> NormalizationResult:
    """Normalize every raw snapshot into the interim store.

    Each output record inherits the fetch timestamp and raw path of the snapshot
    it came from, so provenance describes the *source* rather than this run, and
    re-running normalization on unchanged input is a no-op.
    """
    settings = settings or get_settings()
    paths = paths or build_paths(settings)
    raw = raw or RawStore(paths, source="openalex")
    store = store or InterimStore(paths)

    raw_authors = raw.read("author")
    raw_works = raw.read("work")
    result = NormalizationResult(authors_in=len(raw_authors), works_in=len(raw_works))

    author_records = [
        normalize_author(
            envelope["payload"],
            raw_path=raw.raw_path_for("author", "author"),
            retrieved_at=_retrieved_at(envelope),
            source_url=envelope.get("source_url"),
        )
        for envelope in raw_authors
    ]
    authors = [a for a in author_records if a is not None]
    result.authors_out = len(authors)
    result.authors_dropped = [
        str(e.get("id"))
        for e in raw_authors
        if str(e.get("payload", {}).get("id", "")).rsplit("/", 1)[-1]
        not in {a.openalex_id for a in authors}
    ]
    store.write("authors", [a.model_dump(mode="json") for a in authors])

    work_records = [
        normalize_work(
            envelope["payload"],
            raw_path=raw.raw_path_for("work", "work"),
            retrieved_at=_retrieved_at(envelope),
            source_url=envelope.get("source_url"),
        )
        for envelope in raw_works
    ]
    works = [w for w in work_records if w is not None]
    result.works_out = len(works)
    result.works_dropped = [
        str(e.get("id"))
        for e in raw_works
        if str(e.get("payload", {}).get("id", "")).rsplit("/", 1)[-1]
        not in {w.openalex_id for w in works}
    ]
    result.works_without_abstract = sum(1 for w in works if not w.abstract)
    result.works_without_title = sum(1 for w in works if not w.title)
    store.write("works", [w.model_dump(mode="json") for w in works])

    logger.info("normalization complete", extra=result.as_dict())
    return result
