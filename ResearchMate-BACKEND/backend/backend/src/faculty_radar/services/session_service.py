"""Persistent Research Session (ONE idea -> shared context for all stages).

A session is created ONCE from the Dashboard and flows through:
idea -> faculty -> literature -> analysis -> gaps -> direction -> planner -> paper.
Each stage reads prior stages' results; no stage asks the user to retype the idea.

Storage is in-process (same contract as project_service); Firestore replaces
_REGISTRY later without changing route signatures.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field

# Canonical 8-step workflow (matches the frontend WorkflowIndicator).
STAGES: tuple[str, ...] = (
    "idea",
    "faculty",
    "literature",
    "analysis",
    "gaps",
    "direction",
    "planner",
    "paper",
)

STAGE_LABELS: dict[str, str] = {
    "idea": "Research idea",
    "faculty": "Faculty Discovery",
    "literature": "Literature Search",
    "analysis": "Research Analysis",
    "gaps": "Gaps & Novelty",
    "direction": "Research Direction",
    "planner": "Research Planner",
    "paper": "Paper Studio",
}


class ActivityEvent(BaseModel):
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    stage: str = ""
    message: str = ""


class ResearchSession(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    idea: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # stage -> pending | active | done | error
    stage_status: dict[str, str] = Field(default_factory=lambda: {s: "pending" for s in STAGES})
    # stage -> result payload produced by stage_runner
    results: dict[str, dict] = Field(default_factory=dict)
    activity: list[ActivityEvent] = Field(default_factory=list)


_REGISTRY: dict[str, ResearchSession] = {}


def create_session(idea: str) -> ResearchSession:
    idea = (idea or "").strip()
    if not idea:
        raise ValueError("research idea must not be empty")
    session = ResearchSession(idea=idea)
    session.stage_status["idea"] = "done"
    session.results["idea"] = {"idea": idea}
    session.activity.append(ActivityEvent(stage="idea", message=f"Research started: {idea[:120]}"))
    _REGISTRY[session.id] = session
    return session


def get_session(sid: str) -> ResearchSession | None:
    return _REGISTRY.get(sid)


def list_sessions() -> list[ResearchSession]:
    return sorted(_REGISTRY.values(), key=lambda s: s.updated_at, reverse=True)


def touch(session: ResearchSession, stage: str, status: str, message: str = "") -> ResearchSession:
    session.stage_status[stage] = status
    session.updated_at = datetime.now(UTC)
    if message:
        session.activity.append(ActivityEvent(stage=stage, message=message))
    return session


def store_result(session: ResearchSession, stage: str, result: dict) -> ResearchSession:
    session.results[stage] = result
    session.updated_at = datetime.now(UTC)
    return session


def update_session(
    session: ResearchSession,
    *,
    idea: str | None = None,
    results_patch: dict | None = None,
) -> ResearchSession:
    """Edit active context (idea) and/or stage payloads (planner/draft edits)."""
    if idea is not None and idea.strip():
        session.idea = idea.strip()
        session.activity.append(ActivityEvent(stage="idea", message="Research context edited"))
    if results_patch:
        for key, value in results_patch.items():
            if isinstance(value, dict):
                merged = dict(session.results.get(key, {}))
                merged.update(value)
                session.results[key] = merged
            else:
                session.results[key] = value
    session.updated_at = datetime.now(UTC)
    return session


def save_paper(session: ResearchSession, paper: dict) -> tuple[ResearchSession, bool]:
    """Save a paper into the session. Returns (session, added?)."""
    pid = (paper.get("id") or "").strip()
    if not pid:
        raise ValueError("paper.id is required")
    saved = list((session.results.get("saved_papers") or {}).get("papers", []))
    if any(p.get("id") == pid for p in saved):
        return session, False
    saved.append(paper)
    session.results["saved_papers"] = {"papers": saved}
    session.updated_at = datetime.now(UTC)
    session.activity.append(
        ActivityEvent(stage="literature", message=f"Paper saved: {(paper.get('title') or pid)[:100]}")
    )
    return session, True


def remove_paper(session: ResearchSession, pid: str) -> bool:
    saved = list((session.results.get("saved_papers") or {}).get("papers", []))
    kept = [p for p in saved if p.get("id") != pid]
    if len(kept) == len(saved):
        return False
    session.results["saved_papers"] = {"papers": kept}
    session.updated_at = datetime.now(UTC)
    return True
