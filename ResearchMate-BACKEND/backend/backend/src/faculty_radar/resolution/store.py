"""Persistence of resolved identities and the human review queue.

Writes to `data/processed/`:

  researchers.jsonl  canonical identities, one per line
  decisions.jsonl    every pairwise verdict with its evidence
  review_queue.json  pairs a human must judge, with the evidence for each

The review queue is not optional bookkeeping. It is where every decision the
engine refused to make automatically ends up, so the burden of ambiguity falls
on a person who can resolve it rather than on a threshold nobody chose
deliberately.
"""

from __future__ import annotations

import json
from pathlib import Path

from faculty_radar.models import CanonicalResearcher, ResolutionDecision
from faculty_radar.paths import DataPaths, build_paths
from faculty_radar.resolution.resolver import ResolutionReport


class ResolvedStore:
    def __init__(self, paths: DataPaths | None = None) -> None:
        self.paths = (paths or build_paths()).ensure()

    def _path(self, name: str) -> Path:
        return self.paths.processed / f"{name}.jsonl"

    def _write(self, name: str, records: list[dict]) -> Path:
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, default=str) + "\n")
        tmp.replace(path)
        return path

    def write(self, report: ResolutionReport) -> dict[str, Path]:
        written = {
            "researchers": self._write(
                "researchers",
                [r.model_dump(mode="json") for r in report.researchers],
            ),
            "decisions": self._write(
                "decisions", [d.model_dump(mode="json") for d in report.decisions]
            ),
        }

        review_path = self.paths.processed / "review_queue.json"
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.write_text(
            json.dumps(
                {
                    "note": (
                        "Pairs the engine would not merge automatically. Each entry "
                        "carries the signals it was judged on. Resolve by supplying "
                        "an ORCID or explicit confirmation, not by loosening thresholds."
                    ),
                    "count": len(report.needs_review),
                    "pairs": [d.model_dump(mode="json") for d in report.needs_review],
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        written["review_queue"] = review_path
        return written

    def load_researchers(self) -> list[CanonicalResearcher]:
        return [CanonicalResearcher.model_validate(r) for r in self._read("researchers")]

    def load_decisions(self) -> list[ResolutionDecision]:
        return [ResolutionDecision.model_validate(r) for r in self._read("decisions")]

    def _read(self, name: str) -> list[dict]:
        path = self._path(name)
        if not path.exists():
            return []
        records: list[dict] = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return records

    def load_review_queue(self) -> list[dict]:
        path = self.paths.processed / "review_queue.json"
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8")).get("pairs", [])
