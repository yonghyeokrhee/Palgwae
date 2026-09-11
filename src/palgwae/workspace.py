"""Build one portable context graph from explicitly registered local repositories."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import quote, urlsplit

from .airflow import extract_airflow
from .builder import load_spec
from .bundle import BundleValidationError, GraphBundle
from .model import Claim, Node, Unresolved
from .workspace_resources import extract_resources


ADAPTER = "palgwae-workspace-v1"
SKIP = {"node_modules", "venv", "__pycache__", "dist", "build", "archive", "output"}
EXTENSIONS = {".py", ".tf", ".tfvars", ".json", ".java", ".xml", ".sql", ".js", ".ts", ".go", ".scala"}
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
WORKSPACE_ENTITIES = {
    "Repository": "registered local repository",
    "Orchestrator": "literal Airflow DAG or declared AWS state machine",
    "Task": "literal task within a repository-scoped DAG",
    "Script": "repository-relative Python source with a supported AWS SDK call",
    "Job": "Terraform-declared Glue job",
    "Service": "Terraform-declared Lambda function",
    "Queue": "Terraform-declared SQS queue",
    "PhysicalDataset": "Terraform-declared S3, DynamoDB or Glue Catalog resource",
    "Trigger": "Terraform-declared EventBridge rule",
}
WORKSPACE_RELATIONS = {
    "CONTAINS": ("subject_to_object", False),
    "NEXT": ("subject_to_object", True),
    "WAITS_FOR": ("object_to_subject", True),
    "STARTS": ("subject_to_object", True),
    "INVOKES": ("subject_to_object", True),
}


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _namespace(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme not in {"urn", "https", "http"}
        or (parsed.scheme == "urn" and not parsed.path)
        or (parsed.scheme in {"https", "http"} and not parsed.netloc)
        or any(c.isspace() for c in value)):
        raise BundleValidationError("namespace must be an organization-controlled urn: or https:// URI")
    return value.rstrip("/:")


def _resolve_repository(root: Path, entry: str) -> tuple[str, Path]:
    name, separator, value = entry.partition("=")
    if not separator:
        value = name
    if not value.strip():
        raise BundleValidationError("repository path must not be empty")
    path = Path(value).expanduser()
    if path.is_absolute() or separator or "/" in value or "\\" in value or value in {".", ".."}:
        choices = [(root / path).resolve()]
    else:
        choices = [(root / path).resolve(), (root.parent / path).resolve()]
        if root.name == value:
            choices.append(root)
    found = sorted({p for p in choices if p.is_dir()})
    if len(found) != 1:
        raise BundleValidationError(
            f"repository {entry!r} is missing or ambiguous; provide NAME=../path explicitly"
        )
    target = found[0]
    name = name if separator else target.name
    if not NAME.fullmatch(name):
        raise BundleValidationError("repository names must contain only letters, digits, '.', '_' or '-'")
    return name, target


def initialize_workspace(
    project_root: Path,
    repositories: list[str],
    namespace: str,
    environment: str | None = None,
) -> Path:
    """Register names/relative paths; never clone repositories or change agent settings."""
    root = Path(project_root).resolve()
    namespace = _namespace(namespace)
    projects = []
    names, paths = set(), set()
    for entry in repositories or ["."]:
        name, path = _resolve_repository(root, entry)
        if name in names or path in paths:
            raise BundleValidationError("each repository name and resolved path must be unique")
        names.add(name)
        paths.add(path)
        projects.append({"name": name, "path": os.path.relpath(path, root)})
    config = root / ".palgwae" / "workspace.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    import yaml

    value = {"version": 1, "namespace": namespace, "environment": environment,
             "projects": sorted(projects, key=lambda p: p["name"])}
    try:
        with config.open("x", encoding="utf-8") as handle:
            yaml.safe_dump(value, handle, sort_keys=False)
    except FileExistsError as exc:
        raise BundleValidationError("workspace already exists; use palgwae rebuild or edit its project list") from exc
    return config


def _load_workspace(config: Path) -> tuple[dict, Path, list[tuple[str, Path]]]:
    spec = load_spec(config)
    if spec.get("version") != 1 or not isinstance(spec.get("projects"), list) or not spec["projects"]:
        raise BundleValidationError("workspace requires version: 1 and a non-empty projects list")
    _namespace(str(spec.get("namespace", "")))
    if spec.get("environment") is not None and not isinstance(spec["environment"], str):
        raise BundleValidationError("workspace environment must be a string or null")
    # Paths are relative to the owner checkout, one directory above .palgwae/.
    if config.parent.name != ".palgwae":
        raise BundleValidationError("workspace config must live in the owner's .palgwae directory")
    root = config.parent.parent
    projects = []
    names, paths = set(), set()
    for project in spec["projects"]:
        if not isinstance(project, dict):
            raise BundleValidationError("each project must have a name and a relative path")
        name, relative = project.get("name"), project.get("path")
        if not isinstance(name, str) or not NAME.fullmatch(name) or not isinstance(relative, str):
            raise BundleValidationError("project name/path is invalid")
        if Path(relative).is_absolute():
            raise BundleValidationError("project paths must be relative to the owner checkout")
        path = (root / relative).resolve()
        if not path.is_dir() or name in names or path in paths:
            raise BundleValidationError("project paths must exist and names/paths must be unique")
        names.add(name)
        paths.add(path)
        projects.append((name, path))
    return spec, root, sorted(projects)


def _inventory(root: Path, output: Path | None = None) -> tuple[list[Path], str | None]:
    """Only tracked source files in Git; source extensions in a non-Git directory."""
    git_revision = None
    try:
        top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=False)
        if top.returncode == 0:
            result = subprocess.run(["git", "-C", str(root), "ls-files", "-z"],
                                    capture_output=True, check=True)
            paths = [root / os.fsdecode(name) for name in result.stdout.split(b"\0") if name]
            revision = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                      capture_output=True, text=True, check=False)
            git_revision = revision.stdout.strip() if revision.returncode == 0 else None
        else:
            paths = []
            for directory, dirs, names in os.walk(root, followlinks=False):
                dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in SKIP)
                paths.extend(Path(directory) / name for name in names)
    except FileNotFoundError:
        paths = list(root.rglob("*"))
    selected = []
    for path in paths:
        relative = path.relative_to(root)
        if output is not None and path.resolve().is_relative_to(output.resolve()):
            continue
        if path.suffix not in EXTENSIONS or any(p.startswith(".") or p in SKIP for p in relative.parts):
            continue
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
            continue
        if any(parent.is_symlink() for parent in path.parents if parent != root and root in parent.parents):
            continue
        selected.append(path)
    return sorted(set(selected)), git_revision


def _claim(subject: str, predicate: str, target: str, evidence_ids: list[str], revision: str) -> Claim:
    return Claim.create(
        subject=subject, predicate=predicate, object=target,
        assertion_kind="DECLARED", review_status="AUTO_VERIFIED",
        evidence_ids=sorted(set(evidence_ids)), scope={"revision": revision},
        attributes={"lineage_orientation": "object_to_subject" if predicate == "WAITS_FOR" else "subject_to_object",
                    "include_in_lineage": True, "relation_category": "control",
                    "verifier": ADAPTER, "rule": "unique-explicit-target"},
    )


def _merge_claims(claims: list[Claim]) -> tuple[Claim, ...]:
    merged = {}
    for claim in sorted(claims, key=lambda c: c.claim_id):
        key = (claim.subject, claim.predicate, claim.object)
        if key in merged:
            old = merged[key]
            claim = replace(old, evidence_ids=tuple(sorted(set(old.evidence_ids + claim.evidence_ids))))
        merged[key] = claim
    return tuple(merged.values())


def _publish(bundle: GraphBundle, output: Path, metadata: dict) -> None:
    """Validate before replacement; retain previous valid bundles for recovery."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_symlink():
        raise BundleValidationError("workspace output must not be a symlink")
    lock = output.parent / ("." + output.name + ".build-lock")
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise BundleValidationError("workspace build is locked; wait for the current build or inspect its stale lock") from exc
    try:
        if output.exists():
            old = GraphBundle.load(output)
            if old.manifest.get("build", {}).get("adapter") != ADAPTER:
                raise BundleValidationError("refusing to replace a bundle not built by workspace init")
        with tempfile.TemporaryDirectory(prefix=".workspace-build-", dir=output.parent) as temporary:
            staged = Path(temporary) / "bundle"
            bundle.write(staged, metadata=metadata)
            GraphBundle.load(staged)
            previous = None
            if output.exists():
                previous = Path(tempfile.mkdtemp(prefix="." + output.name + ".previous-", dir=output.parent))
                previous.rmdir()
                output.rename(previous)
            try:
                staged.rename(output)
            except OSError:
                if previous is not None:
                    previous.rename(output)
                raise
    finally:
        lock.rmdir()


def build_workspace(config_path: Path, output: Path | None = None) -> dict:
    """Extract registered repos independently, resolve explicit cross-repo bindings, publish once."""
    config = Path(config_path).resolve()
    spec, owner, projects = _load_workspace(config)
    output_path = Path(output).absolute() if output is not None else owner / ".palgwae" / "bundle"
    if output_path.resolve() in {path for _, path in projects} or output_path.resolve() == owner:
        raise BundleValidationError("bundle output must not replace a project directory")
    namespace = _namespace(spec["namespace"])
    nodes, evidence = {}, {}
    claims, unresolved, refs = [], [], []
    extractions, coverage = [], []

    with tempfile.TemporaryDirectory(prefix="palgwae-sources-") as temporary:
        for name, source in projects:
            paths, git_revision = _inventory(source, output_path)
            staged = Path(temporary) / name
            staged.mkdir()
            hashes = []
            for path in paths:
                relative = path.relative_to(source)
                data = path.read_bytes().replace(b"\r\n", b"\n")
                destination = staged / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                hashes.append((relative.as_posix(), sha256(data).hexdigest()))
            source_revision = "sha256:" + _digest(hashes)
            repo_namespace = namespace + "/repo/" + quote(name, safe="")
            airflow = extract_airflow(staged, repo_namespace)
            resources, resource_refs, resource_coverage = extract_resources(staged, repo_namespace, spec.get("environment"))
            extractions.append((name, airflow))
            nodes.update((node.node_id, node) for node in resources.nodes)
            evidence.update((item.evidence_id, item) for item in resources.evidence)
            claims.extend(resources.claims)
            unresolved.extend(resources.unresolved)
            refs.extend(resource_refs)
            refs.extend(airflow.resource_references)
            root_id = repo_namespace + "/repository/source"
            nodes[root_id] = Node(root_id, "Repository", name,
                                  attributes={"repository": repo_namespace, "source_revision": source_revision})
            extensions = dict(sorted(Counter(p.suffix for p in paths).items()))
            unknown_extensions = sorted(set(extensions) - {".py", ".tf", ".tfvars"})
            # Coverage is an explicit limit, never a completeness/accuracy percentage.
            coverage.append({"project": name, "namespace": repo_namespace,
                             "source_revision": source_revision, "git_revision": git_revision,
                             "source_files": len(paths), "extensions": extensions,
                             "airflow_dags": len(airflow.dags), "airflow_tasks": len(airflow.tasks),
                             "resources": resource_coverage, "status": "PARTIAL",
                             "unsupported_extensions": unknown_extensions})
            unresolved.append(Unresolved.create(
                source_node_id=root_id, target_hint="adapter-coverage",
                reason="Static Airflow/Terraform/literal AWS references only; arbitrary backend, SQL, contracts and runtime state are not proven.",
                attributes={"unsupported_extensions": unknown_extensions, "source_revision": source_revision},
            ))

        task_index = defaultdict(list)
        task_evidence = defaultdict(set)
        for _, result in extractions:
            for key, node_id in result.tasks.items():
                task_index[key].append((result, node_id))
            for _, predicate, target, _, ids in result.candidates:
                if predicate == "CONTAINS":
                    task_evidence[target].update(ids)
        sensor_refs = []
        for name, result in extractions:
            # Local targets are authoritative within that repository's namespace.
            remaining = []
            for source, dag, task, item in result.sensors:
                if dag and task and (dag, task) in result.tasks:
                    remaining.append((source, dag, task, item))
                elif dag and task:
                    matches = task_index.get((dag, task), [])
                    if len(matches) == 1:
                        _, target = matches[0]
                        sensor_refs.append((source, target, [item, *task_evidence[target]]))
                    else:
                        result.gap(source, item, "ExternalTaskSensor target is absent or ambiguous across registered repositories.")
                else:
                    remaining.append((source, dag, task, item))
            result.sensors = remaining
            piece = result.promote()
            for node in piece.nodes:
                if node.node_type != "Repository" or node.node_id not in nodes:
                    nodes[node.node_id] = node
            evidence.update((item.evidence_id, item) for item in piece.evidence)
            # Cross-repo sensors need evidence normally retained by local promotion.
            evidence.update((item.evidence_id, item) for item in result.evidence.values()
                            if any(item.evidence_id in ids for _, _, ids in sensor_refs))
            claims.extend(piece.claims)
            unresolved.extend(piece.unresolved)

        revision = "sha256:" + _digest([(c["project"], c["source_revision"]) for c in coverage])
        for subject, target, ids in sensor_refs:
            claims.append(_claim(subject, "WAITS_FOR", target, ids, revision))
        declarations = defaultdict(set)
        for claim in claims:
            if claim.predicate == "CONTAINS":
                declarations[claim.object].update(claim.evidence_ids)
        resources_by_key = defaultdict(list)
        for node in nodes.values():
            attrs = node.attributes
            if attrs.get("resource_kind") and attrs.get("resource_name"):
                resources_by_key[(attrs["resource_kind"], attrs["resource_name"], attrs.get("environment"))].append(node)
        bindings = 0
        for ref in refs:
            environment = ref.get("environment") or spec.get("environment")
            matches = resources_by_key.get((ref["target_kind"], ref["target_name"], environment), [])
            ids = list(ref["evidence_ids"])
            if len(matches) != 1 or not declarations[matches[0].node_id]:
                unresolved.append(Unresolved.create(
                    source_node_id=ref["subject"], target_hint=ref["target_name"], evidence_ids=ids,
                    reason="Explicit resource target is absent or ambiguous in the selected workspace/environment.",
                    attributes={"resource_kind": ref["target_kind"], "environment": environment},
                ))
                continue
            target = matches[0]
            claims.append(_claim(ref["subject"], ref["predicate"], target.node_id,
                                 [*ids, *declarations[target.node_id]], revision))
            bindings += 1
        merged_claims = _merge_claims(claims)
        if any(node.node_type not in WORKSPACE_ENTITIES for node in nodes.values()):
            raise BundleValidationError("adapter emitted a type outside the workspace ontology")
        if any(claim.predicate not in WORKSPACE_RELATIONS for claim in merged_claims):
            raise BundleValidationError("adapter emitted a relation outside the workspace ontology")
        unresolved_map = {}
        for item in unresolved:
            if item.unresolved_id in unresolved_map:
                item = replace(item, evidence_ids=tuple(sorted(set(item.evidence_ids + unresolved_map[item.unresolved_id].evidence_ids))))
            unresolved_map[item.unresolved_id] = item
        used = {i for c in merged_claims for i in c.evidence_ids} | {i for u in unresolved_map.values() for i in u.evidence_ids}
        bundle = GraphBundle(nodes=tuple(nodes.values()), claims=merged_claims,
                             evidence=tuple(v for k, v in evidence.items() if k in used),
                             unresolved=tuple(unresolved_map.values()))
        metadata = {"project": namespace, "source_revision": revision, "adapter": ADAPTER,
                    "environment": spec.get("environment"), "coverage": coverage,
                    "resolved_resource_references": bindings, "resolved_cross_repo_sensors": len(sensor_refs),
                    "ontology": {"name": "palgwae-workspace", "version": "1",
                                 "entities_sha256": "sha256:" + _digest(WORKSPACE_ENTITIES),
                                 "relations_sha256": "sha256:" + _digest(WORKSPACE_RELATIONS)}}
        _publish(bundle, output_path, metadata)
    report = GraphBundle.load(output_path).doctor()
    report["coverage"] = coverage
    report["resolved_resource_references"] = bindings
    report["resolved_cross_repo_sensors"] = len(sensor_refs)
    # Use the installation that performed init, even when another version is on PATH.
    # These absolute paths are a local client recipe, never part of the portable bundle.
    report["mcp_config"] = {"mcpServers": {"palgwae": {"command": sys.executable, "args": ["-m", "palgwae", "mcp", "--bundle", str(output_path.resolve()), "--transport", "stdio"]}}}
    report["next"] = "Connect this single MCP server to use all registered repositories. Rebuild and restart MCP after source changes."
    return report
