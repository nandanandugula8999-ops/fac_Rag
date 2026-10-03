"""Command line entrypoint.

Stage 1 ships three diagnostic commands. They exist so that configuration,
environment variables and the data layout can be verified without writing any
pipeline code yet. Pipeline subcommands (`ingest`, `index`, `search`, ...) will
be registered here as their stages are built.

    fr doctor    validate configuration and report problems
    fr paths     show the resolved data directory layout
    fr env       print every setting with secrets redacted
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from pydantic import ValidationError

from faculty_radar.config.logging import configure_logging, get_logger, log_settings_banner
from faculty_radar.config.settings import Settings, get_settings
from faculty_radar.paths import DataPaths, build_paths

logger = get_logger("faculty_radar.cli")

EXIT_OK = 0
EXIT_CONFIG_ERROR = 2


def _print_table(rows: Sequence[tuple[str, str]], headers: tuple[str, str]) -> None:
    widths = [
        max(len(str(headers[0])), *(len(r[0]) for r in rows)) if rows else len(headers[0]),
        max(len(str(headers[1])), *(len(r[1]) for r in rows)) if rows else len(headers[1]),
    ]
    print(f"{headers[0]:<{widths[0]}}  {headers[1]}")
    print(f"{'-' * widths[0]}  {'-' * widths[1]}")
    for key, value in rows:
        print(f"{key:<{widths[0]}}  {value}")


def _redact(value: object) -> str:
    return "***set***" if value else "(unset)"


def _flatten(settings: Settings) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = [
        ("app.name", settings.app.name),
        ("app.env", settings.app.env),
        ("app.debug", str(settings.app.debug)),
        ("app.version", settings.app.version),
        ("paths.root", str(settings.paths.root)),
        ("paths.data", str(settings.paths.data)),
        ("paths.logs", str(settings.paths.logs)),
        ("logging.level", settings.logging.level),
        ("logging.format", settings.logging.format),
        ("logging.file_enabled", str(settings.logging.file_enabled)),
        ("openalex.base_url", settings.openalex.base_url),
        ("openalex.mailto", _redact(settings.openalex.mailto)),
        ("openalex.api_key", _redact(settings.openalex.api_key)),
        ("openalex.page_size", str(settings.openalex.page_size)),
        ("scope.institution_ids", ", ".join(settings.scope.institution_ids) or "(none)"),
        ("scope.institution_names", ", ".join(settings.scope.institution_names) or "(none)"),
        ("scope.topic_seeds", ", ".join(settings.scope.topic_seeds) or "(none)"),
        ("scope.require_consent", str(settings.scope.require_consent)),
    ]
    return rows


def _check(settings: Settings) -> list[tuple[str, str, str]]:
    """Return (severity, check, detail) rows describing setup health."""
    checks: list[tuple[str, str, str]] = []

    if settings.paths.env_file.exists():
        checks.append(("ok", "env file", str(settings.paths.env_file)))
    else:
        checks.append(
            ("warn", "env file", "not found - using defaults (copy .env.example to .env)")
        )

    for directory in build_paths(settings).all_dirs:
        if directory.exists():
            checks.append(("ok", f"dir {directory.name}", str(directory)))
        else:
            checks.append(("warn", f"dir {directory.name}", "missing, will create on demand"))

    if settings.openalex.mailto:
        checks.append(("ok", "openalex polite pool", "mailto configured"))
    else:
        checks.append(
            ("warn", "openalex polite pool", "set FR_OPENALEX__MAILTO to avoid rate limits")
        )

    if settings.scope.institution_ids or settings.scope.institution_names:
        checks.append(("ok", "institution scope", "configured"))
    else:
        checks.append(
            ("warn", "institution scope", "set FR_SCOPE__INSTITUTION_IDS before ingesting")
        )

    if settings.scope.require_consent:
        checks.append(("ok", "consent gate", "enabled (required)"))
    else:
        checks.append(("fail", "consent gate", "disabled - discovery must be opt-in"))

    return checks


def cmd_doctor(_: argparse.Namespace) -> int:
    settings = get_settings()
    checks = _check(settings)

    width = max(len(c[1]) for c in checks)
    symbols = {"ok": "[ ok ]", "warn": "[warn]", "fail": "[FAIL]"}
    print("\nFaculty Radar - environment check\n")
    for severity, check, detail in checks:
        print(f"{symbols[severity]}  {check:<{width}}  {detail}")

    failures = [c for c in checks if c[0] == "fail"]
    warnings = [c for c in checks if c[0] == "warn"]

    print()
    if failures:
        print(f"{len(failures)} blocking problem(s), {len(warnings)} warning(s).")
        return EXIT_CONFIG_ERROR
    if warnings:
        print(f"Ready, with {len(warnings)} warning(s).")
    else:
        print("Ready. No issues found.")
    return EXIT_OK


def cmd_paths(_: argparse.Namespace) -> int:
    data_paths: DataPaths = build_paths()
    rows = [(name, purpose) for name, purpose, _ in data_paths.describe()]
    print("\nData directory layout\n")
    _print_table(rows, ("directory", "purpose"))
    print("\nabsolute paths\n")
    for _, _, path in data_paths.describe():
        print(f"{path}")
    print(f"\nenv file: {get_settings().paths.env_file}")
    return EXIT_OK


def cmd_env(args: argparse.Namespace) -> int:
    settings = get_settings()
    if args.create:
        return _create_env_file(settings)
    _print_table(_flatten(settings), ("setting", "value"))
    return EXIT_OK


def _create_env_file(settings: Settings) -> int:
    source = settings.paths.root / ".env.example"
    target = settings.paths.env_file
    if target.exists():
        print(f"{target} already exists; leaving it untouched.")
        return EXIT_OK
    if not source.exists():
        print(f"Cannot create {target}: .env.example is missing.")
        return EXIT_CONFIG_ERROR
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Created {target} from .env.example. Review it before ingesting data.")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fr",
        description="Faculty Research Discovery Assistant - research intelligence engine.",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Override the configured log level for this run.",
    )
    parser.add_argument(
        "--log-format",
        default=None,
        choices=["json", "text"],
        help="Override the configured log format for this run.",
    )

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("doctor", help="Validate configuration and report problems.")

    paths_parser = subparsers.add_parser("paths", help="Show the data directory layout.")
    paths_parser.add_argument(
        "--ensure",
        action="store_true",
        help="Create any missing directories instead of only reporting them.",
    )

    env_parser = subparsers.add_parser("env", help="Print settings with secrets redacted.")
    env_parser.add_argument(
        "--create",
        action="store_true",
        help="Write a .env file from .env.example, then exit.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        settings = get_settings()
    except ValidationError as exc:
        print(f"Configuration is invalid:\n{exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    if args.log_level:
        settings.logging.level = args.log_level
    if args.log_format:
        settings.logging.format = args.log_format

    # `env --create` runs before logging so it never needs a log directory.
    if args.command == "env" and args.create:
        return cmd_env(args)

    if args.command == "paths" and args.ensure:
        build_paths(settings).ensure()
        logger.info("data directories ensured", extra={"root": str(settings.paths.data)})

    if args.command is None:
        parser.print_help()
        return EXIT_OK

    configure_logging(settings)
    log_settings_banner(settings, logger)

    handlers = {
        "doctor": cmd_doctor,
        "paths": cmd_paths,
        "env": cmd_env,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
