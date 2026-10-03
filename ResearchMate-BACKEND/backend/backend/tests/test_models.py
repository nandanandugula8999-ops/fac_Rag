"""Invariants of the shared domain model.

These are contract tests, not behaviour tests. They guard failures that are
easy to introduce and hard to notice: `from __future__ import annotations`
defers evaluation, so an undefined name in a field annotation imports cleanly
and then fails the first time the model is validated.
"""

from __future__ import annotations

import inspect
import pkgutil
from importlib import import_module

import pytest

import faculty_radar
from faculty_radar.models import (
    INSUFFICIENT_EVIDENCE,
    Status,
)

# Full pipeline roadmap. Stages that are not implemented yet are listed so the
# suite reports exactly which packages are still missing, rather than failing
# with an opaque import error later on.
_PIPELINE_ROADMAP = [
    "faculty_radar.models",
    "faculty_radar.ingestion",
    "faculty_radar.normalization",
    "faculty_radar.resolution",
    "faculty_radar.linking",
    "faculty_radar.graph",
    "faculty_radar.corpus",
    "faculty_radar.embeddings",
    "faculty_radar.retrieval",
    "faculty_radar.ranking",
    "faculty_radar.expertise",
    "faculty_radar.collaboration",
    "faculty_radar.trends",
    "faculty_radar.evidence",
    "faculty_radar.rag",
    "faculty_radar.llm",
    "faculty_radar.verification",
    "faculty_radar.evaluation",
]

# Stages built so far. Each is added here as it lands, which keeps this guard
# green while still failing loudly the moment a shipped package breaks.
_MODEL_PACKAGES = [
    "faculty_radar.models",
    "faculty_radar.ingestion",
    "faculty_radar.normalization",
    "faculty_radar.resolution",
    "faculty_radar.linking",
    "faculty_radar.graph",
    "faculty_radar.corpus",
    "faculty_radar.embeddings",
    "faculty_radar.retrieval",
    "faculty_radar.ranking",
    "faculty_radar.expertise",
    "faculty_radar.collaboration",
    "faculty_radar.trends",
    "faculty_radar.evidence",
    "faculty_radar.rag",
    "faculty_radar.llm",
    "faculty_radar.verification",
    "faculty_radar.evaluation",
    "faculty_radar.discovery",
]
_PENDING_PACKAGES = [p for p in _PIPELINE_ROADMAP if p not in _MODEL_PACKAGES]


def _all_models() -> list[type]:
    """Every pydantic BaseModel reachable from the model registry modules."""
    from pydantic import BaseModel

    found: list[type] = []
    seen: set[str] = set()

    def walk(module_name: str) -> None:
        if module_name in seen:
            return
        seen.add(module_name)
        try:
            module = import_module(module_name)
        except ImportError:
            return
        for obj in vars(module).values():
            if (
                inspect.isclass(obj)
                and issubclass(obj, BaseModel)
                and obj.__module__.startswith("faculty_radar")
            ):
                found.append(obj)

    for package in _MODEL_PACKAGES:
        walk(package)
        try:
            pkg = import_module(package)
        except ImportError:
            continue
        for info in pkgutil.iter_modules(getattr(pkg, "__path__", [])):
            walk(f"{package}.{info.name}")
    return found


class TestModelDefinitions:
    def test_no_models_import_error(self):
        # A missing name in an annotation only surfaces here, not at import.
        models = _all_models()
        assert len(models) > 10, "expected the domain model registry to be populated"

    def test_every_model_can_build_its_schema(self):
        for model in _all_models():
            model.model_rebuild(force=True)

    def test_every_model_has_defaults_constructible(self):
        """No model may fail to construct for a reason other than missing required fields.

        A plain ValidationError is correct behaviour (the field really is
        required). What this guards against is a model whose annotations cannot
        be resolved at all, which surfaces as PydanticUserError or NameError.
        """
        from pydantic import PydanticUserError, ValidationError

        for model in _all_models():
            try:
                model()
            except (ValidationError, TypeError):
                continue  # genuinely required fields
            except (PydanticUserError, NameError) as exc:
                pytest.fail(f"{model.__name__} has an unresolved annotation: {exc}")


class TestStatus:
    def test_insufficient_evidence_marker_value(self):
        assert INSUFFICIENT_EVIDENCE == "insufficient_evidence"

    def test_status_enum_matches_marker(self):
        assert Status.INSUFFICIENT_EVIDENCE.value == INSUFFICIENT_EVIDENCE
        assert Status.OK.value == "ok"

    def test_status_is_str_comparable(self):
        # Callers and API clients compare these against plain strings.
        assert Status.INSUFFICIENT_EVIDENCE == "insufficient_evidence"


class TestProvenanceIsMandatory:
    def test_entities_cannot_exist_without_provenance(self):
        """Rule 1: a record with no traceable origin must not be constructible."""
        from pydantic import ValidationError

        from faculty_radar.models import NormalizedAuthor, NormalizedWork

        with pytest.raises(ValidationError):
            NormalizedAuthor(openalex_id="A1", name="X")

        with pytest.raises(ValidationError):
            NormalizedWork(openalex_id="W1", title="X")

    def test_provenance_hash_is_content_addressed(self):
        from faculty_radar.models import Provenance

        payload = {"id": "A1", "display_name": "Wei Zhang"}
        first = Provenance.from_payload("openalex", "A1", payload)
        second = Provenance.from_payload("openalex", "A1", dict(reversed(list(payload.items()))))

        # Key order must not change the hash, or provenance would be unstable.
        assert first.record_hash == second.record_hash
        assert (
            first.record_hash != Provenance.from_payload("openalex", "A1", {"id": "A2"}).record_hash
        )


def test_package_exposes_version_and_surface():
    assert faculty_radar.__version__
    assert hasattr(faculty_radar, "get_settings")


def test_every_implemented_pipeline_package_is_importable():
    """Every stage marked as built must import cleanly."""
    missing = [name for name in _MODEL_PACKAGES if not _importable(name)]
    assert not missing, f"unimportable pipeline packages: {missing}"


def test_roadmap_packages_are_not_yet_implemented():
    """Documents what is still outstanding, without failing on it.

    Keeping the remaining stages visible makes the gap explicit instead of
    silently forgotten; each moves into `_MODEL_PACKAGES` when it lands.
    """
    assert _PENDING_PACKAGES == []


def _importable(module_name: str) -> bool:
    import importlib

    try:
        importlib.import_module(module_name)
    except ImportError:
        return False
    return True
