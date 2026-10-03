"""Logging configuration built on the standard library.

Why stdlib `logging` instead of a third-party logger: the standard library
already gives us handlers, levels, propagation and formatting, and this stage
of the project has no need for anything more. Structured JSON output is
obtained with a small custom formatter rather than by adding a dependency.

Two sinks are configured:
  * console - human readable, colour-free, one line per record
  * file    - rotating JSON Lines, machine parsable for later analysis
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from datetime import UTC, datetime
from typing import Any

from faculty_radar.config.settings import Settings, get_settings

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)-32s %(message)s"

# Attributes present on every LogRecord; anything else was passed by the caller
# via `logger.info("msg", extra={"key": value})` and belongs in the payload.
_STANDARD_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys()) | {
    "message",
    "asctime",
    "taskName",
}

THIRD_PARTY_LOGGERS = ("httpx", "httpcore", "urllib3", "openalex", "filelock", "asyncio")


class JsonFormatter(logging.Formatter):
    """Render each record as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, default=str, ensure_ascii=False)


def get_logger(name: str) -> logging.Logger:
    """Return a module logger. Every module should create its logger this way."""
    return logging.getLogger(name)


def _build_handlers(settings: Settings, log_dir) -> list[logging.Handler]:
    handlers: list[logging.Handler] = []

    if settings.logging.console_enabled:
        console = logging.StreamHandler(stream=sys.stderr)
        if settings.logging.format == "json":
            console.setFormatter(JsonFormatter())
        else:
            console.setFormatter(logging.Formatter(LOG_FORMAT, datefmt="%H:%M:%S"))
        handlers.append(console)

    if settings.logging.file_enabled:
        log_dir.mkdir(parents=True, exist_ok=True)
        rotating = logging.handlers.RotatingFileHandler(
            filename=log_dir / settings.logging.file_name,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        # File logs stay JSON even when the console is human readable, so that
        # pipeline runs can be analyzed later without re-running anything.
        rotating.setFormatter(JsonFormatter())
        handlers.append(rotating)

    return handlers


def configure_logging(settings: Settings | None = None, *, force: bool = False) -> None:
    """Install handlers on the root logger. Idempotent unless `force` is set.

    Application modules should not call this; the CLI entrypoint calls it once
    at startup. Tests can call it with `force=True` to reset handlers between
    cases.
    """
    settings = settings or get_settings()
    root = logging.getLogger()
    if root.handlers and not force:
        return

    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    for handler in _build_handlers(settings, settings.paths.logs):
        root.addHandler(handler)

    root.setLevel(settings.logging.level)

    if settings.logging.silence_third_party:
        for name in THIRD_PARTY_LOGGERS:
            logging.getLogger(name).setLevel(logging.WARNING)


def log_settings_banner(settings: Settings, logger: logging.Logger) -> None:
    """Log a redacted snapshot of settings at the start of a run.

    Secrets are never logged: only whether they are present.
    """
    logger.info(
        "configuration loaded",
        extra={
            "env": settings.app.env,
            "version": settings.app.version,
            "log_level": settings.logging.level,
            "log_format": settings.logging.format,
            "data_dir": str(settings.paths.data),
            "openalex_mailto": bool(settings.openalex.mailto),
            "openalex_api_key": bool(settings.openalex.api_key),
            "institutions_configured": len(settings.scope.institution_ids),
        },
    )
