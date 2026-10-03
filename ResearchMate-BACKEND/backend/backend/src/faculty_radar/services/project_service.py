"""Project models (plan.md sections 18/20).

Firestore wiring comes later (Junior 3 track); this module defines the
backend contract now so frontend builds against a stable shape. Storage is an
in-memory registry per process — sufficient for demo, replaced by Firestore
without changing route signatures.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field


class Project(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str
    idea: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    search_history: list[str] = Field(default_factory=list)
    saved_papers: list[dict] = Field(default_factory=list)
    selected_faculty: list[dict] = Field(default_factory=list)
    gaps: list[dict] = Field(default_factory=list)
    plan: dict | None = None
    draft: dict | None = None


_REGISTRY: dict[str, Project] = {}


def create_project(title: str, idea: str = "") -> Project:
    p = Project(title=title or idea[:60] or "Untitled research", idea=idea)
    _REGISTRY[p.id] = p
    return p


def get_project(pid: str) -> Project | None:
    return _REGISTRY.get(pid)


def list_projects() -> list[Project]:
    return sorted(_REGISTRY.values(), key=lambda p: p.updated_at, reverse=True)


def update_project(pid: str, patch: dict) -> Project | None:
    p = _REGISTRY.get(pid)
    if not p:
        return None
    data = p.model_dump()
    for k, v in patch.items():
        if k in data and k not in ("id", "created_at"):
            data[k] = v
    data["updated_at"] = datetime.now(UTC)
    updated = Project.model_validate(data)
    _REGISTRY[pid] = updated
    return updated


def delete_project(pid: str) -> bool:
    return _REGISTRY.pop(pid, None) is not None
