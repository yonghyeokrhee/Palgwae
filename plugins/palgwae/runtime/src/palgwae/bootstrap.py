"""Safely initialize a project-local bundle for plug-and-play MCP startup."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from contextlib import contextmanager
from typing import Any

from .builder import build_bundle
from .bundle import BundleValidationError, GraphBundle
from .model import Node, Unresolved


DEFAULT_SPEC_NAMES = (
    "palgwae-context-graph.yaml",
    "palgwae-context-graph.yml",
    "palgwae-context-graph.json",
    ".palgwae/context-graph.yaml",
    ".palgwae/context-graph.yml",
    ".palgwae/context-graph.json",
)

_STARTER_ENTITIES = {
    "name": "palgwae-bootstrap",
    "version": "1",
    "entity_types": {"Repository": {"identity": ["name"]}},
}
_STARTER_RELATIONS = {
    "name": "palgwae-bootstrap",
    "version": "1",
    "relations": {
        "CONTAINS": {
            "dependency_direction": "subject_to_object",
            "include_in_lineage": False,
        }
    },
}


def _document_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return f"sha256:{sha256(encoded.encode('utf-8')).hexdigest()}"


def _git_revision(project_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), "rev-parse", "--verify", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    revision = result.stdout.strip()
    if len(revision) == 40 and all(character in "0123456789abcdefABCDEF" for character in revision):
        return revision.lower()
    return None


def _directory_revision(project_root: Path) -> str:
    """Create a deterministic fallback snapshot for a non-Git project."""

    digest = sha256()
    excluded = {".git", ".palgwae", ".venv", "node_modules"}
    for path in sorted(project_root.rglob("*")):
        try:
            relative = path.relative_to(project_root)
        except ValueError:  # pragma: no cover - both paths are resolved.
            continue
        if (
            any(part in excluded for part in relative.parts)
            or path.is_symlink()
            or not path.is_file()
        ):
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        try:
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise BundleValidationError(
                f"cannot snapshot non-Git project file {relative}: {exc}"
            ) from exc
        digest.update(b"\0")
    return f"snapshot:{digest.hexdigest()}"


def discover_project_spec(project_root: str | Path) -> Path | None:
    root = Path(project_root).expanduser().resolve()
    for relative_name in DEFAULT_SPEC_NAMES:
        candidate = root / relative_name
        if candidate.is_file():
            return candidate
    return None


@contextmanager
def _bootstrap_lock(output_path: Path):
    """Serialize first-start bootstrap processes for one owner bundle."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = output_path.parent / f".{output_path.name}.bootstrap.lock"
    with lock_path.open("a+b") as lock_file:
        if os.name == "nt":  # pragma: no cover - exercised by Windows CI.
            import msvcrt

            # Windows allows locking past EOF. Do not read or initialize the
            # byte first: another bootstrap may already hold an exclusive lock.
            lock_file.seek(0)
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def create_starter_bundle(
    project_root: str | Path,
    output: str | Path,
) -> GraphBundle:
    """Create a fail-closed starter without inventing pipeline relationships."""

    root = Path(project_root).expanduser().resolve()
    if not root.is_dir():
        raise BundleValidationError(f"project root does not exist: {root}")
    project_name = root.name or "project"
    revision = _git_revision(root) or _directory_revision(root)
    identity = sha256(
        f"{project_name}\0{revision}".encode("utf-8")
    ).hexdigest()[:20]
    repository_id = f"urn:palgwae:bootstrap:{identity}:repository"
    bundle = GraphBundle(
        nodes=(
            Node(
                repository_id,
                "Repository",
                project_name,
                attributes={"bootstrap": True},
            ),
        ),
        evidence=(),
        claims=(),
        unresolved=(
            Unresolved.create(
                source_node_id=repository_id,
                target_hint="accepted_pipeline_context",
                reason=(
                    "No Palgwae context spec was found. Pipeline relationships "
                    "remain unproven until an evidence-backed project spec is built."
                ),
                attributes={"bootstrap": True},
            ),
        ),
    )
    bundle.write(
        output,
        metadata={
            "project": project_name,
            "source_revision": revision,
            "method": "fail-closed-project-bootstrap",
            "ontology": {
                "name": "palgwae-bootstrap",
                "version": "1",
                "entities_sha256": _document_hash(_STARTER_ENTITIES),
                "relations_sha256": _document_hash(_STARTER_RELATIONS),
            },
        },
    )
    return GraphBundle.load(output)


def bootstrap_project(
    project_root: str | Path,
    output: str | Path,
    *,
    spec: str | Path | None = None,
) -> dict[str, Any]:
    """Ensure a valid bundle exists, preferring a conventional project spec."""

    root = Path(project_root).expanduser().resolve()
    output_path = Path(output).expanduser()
    if not output_path.is_absolute():
        output_path = root / output_path
    output_path = output_path.resolve()
    with _bootstrap_lock(output_path):
        manifest = output_path / "manifest.json"
        if manifest.is_file():
            bundle = GraphBundle.load(output_path)
            mode = "existing"
            source_spec = None
        else:
            if output_path.exists() and any(output_path.iterdir()):
                raise BundleValidationError(
                    "refusing to replace partial or non-empty bundle directory: "
                    f"{output_path}"
                )
            if spec is None:
                spec_path = discover_project_spec(root)
            else:
                spec_path = Path(spec).expanduser()
                if not spec_path.is_absolute():
                    spec_path = root / spec_path
                spec_path = spec_path.resolve()
                if not spec_path.is_file():
                    raise BundleValidationError(
                        f"project spec does not exist: {spec_path}"
                    )
            if spec_path is None:
                bundle = create_starter_bundle(root, output_path)
                mode = "starter"
                source_spec = None
            else:
                bundle = build_bundle(spec_path, output_path)
                mode = "spec"
                source_spec = str(spec_path)

    result = bundle.doctor()
    result.update(
        {
            "bootstrap_mode": mode,
            "bundle_dir": str(output_path),
            "source_spec": source_spec,
        }
    )
    return result
