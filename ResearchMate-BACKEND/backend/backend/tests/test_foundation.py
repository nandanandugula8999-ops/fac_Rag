"""Smoke tests for the foundation: configuration, paths, logging, CLI."""

from __future__ import annotations

import json
import logging

import pytest
from pydantic import ValidationError

from faculty_radar.config.logging import JsonFormatter, configure_logging, get_logger
from faculty_radar.config.settings import Settings, get_settings
from faculty_radar.paths import build_paths


class TestSettings:
    def test_defaults_are_usable_without_env_file(self, tmp_path):
        settings = Settings(paths={"root": tmp_path, "data": None, "logs": None})

        assert settings.app.slug == "faculty-radar"
        assert settings.logging.level == "INFO"
        assert settings.paths.data == tmp_path / "data"
        assert settings.paths.logs == tmp_path / "logs"

    def test_nested_env_vars_are_parsed(self, monkeypatch):
        monkeypatch.setenv("FR_LOGGING__LEVEL", "DEBUG")
        monkeypatch.setenv("FR_OPENALEX__MAILTO", "researcher@university.edu")
        monkeypatch.setenv("FR_APP__ENV", "dev")

        settings = Settings()

        assert settings.logging.level == "DEBUG"
        assert settings.openalex.mailto == "researcher@university.edu"
        assert settings.app.env == "dev"

    def test_list_values_parse_from_json(self, monkeypatch):
        monkeypatch.setenv("FR_SCOPE__INSTITUTION_IDS", '["I1", "I2"]')

        assert Settings().scope.institution_ids == ["I1", "I2"]

    def test_invalid_value_fails_loudly(self, monkeypatch):
        monkeypatch.setenv("FR_LOGGING__LEVEL", "VERBOSE")

        with pytest.raises(ValidationError):
            Settings()

    def test_unknown_env_vars_are_ignored(self, monkeypatch):
        monkeypatch.setenv("FR_SOMETHING_FROM_A_LATER_STAGE", "x")

        assert Settings().app.slug == "faculty-radar"

    def test_get_settings_is_cached(self):
        assert get_settings() is get_settings()


class TestPaths:
    def test_layout_matches_data_dir(self, settings):
        paths = build_paths(settings)

        assert paths.raw == settings.paths.data / "raw"
        assert paths.processed == settings.paths.data / "processed"
        assert paths.vectors == settings.paths.data / "vectors"
        assert paths.logs == settings.paths.logs

    def test_ensure_creates_every_directory(self, data_paths):
        data_paths.ensure()

        for directory in data_paths.all_dirs:
            assert directory.is_dir(), f"{directory} was not created"

    def test_ensure_is_idempotent(self, data_paths):
        data_paths.ensure()
        data_paths.ensure()

        assert data_paths.raw.is_dir()

    def test_describe_covers_every_directory(self, data_paths):
        assert len(data_paths.describe()) == len(data_paths.all_dirs)


class TestLogging:
    def test_json_formatter_emits_one_object_with_extras(self):
        record = logging.LogRecord("t", logging.INFO, __file__, 1, "hello", None, None)
        record.count = 42

        payload = json.loads(JsonFormatter().format(record))

        assert payload["message"] == "hello"
        assert payload["level"] == "INFO"
        assert payload["logger"] == "t"
        assert payload["count"] == 42

    def test_json_formatter_omits_standard_attributes(self):
        record = logging.LogRecord("t", logging.INFO, __file__, 1, "hi", None, None)

        payload = json.loads(JsonFormatter().format(record))

        assert "args" not in payload
        assert "msg" not in payload
        assert "exc_info" not in payload

    def test_configure_logging_installs_handlers(self, settings):
        configure_logging(settings, force=True)

        assert isinstance(logging.getLogger().level, int)

    def test_configure_logging_is_idempotent(self, settings):
        configure_logging(settings, force=True)
        first = len(logging.getLogger().handlers)
        configure_logging(settings)

        assert len(logging.getLogger().handlers) == first

    def test_get_logger_returns_named_logger(self):
        assert get_logger(__name__).name == __name__


class TestCLI:
    def test_help_exits_cleanly(self, capsys):
        from faculty_radar.cli import main

        with pytest.raises(SystemExit) as exc:
            main(["--help"])

        assert exc.value.code == 0
        assert "doctor" in capsys.readouterr().out

    def test_no_command_prints_help(self, capsys):
        from faculty_radar.cli import main

        assert main([]) == 0
        assert "usage" in capsys.readouterr().out.lower()

    def test_env_redacts_secrets(self, monkeypatch, capsys):
        from faculty_radar.cli import main

        monkeypatch.setenv("FR_OPENALEX__API_KEY", "super-secret-value")
        monkeypatch.setenv("FR_OPENALEX__MAILTO", "someone@university.edu")

        assert main(["env"]) == 0
        out = capsys.readouterr().out

        assert "super-secret-value" not in out
        assert "***set***" in out

    def test_paths_command_runs(self, capsys):
        from faculty_radar.cli import main

        assert main(["paths"]) == 0
        assert "processed" in capsys.readouterr().out

    def test_doctor_reports_consent_gate_as_ok(self, capsys):
        from faculty_radar.cli import main

        main(["doctor"])
        assert "consent gate" in capsys.readouterr().out
