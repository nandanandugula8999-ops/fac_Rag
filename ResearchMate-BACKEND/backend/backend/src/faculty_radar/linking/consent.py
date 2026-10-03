"""Consent registry: the gate on faculty discoverability.

Faculty expertise data is personal. A person who has not opted in must not be
findable through this system, and the safest way to guarantee that is to make
the unconsented state *absent* rather than *filtered*: no registry entry means
no `FacultyProfile`, which means nothing downstream - corpus, retrieval,
ranking, API, LLM - can ever see that person.

The registry is intentionally explicit and human-curated:

    {
      "entries": [
        {
          "researcher_id": "A100000001",
          "consented": true,
          "stated_topics": ["Graph Neural Networks"],
          "stated_project_descriptions": ["Molecular property prediction"],
          "contact_email": "wzhang@northgate.edu",
          "consented_at": "2026-01-15",
          "reviewed_by": "research-office"
        }
      ]
    }

`stated_topics` is the *only* source of STATED expertise in this pipeline.
OpenAlex author topics are derived from a person's publications, so treating
them as stated would be exactly the conflation Rule 3 forbids.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from faculty_radar.config import Settings, get_logger, get_settings
from faculty_radar.models import Topic
from faculty_radar.paths import DataPaths, build_paths

logger = get_logger(__name__)

DEFAULT_REGISTRY_NAME = "consent.json"


class ConsentEntry:
    """One person's recorded consent decision."""

    __slots__ = (
        "consented",
        "consented_at",
        "contact_email",
        "researcher_id",
        "reviewed_by",
        "stated_project_descriptions",
        "stated_topics",
    )

    def __init__(
        self,
        researcher_id: str,
        consented: bool,
        stated_topics: list[str] | None = None,
        stated_project_descriptions: list[str] | None = None,
        contact_email: str | None = None,
        consented_at: str | None = None,
        reviewed_by: str | None = None,
    ) -> None:
        self.researcher_id = researcher_id
        self.consented = consented
        self.stated_topics = stated_topics or []
        self.stated_project_descriptions = stated_project_descriptions or []
        self.contact_email = contact_email
        self.consented_at = consented_at
        self.reviewed_by = reviewed_by

    def topic_models(self) -> list[Topic]:
        return [Topic(name=name, share=1.0) for name in self.stated_topics if name]

    @classmethod
    def from_dict(cls, payload: dict) -> ConsentEntry | None:
        researcher_id = str(payload.get("researcher_id") or "").strip()
        if not researcher_id:
            return None
        topics = payload.get("stated_topics") or []
        descriptions = payload.get("stated_project_descriptions") or []
        return cls(
            researcher_id=researcher_id,
            consented=bool(payload.get("consented", False)),
            stated_topics=[str(t) for t in topics if t],
            stated_project_descriptions=[str(d) for d in descriptions if d],
            contact_email=payload.get("contact_email"),
            consented_at=payload.get("consented_at"),
            reviewed_by=payload.get("reviewed_by"),
        )


class ConsentRegistry:
    """Lookup of who has consented to being discoverable."""

    def __init__(
        self,
        entries: dict[str, ConsentEntry] | None = None,
        *,
        enforce: bool = True,
    ) -> None:
        self._entries = entries or {}
        # When enforcement is off this is a deliberate, explicit opt-out used
        # only for local development against synthetic data. `fr doctor` treats a
        # disabled consent gate as a blocking problem.
        self.enforce = enforce

    def __len__(self) -> int:
        return len(self._entries)

    def is_consented(self, researcher_id: str) -> bool:
        if not self.enforce:
            return True
        entry = self._entries.get(researcher_id)
        return bool(entry and entry.consented)

    def get(self, researcher_id: str) -> ConsentEntry | None:
        return self._entries.get(researcher_id)

    def stated_topics(self, researcher_id: str) -> list[Topic]:
        entry = self._entries.get(researcher_id)
        return entry.topic_models() if entry else []

    def project_descriptions(self, researcher_id: str) -> list[str]:
        entry = self._entries.get(researcher_id)
        return list(entry.stated_project_descriptions) if entry else []

    @property
    def consented_ids(self) -> set[str]:
        return {rid for rid, entry in self._entries.items() if entry.consented}

    @classmethod
    def from_file(cls, path: Path, *, enforce: bool = True) -> ConsentRegistry:
        if not path.exists():
            logger.warning(
                "no consent registry found; no faculty will be discoverable",
                extra={"path": str(path)},
            )
            return cls(enforce=enforce)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.error(
                "consent registry is not valid JSON; treating as empty",
                extra={"error": str(exc)},
            )
            return cls(enforce=enforce)

        entries: dict[str, ConsentEntry] = {}
        for raw in payload.get("entries", []):
            entry = ConsentEntry.from_dict(raw)
            if entry is not None:
                entries[entry.researcher_id] = entry
        return cls(entries, enforce=enforce)

    def write(self, path: Path) -> Path:
        """Write the registry back, for tests and operator tooling."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "entries": [
                {
                    "researcher_id": entry.researcher_id,
                    "consented": entry.consented,
                    "stated_topics": entry.stated_topics,
                    "stated_project_descriptions": entry.stated_project_descriptions,
                    "contact_email": entry.contact_email,
                    "consented_at": entry.consented_at,
                    "reviewed_by": entry.reviewed_by,
                }
                for entry in sorted(self._entries.values(), key=lambda e: e.researcher_id)
            ]
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path


def registry_path(settings: Settings | None = None, paths: DataPaths | None = None) -> Path:
    paths = paths or build_paths(settings or get_settings())
    return paths.processed / DEFAULT_REGISTRY_NAME


def load_consent_registry(
    settings: Settings | None = None,
    paths: DataPaths | None = None,
    *,
    enforce: bool | None = None,
) -> ConsentRegistry:
    settings = settings or get_settings()
    enforce = settings.scope.require_consent if enforce is None else enforce
    return ConsentRegistry.from_file(registry_path(settings, paths), enforce=enforce)


def today() -> str:
    return date.today().isoformat()
