"""Conservative Airflow source extraction. Never import or execute a DAG file."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from hashlib import sha256
import json
import warnings
from pathlib import Path
from urllib.parse import quote, urlsplit

from .bundle import BundleValidationError, GraphBundle
from .model import Claim, Evidence, Node, Unresolved, stable_id


EXTRACTOR = "palgwae-airflow-ast-v1"
RELATIONS = {
    "CONTAINS": ("subject_to_object", False),
    "NEXT": ("subject_to_object", True),
    "WAITS_FOR": ("object_to_subject", True),
}
RULES = {
    "dag-task": "CONTAINS",
    "bitshift": "NEXT",
    "taskflow-input": "NEXT",
    "set-dependency": "NEXT",
    "external-task": "WAITS_FOR",
}
RESOURCE_OPERATORS = {
    "airflow.providers.amazon.aws.operators.glue.GlueJobOperator": (
        "job_name", "aws_glue_job"
    ),
    "airflow.providers.amazon.aws.operators.lambda_function.LambdaInvokeFunctionOperator": (
        "function_name", "aws_lambda_function"
    ),
}


def _digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((item.value for item in call.keywords if item.arg == name), None)


def _literal(value: ast.AST | None) -> str | None:
    if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value:
        return value.value
    return None


def _aws_scope_safe(call: ast.Call) -> bool:
    if any(item.arg is None for item in call.keywords):
        return False
    connection = _keyword(call, "aws_conn_id")
    if connection is not None and _literal(connection) != "aws_default":
        return False
    scope_keys = {"region_name", "botocore_config", "endpoint_url"}
    if any(_keyword(call, key) is not None for key in scope_keys):
        return False
    defaults = _keyword(call, "default_args")
    if defaults is None:
        return True
    if not isinstance(defaults, ast.Dict):
        return False
    for key, value in zip(defaults.keys, defaults.values):
        name = _literal(key)
        if name is None or name in scope_keys:
            return False
        if name == "aws_conn_id" and _literal(value) != "aws_default":
            return False
    return True


@dataclass
class Extraction:
    """Candidates are separate from predicate-specific promotion."""

    namespace: str
    revision: str
    nodes: dict[str, Node] = field(default_factory=dict)
    evidence: dict[str, Evidence] = field(default_factory=dict)
    candidates: list[tuple[str, str, str, str, tuple[str, ...]]] = field(default_factory=list)
    unresolved: list[Unresolved] = field(default_factory=list)
    dags: dict[str, str] = field(default_factory=dict)
    tasks: dict[tuple[str, str], str] = field(default_factory=dict)
    sensors: list[tuple[str, str | None, str | None, str]] = field(default_factory=list)
    resource_references: list[dict] = field(default_factory=list)
    files: int = 0
    airflow_files: int = 0

    def identifier(self, kind: str, *parts: str) -> str:
        return (
            self.namespace.rstrip("/:")
            + "/"
            + kind
            + "/"
            + "/".join(quote(p, safe="") for p in parts)
        )

    def gap(self, source: str | None, evidence: str, reason: str) -> None:
        source = source or self.identifier("repository", "source")
        if source not in self.nodes:
            self.nodes[source] = Node(source, "Repository", "source")
        self.unresolved.append(
            Unresolved.create(
                unresolved_id=stable_id(
                    "unresolved", {"source": source, "evidence": evidence, "reason": reason}
                ),
                source_node_id=source,
                target_hint="unresolved-control-flow",
                reason=reason,
                evidence_ids=[evidence],
            )
        )

    def promote(self) -> GraphBundle:
        """Accept only the documented AST rules and locally resolved endpoints."""
        candidates = list(self.candidates)
        for source, dag, task, evidence in self.sensors:
            target = self.tasks.get((dag, task)) if dag and task else None
            if target:
                candidates.append((source, "WAITS_FOR", target, "external-task", (evidence,)))
            else:
                self.gap(
                    source,
                    evidence,
                    "ExternalTaskSensor target is dynamic, absent, or DAG-level; runtime timing is not proven.",
                )
        claims: dict[str, Claim] = {}
        for subject, predicate, target, rule, evidence_ids in candidates:
            if (
                RULES.get(rule) != predicate
                or subject not in self.nodes
                or target not in self.nodes
            ):
                raise BundleValidationError("Airflow candidate failed the predicate gate")
            if any(
                e not in self.evidence
                or self.evidence[e].attributes.get("locator_verified") is not True
                for e in evidence_ids
            ):
                raise BundleValidationError("Airflow candidate has unverified evidence")
            if predicate != "CONTAINS" and (
                self.nodes[subject].node_type != "Task" or self.nodes[target].node_type != "Task"
            ):
                raise BundleValidationError("Airflow dependency endpoints must be tasks")
            if (
                predicate == "NEXT"
                and self.nodes[subject].attributes["orchestrator"]
                != self.nodes[target].attributes["orchestrator"]
            ):
                raise BundleValidationError("Airflow NEXT cannot cross DAGs")
            orientation, include = RELATIONS[predicate]
            claim = Claim.create(
                subject=subject,
                predicate=predicate,
                object=target,
                evidence_ids=evidence_ids,
                assertion_kind="DECLARED",
                review_status="AUTO_VERIFIED",
                confidence=1.0,
                scope={"namespace": self.namespace, "revision": self.revision},
                attributes={
                    "lineage_orientation": orientation,
                    "include_in_lineage": include,
                    "relation_category": "structural" if predicate == "CONTAINS" else "control",
                    "verifier": EXTRACTOR,
                    "rule": rule,
                },
            )
            claims[claim.claim_id] = claim
        used = {e for c in claims.values() for e in c.evidence_ids} | {
            e for u in self.unresolved for e in u.evidence_ids
        } | {
            e for reference in self.resource_references for e in reference["evidence_ids"]
        }
        return GraphBundle(
            nodes=tuple(self.nodes.values()),
            evidence=tuple(e for key, e in self.evidence.items() if key in used),
            claims=tuple(claims.values()),
            unresolved=tuple({u.unresolved_id: u for u in self.unresolved}.values()),
        )


class Source:
    def __init__(self, result: Extraction, path: str, data: bytes):
        self.result, self.path, self.data = result, path, data
        self.imports: dict[str, str] = {}
        self.bindings: dict[str, list[str]] = {}
        self.factories: dict[str, tuple[ast.FunctionDef, ast.expr]] = {}
        self.task_functions: dict[str, str] = {}
        self.dag_bindings: dict[str, str] = {}
        self.dag_aws_scopes: dict[str, tuple[bool, str]] = {}
        self.called: set[str] = set()
        self.call_cache: dict[int, list[str]] = {}
        self.active_dag: str | None = None

    def name(self, value: ast.AST) -> str:
        if isinstance(value, ast.Name):
            return self.imports.get(value.id, "")
        if isinstance(value, ast.Attribute):
            parent = self.name(value.value)
            return parent + "." + value.attr if parent else ""
        return ""

    def is_airflow(self, value: ast.AST, terminal: str) -> bool:
        name = self.name(value)
        return name.startswith("airflow.") and name.rsplit(".", 1)[-1] == terminal

    def evidence(self, node: ast.AST) -> str:
        item = Evidence.create(
            source_type="source",
            repository=self.result.namespace,
            revision=self.result.revision,
            path=self.path,
            locator=f"L{node.lineno}-L{getattr(node, 'end_lineno', None) or node.lineno}",
            content_hash=sha256(self.data).hexdigest(),
            extractor=EXTRACTOR,
            attributes={"locator_verified": True},
        )
        self.result.evidence[item.evidence_id] = item
        return item.evidence_id

    def gap(self, node: ast.AST, reason: str) -> None:
        self.result.gap(self.active_dag, self.evidence(node), reason)

    def make_dag(self, call: ast.expr, fallback: str | None = None) -> str | None:
        value = (
            (_keyword(call, "dag_id") or (call.args[0] if call.args else None))
            if isinstance(call, ast.Call)
            else None
        )
        name = _literal(value) if value is not None else fallback
        if not name:
            self.gap(call, "Dynamic DAG identity is not evaluated.")
            return None
        if name in self.result.dags:
            raise BundleValidationError(
                "Duplicate DAG identity; narrow the source root to one deployment"
            )
        identity = self.result.identifier("dag", name)
        self.result.dags[name] = identity
        attributes = {"repository": self.result.namespace, "source_path": self.path}
        if isinstance(call, ast.Call):
            schedule = _keyword(call, "schedule") or _keyword(call, "schedule_interval")
            if _literal(schedule):
                attributes["schedule"] = _literal(schedule)
        self.result.nodes[identity] = Node(identity, "Orchestrator", name, attributes=attributes)
        self.dag_aws_scopes[identity] = (
            _aws_scope_safe(call) if isinstance(call, ast.Call) else True,
            self.evidence(call),
        )
        return identity

    def make_task(
        self, call: ast.Call, task_id: str | None, operator: str, dag: str | None
    ) -> list[str]:
        if not task_id or not dag:
            self.gap(
                call, "Task identity or DAG membership is dynamic or outside the supported context."
            )
            return []
        dag_name = self.result.nodes[dag].name
        key = (dag_name, task_id)
        if key in self.result.tasks:
            if operator != "TaskFlow":
                raise BundleValidationError("Duplicate task_id in a DAG; no bundle was written")
            self.gap(
                call,
                "Repeated task identity is not expanded; implicit TaskFlow suffixes require runtime resolution.",
            )
            return []
        identity = self.result.identifier("task", dag_name, task_id)
        self.result.tasks[key] = identity
        self.result.nodes[identity] = Node(
            identity,
            "Task",
            task_id,
            attributes={"orchestrator": dag, "operator": operator, "source_path": self.path},
        )
        evidence = self.evidence(call)
        self.result.candidates.append((dag, "CONTAINS", identity, "dag-task", (evidence,)))
        if operator.endswith("ExternalTaskSensor"):
            self.result.sensors.append(
                (
                    identity,
                    _literal(_keyword(call, "external_dag_id")),
                    _literal(_keyword(call, "external_task_id")),
                    evidence,
                )
            )
        if operator in RESOURCE_OPERATORS:
            argument, target_kind = RESOURCE_OPERATORS[operator]
            target_name = _literal(_keyword(call, argument))
            dag_scope_safe, dag_evidence = self.dag_aws_scopes[dag]
            if not _aws_scope_safe(call) or not dag_scope_safe:
                self.result.gap(
                    identity,
                    evidence,
                    "Airflow AWS connection or region scope, including inherited defaults, cannot be resolved; "
                    "no resource target was inferred.",
                )
            elif target_name is None:
                self.result.gap(
                    identity,
                    evidence,
                    f"{operator.rsplit('.', 1)[-1]} {argument} is absent or dynamic; "
                    "no resource target was inferred.",
                )
            else:
                self.result.resource_references.append(
                    {
                        "subject": identity,
                        "predicate": "STARTS",
                        "target_kind": target_kind,
                        "target_name": target_name,
                        "evidence_ids": [evidence, dag_evidence],
                        "environment": None,
                    }
                )
        return [identity]

    def connect(self, left: list[str], right: list[str], node: ast.AST, rule: str) -> None:
        if not left or not right:
            self.gap(node, "A dependency endpoint is unresolved; no edge was inferred.")
            return
        if rule == "bitshift" and len(left) > 1 and len(right) > 1:
            self.gap(node, "List-to-list bitshift is not a valid Airflow dependency operation.")
            return
        evidence = self.evidence(node)
        for source in left:
            for target in right:
                self.result.candidates.append((source, "NEXT", target, rule, (evidence,)))

    def expression(self, value: ast.AST | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, ast.Name):
            return self.bindings.get(value.id, [])
        if isinstance(value, (ast.List, ast.Tuple)):
            groups = [self.expression(v) for v in value.elts]
            return [item for group in groups for item in group] if all(groups) else []
        if isinstance(value, ast.Subscript):
            values = self.expression(value.value)
            if (
                len(values) == 1
                and _literal(value.slice) is not None
                and self.result.nodes[values[0]].attributes.get("operator") == "TaskFlow"
            ):
                return values
            return []
        if isinstance(value, ast.BinOp) and isinstance(value.op, (ast.RShift, ast.LShift)):
            left, right = self.expression(value.left), self.expression(value.right)
            self.connect(
                left if isinstance(value.op, ast.RShift) else right,
                right if isinstance(value.op, ast.RShift) else left,
                value,
                "bitshift",
            )
            return right
        if not isinstance(value, ast.Call):
            return []
        if id(value) in self.call_cache:
            return self.call_cache[id(value)]
        function = value.func
        if isinstance(function, ast.Name) and function.id in self.factories:
            if function.id in self.called:
                self.gap(value, "Repeated DAG factory call was not expanded.")
                return []
            definition, decorator = self.factories[function.id]
            self.called.add(function.id)
            if value.args or value.keywords or definition.args.args:
                self.gap(value, "Parameterized DAG factory was not evaluated.")
                return []
            previous = self.active_dag
            self.active_dag = self.make_dag(decorator, definition.name)
            if self.active_dag:
                old_bindings, old_tasks = self.bindings.copy(), self.task_functions.copy()
                self.statements(definition.body)
                self.bindings, self.task_functions = old_bindings, old_tasks
            self.active_dag = previous
            return []
        override = None
        if (
            isinstance(function, ast.Call)
            and isinstance(function.func, ast.Attribute)
            and function.func.attr == "override"
        ):
            override = _literal(_keyword(function, "task_id"))
            function = function.func.value
            if override is None:
                self.gap(value, "Task override without a literal task_id was not expanded.")
                return []
        if isinstance(function, ast.Name) and function.id in self.task_functions:
            # Evaluate nested TaskFlow inputs before creating the receiving task.
            inputs = [self.expression(v) for v in [*value.args, *(k.value for k in value.keywords)]]
            tasks = self.make_task(
                value, override or self.task_functions[function.id], "TaskFlow", self.active_dag
            )
            for upstream in inputs:
                if upstream:
                    self.connect(upstream, tasks, value, "taskflow-input")
            self.call_cache[id(value)] = tasks
            return tasks
        name = self.name(function)
        if name.startswith("airflow.") and name.endswith(("Operator", "Sensor")):
            dag_value = _keyword(value, "dag")
            dag = (
                (self.dag_bindings.get(dag_value.id) if isinstance(dag_value, ast.Name) else None)
                if dag_value is not None
                else self.active_dag
            )
            tasks = self.make_task(value, _literal(_keyword(value, "task_id")), name, dag)
            self.call_cache[id(value)] = tasks
            return tasks
        if isinstance(function, ast.Attribute) and function.attr in {
            "set_downstream",
            "set_upstream",
        }:
            left = self.expression(function.value)
            right = self.expression(value.args[0]) if len(value.args) == 1 else []
            self.connect(
                left if function.attr == "set_downstream" else right,
                right if function.attr == "set_downstream" else left,
                value,
                "set-dependency",
            )
        elif self.active_dag and (
            isinstance(function, ast.Attribute)
            and function.attr in {"expand", "expand_kwargs", "partial"}
        ):
            self.gap(value, "Dynamic task mapping is not expanded.")
        return []

    def statements(self, statements: list[ast.stmt]) -> None:
        for node in statements:
            if isinstance(node, ast.ImportFrom):
                if any(item.name == "*" for item in node.names):
                    self.imports.clear()
                    self.gap(node, "Wildcard imports may shadow Airflow bindings; named imports must re-establish them.")
                    continue
                for item in node.names:
                    self.imports[item.asname or item.name] = (
                        "." * node.level + (node.module or "") + "." + item.name
                    )
            elif isinstance(node, ast.Import):
                for item in node.names:
                    self.imports[item.asname or item.name.split(".")[0]] = (
                        item.name if item.asname else item.name.split(".")[0]
                    )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.imports.pop(node.name, None)
                self.bindings.pop(node.name, None)
                self.task_functions.pop(node.name, None)
                for decorator in node.decorator_list:
                    func = decorator.func if isinstance(decorator, ast.Call) else decorator
                    if self.is_airflow(func, "dag"):
                        self.factories[node.name] = (node, decorator)
                    if self.is_airflow(func, "task"):
                        specified = (
                            _keyword(decorator, "task_id")
                            if isinstance(decorator, ast.Call)
                            else None
                        )
                        name = _literal(specified) if specified is not None else node.name
                        if name:
                            self.task_functions[node.name] = name
                        else:
                            self.gap(node, "Decorated task has a dynamic task_id.")
            elif isinstance(node, ast.With):
                item = node.items[0]
                call = item.context_expr
                if (
                    len(node.items) == 1
                    and isinstance(call, ast.Call)
                    and self.is_airflow(call.func, "DAG")
                ):
                    previous = self.active_dag
                    self.active_dag = self.make_dag(call)
                    if self.active_dag:
                        if isinstance(item.optional_vars, ast.Name):
                            self.dag_bindings[item.optional_vars.id] = self.active_dag
                        self.statements(node.body)
                    self.active_dag = previous
                elif self.active_dag:
                    self.gap(
                        node,
                        "Unsupported context manager (including TaskGroup); its body was not expanded.",
                    )
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                value = node.value
                if isinstance(value, ast.Call) and self.is_airflow(value.func, "DAG"):
                    dag = self.make_dag(value)
                    for target in targets:
                        if isinstance(target, ast.Name) and dag:
                            self.dag_bindings[target.id] = dag
                else:
                    binding = self.expression(value)
                    for target in targets:
                        if isinstance(target, ast.Name):
                            self.bindings[target.id] = binding
                            # Python assignment shadows imported constructors and decorated functions.
                            self.imports.pop(target.id, None)
                            self.task_functions.pop(target.id, None)
            elif isinstance(node, ast.Expr):
                self.expression(node.value)
            elif isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.Match)):
                self.gap(
                    node,
                    "Conditional, loop, or exception-controlled code was not executed or expanded.",
                )
                for child in ast.walk(node):
                    if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                        self.bindings.pop(child.id, None)
                        self.imports.pop(child.id, None)
                        self.task_functions.pop(child.id, None)
            elif isinstance(node, ast.ClassDef):
                self.imports.pop(node.name, None)


def extract_airflow(source: str | Path, namespace: str) -> Extraction:
    """Extract literal DAG/task identities and control dependencies from Python files."""
    if (
        not namespace
        or urlsplit(namespace).scheme not in {"urn", "https", "http"}
        or any(c.isspace() for c in namespace)
    ):
        raise BundleValidationError(
            "namespace must be an organization-controlled urn: or https:// URI"
        )
    root = Path(source).expanduser().resolve()
    if not root.is_dir():
        raise BundleValidationError("Airflow source must be a directory")
    files = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if any(
            p.startswith(".") or p in {"__pycache__", "node_modules", "venv", "dist", "build"}
            for p in relative.parts
        ):
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            continue
        files.append((relative.as_posix(), path.read_bytes().replace(b"\r\n", b"\n")))
    revision = "sha256:" + _digest([(p, sha256(data).hexdigest()) for p, data in files])
    result = Extraction(namespace, revision, files=len(files))
    for path, data in files:
        parser = Source(result, path, data)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse(data, filename=path)
        except (SyntaxError, UnicodeError):
            marker = ast.Constant(value=None, lineno=1, end_lineno=max(1, len(data.splitlines())))
            parser.gap(
                marker,
                "Python source could not be parsed; no claims were extracted from this file.",
            )
            continue
        if not any(
            isinstance(n, ast.ImportFrom)
            and (n.module or "").split(".")[0] == "airflow"
            or isinstance(n, ast.Import)
            and any(a.name.split(".")[0] == "airflow" for a in n.names)
            for n in tree.body
        ):
            continue
        result.airflow_files += 1
        parser.statements(tree.body)
        for name, (definition, _) in parser.factories.items():
            if name not in parser.called:
                parser.gap(
                    definition,
                    "DAG factory has no supported top-level call; its body was not expanded.",
                )
    return result


def build_airflow(source: str | Path, output: str | Path, namespace: str) -> dict:
    result = extract_airflow(source, namespace)
    if not result.dags:
        raise BundleValidationError(
            "No statically resolvable Airflow DAGs found; use a DAG source directory with literal identities"
        )
    bundle = result.promote()
    bundle.write(
        output,
        metadata={
            "project": namespace,
            "source_revision": result.revision,
            "adapter": EXTRACTOR,
            "source_files": result.files,
            "airflow_files": result.airflow_files,
            "ontology": {
                "name": "palgwae-airflow-control",
                "version": "1",
                "entities_sha256": "sha256:"
                + _digest(
                    {
                        "Repository": ["name"],
                        "Orchestrator": ["repository", "name"],
                        "Task": ["orchestrator", "name"],
                    }
                ),
                "relations_sha256": "sha256:" + _digest(RELATIONS),
            },
        },
    )
    report = GraphBundle.load(output).doctor()
    report["extraction"] = {
        "files_scanned": result.files,
        "airflow_files": result.airflow_files,
        "dags": len(result.dags),
        "tasks": len(result.tasks),
        "candidates": len(bundle.claims),
        "unresolved": len(bundle.unresolved),
        "scope": "declared-control-flow-only",
        "source_revision": result.revision,
    }
    return report
