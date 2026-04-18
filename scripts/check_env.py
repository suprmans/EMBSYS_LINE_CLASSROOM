#!/usr/bin/env python3.12
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "rich>=13.7.0",
# ]
# ///
"""
scripts/check_env.py

Validate required environment variables for LINE bot integration.

Usage:
    uv run scripts/check_env.py
    uv run scripts/check_env.py --env-file .env
    uv run scripts/check_env.py --require APP_ENV --require WEBHOOK_BASE_URL
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console(stderr=True)

DEFAULT_REQUIRED = [
    "LINE_CHANNEL_SECRET",
    "LINE_CHANNEL_ACCESS_TOKEN",
]

PLACEHOLDER_PATTERN = re.compile(
    r"(?i)^(?:changeme|change_me|your[_-]?token|your[_-]?secret|placeholder|example|test|dummy)$"
)


@dataclass
class CheckRow:
    key: str
    status: str
    source: str
    preview: str


def parse_env_file(env_file: Path) -> dict[str, str]:
    """Parse simple .env format with KEY=VALUE and optional `export` prefix."""
    values: dict[str, str] = {}

    if not env_file.exists():
        raise FileNotFoundError(f"Env file not found: {env_file}")

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]

        values[key] = value

    return values


def mask(value: str) -> str:
    """Return masked value for safe logging."""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def is_placeholder(value: str) -> bool:
    """Return True if the value appears to be a sample placeholder."""
    normalized = value.strip().strip('"').strip("'")
    if not normalized:
        return True
    if PLACEHOLDER_PATTERN.match(normalized):
        return True
    if normalized.startswith("<") and normalized.endswith(">"):
        return True
    if normalized.startswith("${") and normalized.endswith("}"):
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check required LINE bot secrets in env vars or an env file."
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Optional .env file to read values from.",
    )
    parser.add_argument(
        "--require",
        action="append",
        default=[],
        help="Additional required variable name (repeatable).",
    )
    args = parser.parse_args()

    merged_env = dict(os.environ)
    file_values: dict[str, str] = {}

    if args.env_file is not None:
        try:
            file_values = parse_env_file(args.env_file)
            merged_env.update(file_values)
        except FileNotFoundError as exc:
            console.print(f"[red]ERROR:[/red] {exc}")
            return 2

    required = [*DEFAULT_REQUIRED, *args.require]
    rows: list[CheckRow] = []
    missing: list[str] = []
    invalid: list[str] = []

    for key in required:
        value = merged_env.get(key, "").strip()
        if not value:
            missing.append(key)
            rows.append(CheckRow(key=key, status="MISSING", source="-", preview="-"))
            continue

        source = "env-file" if key in file_values else "process-env"
        if is_placeholder(value):
            invalid.append(key)
            rows.append(CheckRow(key=key, status="INVALID", source=source, preview=mask(value)))
        else:
            rows.append(CheckRow(key=key, status="OK", source=source, preview=mask(value)))

    table = Table(title="LINE Environment Validation")
    table.add_column("Variable", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Source")
    table.add_column("Preview")

    for row in rows:
        status_style = {
            "OK": "green",
            "MISSING": "red",
            "INVALID": "yellow",
        }.get(row.status, "white")
        table.add_row(row.key, f"[{status_style}]{row.status}[/{status_style}]", row.source, row.preview)

    console.print(table)

    if missing or invalid:
        console.print("\n[red]Result: FAILED[/red]")
        if missing:
            console.print("Missing variables:")
            for key in missing:
                console.print(f"- {key}")
        if invalid:
            console.print("Invalid/placeholder variables:")
            for key in invalid:
                console.print(f"- {key}")
        return 1

    console.print("\n[green]Result: PASSED[/green]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
