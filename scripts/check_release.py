"""Fail if release-facing versions disagree or public installation files are missing."""

import json
from pathlib import Path
import tomllib

root = Path(__file__).resolve().parents[1]
version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
for name in (
    "distributions/npm/package.json",
    "plugins/palgwae/.codex-plugin/plugin.json",
    "plugins/claude/palgwae/.claude-plugin/plugin.json",
):
    if json.loads((root / name).read_text())["version"] != version:
        raise SystemExit(f"Version mismatch: {name}")
for name in (
    "CHANGELOG.md",
    "SECURITY.md",
    "SUPPORT.md",
    "docs/installation.md",
    "docs/airflow.md",
    ".claude-plugin/marketplace.json",
):
    if not (root / name).is_file():
        raise SystemExit(f"Missing release file: {name}")
print(f"Release metadata is consistent: {version}")
