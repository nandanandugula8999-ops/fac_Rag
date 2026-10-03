"""Shared pytest fixtures.

Every test in this suite runs fully offline. `engine_settings` points the data
lake at a tmp directory and disables network rate limiting; `fake_openalex`
wires the ingestion client to an in-memory source.
"""

from __future__ import annotations

import pytest

from faculty_radar.config.settings import Settings, get_settings
from faculty_radar.paths import build_paths


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings(tmp_path) -> Settings:
    """Minimal isolated settings, ignoring any real .env file."""
    return Settings(
        paths={"root": tmp_path, "data": tmp_path / "data", "logs": tmp_path / "logs"},
        logging={"file_enabled": False, "console_enabled": False},
    )


@pytest.fixture
def data_paths(settings):
    return build_paths(settings)


@pytest.fixture
def engine_settings(tmp_path) -> Settings:
    """Full engine settings for offline, tmp-scoped runs.

    Uses a small hashing embedding dimension so tests stay fast, and leaves the
    institution scope pointing at the fixture institution I1000.
    """
    return Settings(
        paths={"root": tmp_path, "data": tmp_path / "data", "logs": tmp_path / "logs"},
        logging={"file_enabled": False, "console_enabled": False},
        openalex={"requests_per_second": 0.0, "backoff_seconds": 0.0, "mailto": None},
        ingestion={"max_authors": 10, "max_works_per_author": 10},
        embeddings={"provider": "hashing", "dimension": 256, "batch_size": 16},
        scope={
            "institution_ids": ["I1000"],
            "institution_names": ["Northgate University"],
            "topic_seeds": ["graph neural networks"],
        },
    )


@pytest.fixture
def raw_payloads():
    """The OpenAlex fixture payloads, shared by normalization and later tests."""
    from tests import fake_openalex

    return {
        "institutions": fake_openalex.INSTITUTIONS,
        "authors": fake_openalex.AUTHORS,
        "works": fake_openalex.WORKS,
    }
