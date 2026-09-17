#!/usr/bin/env python3
"""Resolve an owner cwd from a Codex CLI parent without printing its argv."""

from __future__ import annotations

from pathlib import Path
import shlex
import subprocess
import sys


def _process_record(pid: int) -> tuple[int, list[str]] | None:
    try:
        output = subprocess.run(
            ["ps", "-p", str(pid), "-o", "ppid=", "-o", "command="],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not output:
        return None
    fields = output.split(maxsplit=1)
    if len(fields) != 2:
        return None
    parent_text, command = fields
    try:
        parent_pid = int(parent_text)
        arguments = shlex.split(command)
    except (ValueError, IndexError):
        return None
    return parent_pid, arguments


def _directory_argument(arguments: list[str]) -> Path | None:
    for index, argument in enumerate(arguments):
        candidate: str | None = None
        if argument in {"--cd", "-C"} and index + 1 < len(arguments):
            candidate = arguments[index + 1]
        elif argument.startswith("--cd="):
            candidate = argument.split("=", 1)[1]
        if candidate:
            path = Path(candidate).expanduser()
            if path.is_dir():
                return path.resolve()
    return None


def main() -> int:
    if len(sys.argv) != 2:
        return 2
    try:
        pid = int(sys.argv[1])
    except ValueError:
        return 2
    visited: set[int] = set()
    for _ in range(6):
        if pid <= 1 or pid in visited:
            break
        visited.add(pid)
        record = _process_record(pid)
        if record is None:
            break
        parent_pid, arguments = record
        candidate = _directory_argument(arguments)
        if candidate is not None:
            print(candidate)
            return 0
        pid = parent_pid
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
