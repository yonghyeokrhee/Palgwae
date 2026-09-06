from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any


GRAPHIFY_VERSION = "0.9.46"
RUNNER_VERSION = "1"
_ENV_ALLOWLIST = frozenset(
    {
        "COMSPEC",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
        "TZ",
        "WINDIR",
    }
)
DEFAULT_EXCLUDES = (
    ".agents/",
    ".claude/",
    ".codex/",
    ".git/",
    ".palgwae/",
    ".venv/",
    "graphify-out/",
)


def _environment() -> dict[str, str]:
    result = {key: value for key, value in os.environ.items() if key in _ENV_ALLOWLIST}
    result.update(
        {
            "GRAPHIFY_QUERY_LOG_DISABLE": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONNOUSERSITE": "1",
            "PYTHONUTF8": "1",
        }
    )
    return result


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _hash_file(path: Path) -> str:
    digest = sha256(path.read_bytes()).hexdigest()
    return "sha256:" + digest


def run_graphify(
    *,
    repo_root: Path,
    repository: str,
    revision: str,
    output_dir: Path,
    executable: str | Path = "graphify",
    max_workers: int = 1,
) -> dict[str, Any]:
    """Run pinned, code-only Graphify without forwarding ambient credentials."""

    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    if not repo_root.is_dir():
        raise ValueError(f"repository root does not exist: {repo_root}")
    if not repository or any(character.isspace() for character in repository):
        raise ValueError("repository must be a stable name without whitespace")
    if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("revision must be a lowercase 40-character Git SHA")
    if max_workers < 1:
        raise ValueError("max_workers must be positive")
    try:
        output_dir.relative_to(repo_root)
    except ValueError:
        pass
    else:
        raise ValueError("Graphify output must be outside the source repository")
    if output_dir.exists():
        raise FileExistsError(f"Graphify output already exists: {output_dir}")
    if _git(repo_root, "rev-parse", "HEAD") != revision:
        raise ValueError("repository HEAD does not match the pinned revision")
    if _git(repo_root, "status", "--porcelain"):
        raise ValueError("Graphify extraction requires a clean repository")

    resolved = shutil.which(str(executable))
    if resolved is None:
        candidate = Path(executable)
        if not candidate.is_file():
            raise ValueError(f"Graphify executable not found: {executable}")
        resolved = str(candidate.resolve())
    version = subprocess.run(
        [resolved, "--version"],
        check=True,
        capture_output=True,
        text=True,
        env=_environment(),
    ).stdout.strip()
    if version != f"graphify {GRAPHIFY_VERSION}":
        raise ValueError(f"expected graphify {GRAPHIFY_VERSION}, received {version!r}")

    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True)
    command = [
        resolved,
        "extract",
        str(repo_root),
        "--code-only",
        "--no-cluster",
        "--max-workers",
        str(max_workers),
        "--out",
        str(raw_dir),
    ]
    for pattern in DEFAULT_EXCLUDES:
        command.extend(("--exclude", pattern))
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=_environment(),
    )
    (output_dir / "stdout.log").write_text(completed.stdout, encoding="utf-8")
    (output_dir / "stderr.log").write_text(completed.stderr, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(f"Graphify failed with exit code {completed.returncode}")

    graph_path = raw_dir / "graphify-out" / "graph.json"
    if not graph_path.is_file():
        raise RuntimeError("Graphify did not produce graphify-out/graph.json")
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    if graph.get("input_tokens", 0) or graph.get("output_tokens", 0):
        raise ValueError("code-only Graphify run unexpectedly used LLM tokens")
    manifest = {
        "schema_version": "palgwae.graphify-run/v1",
        "runner_version": RUNNER_VERSION,
        "graphify_version": GRAPHIFY_VERSION,
        "repository": repository,
        "revision": revision,
        "mode": "code-only",
        "subprocess_environment": "minimal-allowlist/v1",
        "raw_graph_sha256": _hash_file(graph_path),
        "node_count": len(graph.get("nodes", [])),
        "edge_count": len(graph.get("edges", [])),
        "accepted_claim_count": 0,
    }
    (output_dir / "run-manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    manifest["graph_path"] = str(graph_path)
    return manifest
