# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Portable launcher for the isolated, bundled Palgwae runtime."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys


def owner_root(plugin_root: Path) -> Path:
    explicit = os.environ.get("PALGWAE_PROJECT_ROOT")
    if explicit:
        root = Path(explicit).expanduser().resolve()
        if not root.is_dir():
            raise ValueError("PALGWAE_PROJECT_ROOT is not a directory")
        return root

    for value in (str(Path.cwd()), os.environ.get("OLDPWD")):
        if value:
            root = Path(value).expanduser().resolve()
            if root.is_dir() and not root.is_relative_to(plugin_root):
                return root

    result = subprocess.run(
        [sys.executable, str(plugin_root / "bin" / "resolve-owner-root.py"),
         str(os.getppid())], capture_output=True, text=True, timeout=35,
    )
    if result.returncode == 0:
        root = Path(result.stdout.strip()).resolve()
        if root.is_dir() and not root.is_relative_to(plugin_root):
            return root
    parent_cwd = Path(f"/proc/{os.getppid()}/cwd")
    if parent_cwd.exists():
        root = parent_cwd.resolve()
        if root.is_dir() and not root.is_relative_to(plugin_root):
            return root
    if shutil.which("lsof"):
        result = subprocess.run(
            ["lsof", "-a", "-p", str(os.getppid()), "-d", "cwd", "-Fn"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.splitlines():
            if line.startswith("n"):
                root = Path(line[1:]).resolve()
                if root.is_dir() and not root.is_relative_to(plugin_root):
                    return root
    raise ValueError("cannot determine owner project; set PALGWAE_PROJECT_ROOT")


def main() -> int:
    plugin_root = Path(__file__).resolve().parents[1]
    uv = shutil.which("uv")
    if not uv:
        print("palgwae plugin: uv is required", file=sys.stderr)
        return 127
    try:
        owner = owner_root(plugin_root)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"palgwae plugin: {exc}", file=sys.stderr)
        return 2
    runtime = plugin_root / "runtime"
    cache = Path(os.environ.get("XDG_CACHE_HOME") or
                 os.environ.get("LOCALAPPDATA") or Path.home() / ".cache")
    environment = dict(os.environ)
    environment["UV_PROJECT_ENVIRONMENT"] = str(cache / "palgwae" / "plugin-runtime-0.3.0")
    # Load this plugin's exact source, even if another Palgwae is installed.
    environment["PYTHONPATH"] = str(runtime / "src")
    os.chdir(owner)
    os.execvpe(uv, [uv, "run", "--quiet", "--frozen", "--project", str(runtime),
                   "--", "python", "-m", "palgwae", *sys.argv[1:]], environment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
