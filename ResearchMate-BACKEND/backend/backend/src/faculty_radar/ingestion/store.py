"""Append-only raw snapshot store.

Rule 1 (preserve provenance) is only meaningful if the source records survive
untouched. This store therefore:

  * only ever appends, never rewrites or deletes a record
  * writes each record together with the request that produced it
  * dedupes by source id on append, so re-ingesting is idempotent
  * exposes the raw payload so later stages can be audited against it

Reading a snapshot returns the *original* payload, not a normalized form.
Normalization happens in `faculty_radar.normalization`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from faculty_radar.config import get_logger
from faculty_radar.paths import DataPaths, build_paths

logger = get_logger(__name__)

# Entity types this store knows how to persist.
ENTITIES = ("institution", "author", "work", "topic")


class RawStore:
    """JSON Lines snapshots under `data/raw/<source>/<entity>.jsonl`."""

    def __init__(
        self,
        paths: DataPaths | None = None,
        *,
        source: str = "openalex",
    ) -> None:
        self.paths = (paths or build_paths()).ensure()
        self.source = source
        self._seen: dict[str, set[str]] = {}

    # ------------------------------------------------------------------ paths

    def directory(self) -> Path:
        return self.paths.raw / self.source

    def path_for(self, entity: str) -> Path:
        if entity not in ENTITIES:
            raise ValueError(f"unknown entity type {entity!r}; expected one of {ENTITIES}")
        return self.directory() / f"{entity}.jsonl"

    # ----------------------------------------------------------------- writing

    def append(
        self,
        entity: str,
        payload: dict[str, Any],
        *,
        source_url: str | None = None,
        retrieved_at: datetime | None = None,
    ) -> bool:
        """Append one record. Returns False if this id was already stored.

        The envelope keeps the fetch context next to the payload, so a record
        is self-describing once detached from the request that created it.
        """
        record_id = str(payload.get("id") or "").strip()
        if not record_id:
            raise ValueError(f"{entity} payload has no 'id'; cannot store it traceably")

        seen = self._seen.setdefault(entity, self._load_ids(entity))
        if record_id in seen:
            return False

        envelope = {
            "id": record_id,
            "source": self.source,
            "source_url": source_url or f"{self.source}:{entity}:{record_id}",
            "retrieved_at": (retrieved_at or datetime.now(UTC)).isoformat(),
            "payload": payload,
        }

        path = self.path_for(entity)
        path.parent.mkdir(parents=True, exist_ok=True)
        # "a" is append-only by construction, not by convention.
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(envelope, default=str) + "\n")
        seen.add(record_id)
        return True

    def append_many(self, entity: str, payloads: list[dict[str, Any]]) -> int:
        return sum(1 for payload in payloads if self.append(entity, payload))

    # ----------------------------------------------------------------- reading

    def _load_ids(self, entity: str) -> set[str]:
        path = self.path_for(entity)
        if not path.exists():
            return set()
        ids: set[str] = set()
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    ids.add(str(json.loads(line)["id"]))
                except (json.JSONDecodeError, KeyError) as exc:
                    logger.warning(
                        "skipping malformed raw record", extra={"entity": entity, "error": str(exc)}
                    )
        return ids

    def read(self, entity: str) -> list[dict[str, Any]]:
        """All payloads for an entity, in insertion order."""
        path = self.path_for(entity)
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records

    def iter_payloads(self, entity: str):
        """Yield raw payloads without envelope."""
        for record in self.read(entity):
            yield record.get("payload", {})

    def ids(self, entity: str) -> set[str]:
        return set(self._seen.get(entity) or self._load_ids(entity))

    def count(self, entity: str) -> int:
        return len(self.ids(entity))

    def raw_path_for(self, entity: str, record_id: str) -> str | None:
        """Where a specific record lives, for provenance annotation."""
        path = self.path_for(entity)
        if not path.exists():
            return None
        return str(path.relative_to(self.paths.root))

    def stats(self) -> dict[str, int]:
        return {entity: self.count(entity) for entity in ENTITIES}
