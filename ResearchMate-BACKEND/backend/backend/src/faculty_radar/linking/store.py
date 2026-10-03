"""Persistence of faculty profiles.

Writes to `data/processed/`:

  faculty.jsonl       consented profiles with linked publications
  institutions.jsonl  institutions observed in scope
"""

from __future__ import annotations

import json
from pathlib import Path

from faculty_radar.models import FacultyProfile, Institution
from faculty_radar.paths import DataPaths, build_paths


class FacultyStore:
    def __init__(self, paths: DataPaths | None = None) -> None:
        self.paths = (paths or build_paths()).ensure()

    def _path(self, name: str) -> Path:
        return self.paths.processed / name

    def _write(self, name: str, records: list[dict]) -> Path:
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, default=str) + "\n")
        tmp.replace(path)
        return path

    def write_profiles(self, profiles: list[FacultyProfile]) -> Path:
        return self._write("faculty.jsonl", [p.model_dump(mode="json") for p in profiles])

    def write_institutions(self, institutions: dict[str, Institution]) -> Path:
        return self._write(
            "institutions.jsonl",
            [i.model_dump(mode="json") for i in institutions.values()],
        )

    def load_profiles(self) -> list[FacultyProfile]:
        path = self._path("faculty.jsonl")
        if not path.exists():
            return []
        profiles: list[FacultyProfile] = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    profiles.append(FacultyProfile.model_validate(json.loads(line)))
                except (json.JSONDecodeError, ValueError):
                    continue
        return profiles

    def load_institutions(self) -> list[Institution]:
        path = self._path("institutions.jsonl")
        if not path.exists():
            return []
        records: list[Institution] = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    try:
                        records.append(Institution.model_validate(json.loads(line)))
                    except (json.JSONDecodeError, ValueError):
                        continue
        return records
