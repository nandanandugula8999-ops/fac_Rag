"""Disk cache for generated answers.

Keyed by model, query, and the exact evidence set, so a cache hit can only
replay an answer generated from identical inputs. Evidence edits, query edits,
and model changes all miss the cache by construction.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from faculty_radar.models import Answer, EvidenceItem
from faculty_radar.paths import DataPaths, build_paths


def cached_answer_key(model: str, query: str, evidence: list[EvidenceItem]) -> str:
    """Stable cache key covering everything the answer depends on."""
    payload = {
        "model": model,
        "query": query,
        "evidence": [(item.evidence_id, item.quote, item.source_url) for item in evidence],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


class LlmCache:
    """JSON answer cache under `paths.cache/llm/`."""

    def __init__(self, paths: DataPaths | None = None) -> None:
        self.paths = paths or build_paths()

    @property
    def cache_dir(self) -> Path:
        return self.paths.cache / "llm"

    def get(self, key: str) -> Answer | None:
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            return Answer.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return None

    def set(self, key: str, answer: Answer) -> Path:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / f"{key}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(answer.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)
        return path
