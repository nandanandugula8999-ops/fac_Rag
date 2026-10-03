"""HTTP response cache for source API calls.

Ingestion is the most expensive stage to re-run, so responses are cached on
disk keyed by request. This makes re-runs cheap, makes tests hermetic without
network access, and makes ingestion reproducible.

The cache is deliberately *not* part of `raw/`: a cache entry is a transport
detail, not a source snapshot. `raw/` remains the immutable record.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from faculty_radar.config import get_logger

logger = get_logger(__name__)

# Fields that must never be written to disk in a cache key or payload.
_SECRET_KEYS = frozenset({"api_key", "mailto"})


def make_cache_key(method: str, url: str, params: dict[str, Any] | None = None) -> str:
    """Stable key for a request.

    Secrets are excluded from the key so rotating an API key does not
    invalidate the cache, but the value is never persisted.
    """
    safe_params = {k: v for k, v in sorted((params or {}).items()) if k not in _SECRET_KEYS}
    material = json.dumps([method.upper(), url, safe_params], sort_keys=True, default=str)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class ResponseCache:
    """Filesystem cache with TTL. Safe to use when disabled."""

    def __init__(
        self,
        directory: Path,
        *,
        ttl_hours: int = 24,
        enabled: bool = True,
    ) -> None:
        self.directory = directory
        self.ttl = timedelta(hours=ttl_hours)
        self.enabled = enabled
        self.hits = 0
        self.misses = 0

    def _path(self, key: str) -> Path:
        # Two-level fan-out keeps directories small on Windows filesystems.
        return self.directory / key[:2] / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        path = self._path(key)
        if not path.exists():
            self.misses += 1
            return None
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "cache entry unreadable, treating as miss", extra={"key": key, "error": str(exc)}
            )
            self.misses += 1
            return None

        fetched_at = datetime.fromisoformat(envelope["fetched_at"])
        if datetime.now(UTC) - fetched_at > self.ttl:
            self.misses += 1
            return None

        self.hits += 1
        return envelope["payload"]

    def put(self, key: str, payload: dict[str, Any]) -> None:
        if not self.enabled:
            return
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        envelope = {
            "fetched_at": datetime.now(UTC).isoformat(),
            "payload": payload,
        }
        # Write-then-rename so a crash never leaves a half-written entry.
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(envelope, default=str), encoding="utf-8")
        tmp.replace(path)

    def get_stats(self) -> dict[str, int]:
        total = self.hits + self.misses
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 3) if total else 0.0,
        }

    def clear(self) -> None:
        if not self.directory.exists():
            return
        for path in self.directory.rglob("*.json"):
            path.unlink()
