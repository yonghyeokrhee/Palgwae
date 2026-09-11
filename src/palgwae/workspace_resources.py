"""Bounded source declarations and AWS SDK references; never execute source code.

Terraform support intentionally excludes expression evaluation and deployment
claims. Selected tfvars establish declared registration, not runtime existence.
"""

from __future__ import annotations

import ast
from collections import Counter, defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from urllib.parse import quote
import warnings

import hcl2

from .bundle import GraphBundle
from .model import Claim, Evidence, Node, Unresolved, stable_id


EXTRACTOR = "palgwae-workspace-resources-v1"
SKIP = {".git", ".palgwae", ".venv", "venv", ".worktrees", "node_modules", "__pycache__", "docs", "archive", "output", "dist", "build", "test", "tests", "fixtures", "examples", "vendor"}
KINDS = {
    "aws_glue_job": ("name", "Job"),
    "aws_lambda_function": ("function_name", "Service"),
    "aws_sfn_state_machine": ("name", "Orchestrator"),
    "aws_sqs_queue": ("name", "Queue"),
    "aws_s3_bucket": ("bucket", "PhysicalDataset"),
    "aws_dynamodb_table": ("name", "PhysicalDataset"),
    "aws_glue_catalog_database": ("name", "PhysicalDataset"),
    "aws_glue_catalog_table": ("name", "PhysicalDataset"),
    "aws_cloudwatch_event_rule": ("name", "Trigger"),
}
VAR_PATH = re.compile(r"^\$\{var\.([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*)\}$")


def _files(root: Path):
    for directory, children, names in os.walk(root, followlinks=False):
        children[:] = sorted(name for name in children if name not in SKIP and not name.startswith(".") and not (Path(directory) / name).is_symlink())
        for name in sorted(names):
            path = Path(directory) / name
            if not path.is_symlink() and not name.startswith(".") and (path.suffix in {".tf", ".tfvars", ".py"} or name.endswith((".tfvars.json", ".tf.json"))):
                yield path


def _literal(value):
    return value if isinstance(value, str) and value and "${" not in value and "%{" not in value else None


class _Extraction:
    def __init__(self, root, namespace, environment):
        self.root, self.namespace, self.environment = root, namespace, environment
        self.nodes, self.evidence, self.claims, self.unresolved = {}, {}, {}, {}
        self.content = {}
        self.revision = ""
        self.references = []
        self.coverage = Counter(terraform_files=0, terraform_modules=0, resource_declarations=0, resources=0, python_files=0, sdk_references=0, unsupported=0)
        self.repository = self.identifier("repository", "source")
        self.nodes[self.repository] = Node(self.repository, "Repository", "source")

    def identifier(self, kind, *parts):
        return self.namespace.rstrip("/:") + "/" + kind + "/" + "/".join(quote(str(p), safe="") for p in parts)

    def cite(self, path, node=None):
        data = self.read(path)
        start = node.lineno if node else 1
        end = (getattr(node, "end_lineno", None) or start) if node else max(1, len(data.splitlines()))
        digest = sha256(data).hexdigest()
        item = Evidence.create(source_type="source", repository=self.namespace, revision=self.revision, path=path.relative_to(self.root).as_posix(), locator=f"L{start}-L{end}", content_hash=digest, extractor=EXTRACTOR, environment=self.environment, attributes={"locator_verified": True})
        self.evidence[item.evidence_id] = item
        return item.evidence_id

    def read(self, path):
        if path not in self.content:
            self.content[path] = path.read_bytes()
        return self.content[path]

    def gap(self, path, reason, subject=None, node=None, target="unresolved-resource", evidence_ids=()):
        ids = tuple(dict.fromkeys((self.cite(path, node), *evidence_ids)))
        source = subject or self.repository
        item = Unresolved.create(unresolved_id=stable_id("unresolved", {"source": source, "reason": reason, "evidence": ids, "target": target}), source_node_id=source, reason=reason, evidence_ids=ids, target_hint=target)
        self.unresolved[item.unresolved_id] = item
        self.coverage["unsupported"] += 1

    def resource(self, path, kind, address, name, evidence_ids):
        identity = self.identifier("resource", kind, path.relative_to(self.root).as_posix(), address, name)
        self.nodes[identity] = Node(identity, KINDS[kind][1], name, attributes={"resource_kind": kind, "resource_name": name, "environment": self.environment, "repository": self.namespace, "source_path": path.relative_to(self.root).as_posix(), "terraform_address": address})
        claim = Claim.create(subject=self.repository, predicate="CONTAINS", object=identity, evidence_ids=evidence_ids, assertion_kind="DECLARED", review_status="AUTO_VERIFIED", scope={"namespace": self.namespace, "environment": self.environment}, attributes={"lineage_orientation": "subject_to_object", "include_in_lineage": False, "relation_category": "structural", "verifier": EXTRACTOR, "rule": "terraform-static-registration"})
        self.claims[claim.claim_id] = claim
        self.coverage["resources"] += 1

    def terraform(self, paths, all_files):
        modules = defaultdict(list)
        for path in paths:
            modules[path.parent].append(path)
        self.coverage["terraform_modules"] = len(modules)
        for module, declarations in modules.items():
            overrides = [p for p in declarations if p.name in {"override.tf", "override.tf.json"} or p.name.endswith(("_override.tf", "_override.tf.json"))]
            json_declarations = [p for p in declarations if p.name.endswith(".tf.json")]
            if overrides or json_declarations:
                self.coverage["terraform_files"] += len(declarations)
                reason = (
                    "Terraform override files require merged module evaluation; this module remains unresolved."
                    if overrides else
                    "Terraform JSON configuration is unsupported; this module remains unresolved."
                )
                blockers = overrides or json_declarations
                for path in declarations:
                    self.gap(path, reason, evidence_ids=[self.cite(p) for p in blockers])
                continue
            allowed_dirs = {module, *(module / name for name in ("config", "configurations", "env", "environments"))}
            selected = [p for p in all_files if p.suffix == ".tfvars" and p.parent in allowed_dirs and (p.name == "terraform.tfvars" or (self.environment and p.name == self.environment + ".tfvars")) and (p.parent == module or p.parent not in modules)]
            variables = defaultdict(list)
            variable_parse_failed = False
            for path in selected:
                try:
                    parsed = hcl2.loads(self.read(path).decode("utf-8"))
                except Exception:
                    self.gap(path, "Selected Terraform variable source could not be parsed; no values were evaluated.")
                    variable_parse_failed = True
                    continue
                for name, value in parsed.items():
                    variables[name].append((value, path))
            auto_variables = [p for p in all_files if p.parent == module and (p.name.endswith(".auto.tfvars") or p.name.endswith(".auto.tfvars.json") or p.name == "terraform.tfvars.json")]
            for path in declarations:
                self.coverage["terraform_files"] += 1
                try:
                    parsed = hcl2.loads(self.read(path).decode("utf-8"))
                except Exception:
                    self.gap(path, "Terraform source could not be parsed; resource declarations remain unresolved.")
                    continue
                for block in parsed.get("resource", []):
                    for kind, entries in block.items():
                        for address, body in entries.items():
                            self.coverage["resource_declarations"] += 1
                            if kind not in KINDS:
                                self.gap(path, "Terraform resource kind is outside the static registration adapter.", target=kind + "." + address)
                                continue
                            if "provider" in body:
                                self.gap(path, "Explicit Terraform provider selection requires provider scope resolution.", target=kind + "." + address)
                                continue
                            name = body.get(KINDS[kind][0])
                            evidence_ids = [self.cite(path)]
                            if "count" in body:
                                if body["count"] == 0:
                                    continue
                                self.gap(path, "Terraform count-based resource registration is not evaluated.", target=kind + "." + address)
                                continue
                            if "for_each" not in body:
                                if _literal(name):
                                    self.resource(path, kind, address, name, evidence_ids)
                                else:
                                    self.gap(path, "Terraform resource name is absent or dynamic.", target=kind + "." + address)
                                continue
                            match = VAR_PATH.fullmatch(body["for_each"]) if isinstance(body["for_each"], str) else None
                            if name != "${each.key}" or not match:
                                self.gap(path, "Terraform for_each requires a direct variable map and each.key identity; expression evaluation is unsupported.", target=kind + "." + address)
                                continue
                            segments = match.group(1).split(".")
                            sources = variables.get(segments[0], [])
                            if variable_parse_failed or auto_variables or len(sources) != 1:
                                self.gap(path, "Terraform variable map has no unique selected source, or unhandled automatic overrides exist.", target=kind + "." + address, evidence_ids=[self.cite(p) for _, p in sources])
                                continue
                            value, variable_path = sources[0]
                            for segment in segments[1:]:
                                value = value.get(segment) if isinstance(value, dict) else None
                            evidence_ids.append(self.cite(variable_path))
                            if not isinstance(value, dict) or not all(_literal(key) for key in value):
                                self.gap(path, "Terraform registration map or its keys are dynamic or absent.", target=kind + "." + address, evidence_ids=evidence_ids)
                                continue
                            for resource_name in sorted(value):
                                self.resource(path, kind, address, resource_name, evidence_ids)

    def python(self, path):
        self.coverage["python_files"] += 1
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse(self.read(path).decode("utf-8"))
        except (SyntaxError, UnicodeError):
            self.gap(path, "Python source could not be parsed for static SDK references.")
            return
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in {"start_job_run", "invoke"}]
        if not calls:
            return
        script = self.identifier("script", path.relative_to(self.root).as_posix())
        self.nodes[script] = Node(script, "Script", path.relative_to(self.root).as_posix(), attributes={"repository": self.namespace, "source_path": path.relative_to(self.root).as_posix()})
        scopes = _python_scopes(tree)
        shadowed_package = (self.root / "boto3.py").exists() or (self.root / "boto3").exists() or (path.parent / "boto3.py").exists() or (path.parent / "boto3").exists()
        for call in calls:
            scope = scopes.get(id(call))
            service = None if shadowed_package or scope is None else scope.resolve(call.func.value, call.lineno)
            expected, argument, kind = {"start_job_run": ("client:glue", "JobName", "aws_glue_job"), "invoke": ("client:lambda", "FunctionName", "aws_lambda_function")}[call.func.attr]
            value = next((kw.value for kw in call.keywords if kw.arg == argument), None)
            literal = value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value else None
            if service != expected or not literal or any(kw.arg is None for kw in call.keywords):
                self.gap(path, "SDK receiver or target is not a unique static boto3 binding; invocation remains unresolved.", subject=script, node=call)
                continue
            # ARNs and aliases need account/qualifier-aware identity resolution.
            if ":" in literal or "/" in literal or "${" in literal:
                self.gap(path, "Qualified SDK target requires account or alias-aware resolution.", subject=script, node=call)
                continue
            self.references.append({"subject": script, "predicate": "INVOKES", "target_kind": kind, "target_name": literal, "evidence_ids": [self.cite(path, call)], "environment": self.environment})
            self.coverage["sdk_references"] += 1


class _Scope:
    def __init__(self, parent=None, is_class=False):
        self.parent = parent
        self.is_class = is_class
        self.bindings = defaultdict(list)
        self.wildcard_import = False

    def resolve(self, node, before, seen=frozenset()):
        if self.wildcard_import:
            return None
        if isinstance(node, ast.Name):
            if node.id in seen:
                return None
            choices = self.bindings.get(node.id)
            if choices is None:
                return self.parent.resolve(node, float("inf"), seen) if self.parent else None
            if len(choices) != 1:
                return None
            line, value = choices[0]
            if line >= before or value is None:
                return None
            if isinstance(value, str):
                return value
            return self.resolve(value, line, seen | {node.id})
        if isinstance(node, ast.Attribute):
            parent = self.resolve(node.value, before, seen)
            return "boto3.client" if parent == "boto3" and node.attr == "client" else None
        if isinstance(node, ast.Call) and self.resolve(node.func, before, seen) == "boto3.client":
            if len(node.args) > 1 or any(k.arg != "service_name" for k in node.keywords):
                return None
            service = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "service_name"), None)
            if isinstance(service, ast.Constant) and service.value in {"glue", "lambda"}:
                return "client:" + service.value
        return None


def _python_scopes(tree):
    scopes = {}

    def visit(node, scope, direct=True):
        scopes[id(node)] = scope
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            if hasattr(node, "name"):
                scope.bindings[node.name].append((node.lineno, None))
            child = _Scope(scope.parent if scope.is_class else scope, isinstance(node, ast.ClassDef))
            if hasattr(node, "args"):
                args = node.args
                for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs, *([args.vararg] if args.vararg else []), *([args.kwarg] if args.kwarg else [])]:
                    child.bindings[arg.arg].append((0, None))
            body = node.body if isinstance(node.body, list) else [node.body]
            for statement in body:
                visit(statement, child)
            return
        if isinstance(node, ast.Import):
            for item in node.names:
                scope.bindings[item.asname or item.name.split(".")[0]].append((node.lineno, "boto3" if direct and item.name == "boto3" else None))
        elif isinstance(node, ast.ImportFrom):
            for item in node.names:
                if item.name == "*":
                    scope.wildcard_import = True
                    continue
                scope.bindings[item.asname or item.name].append((node.lineno, "boto3.client" if direct and node.module == "boto3" and node.level == 0 and item.name == "client" else None))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                receiver = target
                while isinstance(receiver, (ast.Attribute, ast.Subscript)):
                    receiver = receiver.value
                if receiver is not target and isinstance(receiver, ast.Name):
                    scope.bindings[receiver.id].append((node.lineno, None))
                for name in ast.walk(target):
                    if isinstance(name, ast.Name) and isinstance(name.ctx, ast.Store):
                        scope.bindings[name.id].append((node.lineno, node.value if direct and isinstance(target, ast.Name) else None))
            if node.value is not None:
                visit(node.value, scope, direct)
            return
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            scope.bindings[node.id].append((node.lineno, None))
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, (ast.Store, ast.Del)):
            receiver = node.value
            while isinstance(receiver, ast.Attribute):
                receiver = receiver.value
            if isinstance(receiver, ast.Name):
                scope.bindings[receiver.id].append((node.lineno, None))
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            for name in node.names:
                scope.bindings[name].append((node.lineno, None))
        compound = isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.Match, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp))
        for child in ast.iter_child_nodes(node):
            visit(child, scope, direct and not compound)

    visit(tree, _Scope())
    return scopes


def extract_resources(root: Path, namespace: str, environment: str | None = None) -> tuple[GraphBundle, list[dict], dict]:
    """Read one local repository and return proven resources plus unresolved refs."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("resource source must be a real directory")
    if not namespace or ":" not in namespace or any(char.isspace() for char in namespace):
        raise ValueError("resource namespace must be an absolute URI")
    if environment is not None and not re.fullmatch(r"[A-Za-z0-9_-]+", environment):
        raise ValueError("environment must be a simple deployment name")
    root = root.resolve()
    result = _Extraction(root, namespace, environment)
    files = list(_files(root))
    # Pin the complete adapter input once. Per-file hashes remain on evidence,
    # while source revision identifies the repository snapshot rather than
    # advertising every file as a separate revision of the same repository.
    inventory = [(p.relative_to(root).as_posix(), sha256(result.read(p)).hexdigest()) for p in files]
    result.revision = "sha256:" + sha256(json.dumps(inventory, separators=(",", ":")).encode()).hexdigest()
    result.terraform([p for p in files if p.suffix == ".tf" or p.name.endswith(".tf.json")], files)
    for path in files:
        if path.suffix == ".py":
            result.python(path)
    bundle = GraphBundle(nodes=tuple(result.nodes.values()), evidence=tuple(result.evidence.values()), claims=tuple(result.claims.values()), unresolved=tuple(result.unresolved.values()))
    coverage = dict(result.coverage)
    coverage.update({"environment": environment, "assertion_kind": "DECLARED", "runtime_verified": False, "supported": ["terraform-literal-resources", "terraform-selected-variable-map-keys", "python-static-boto3-calls"], "excluded_directories": sorted(SKIP)})
    return bundle, result.references, coverage
