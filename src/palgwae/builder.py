"""Compile a small, reviewable project manifest into a portable graph bundle."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping

from .bundle import BundleValidationError, GraphBundle
from .model import Claim, Evidence, Node, Unresolved, is_pinned_revision


_LINE_LOCATOR = re.compile(r"^L([1-9][0-9]*)(?:-L?([1-9][0-9]*))?$")


def load_spec(path: str | Path) -> dict[str, Any]:
    """Load a JSON or YAML graph specification.

    JSON uses the standard library. YAML uses the declared PyYAML dependency;
    neither format requires network access or a model call.
    """

    spec_path = Path(path).expanduser().resolve()
    try:
        text = spec_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BundleValidationError(f"cannot read spec {spec_path}: {exc}") from exc
    if spec_path.suffix.lower() == ".json":
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise BundleValidationError(f"invalid JSON spec: {exc}") from exc
    else:
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError as exc:
            raise BundleValidationError(
                "YAML specs require PyYAML; reinstall Palgwae or use a JSON spec"
            ) from exc
        try:
            value = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise BundleValidationError(f"invalid YAML spec: {exc}") from exc
    if not isinstance(value, dict):
        raise BundleValidationError("spec root must be an object")
    return value


def _source_path(spec_dir: Path, relative_name: str) -> Path:
    relative = PurePosixPath(relative_name)
    if relative.is_absolute() or ".." in relative.parts:
        raise BundleValidationError(
            f"evidence path must be relative to the spec: {relative_name!r}"
        )
    resolved = spec_dir.joinpath(*relative.parts).resolve()
    try:
        resolved.relative_to(spec_dir.resolve())
    except ValueError as exc:
        raise BundleValidationError(
            f"evidence path escapes the spec directory: {relative_name!r}"
        ) from exc
    return resolved


def _file_hash(path: Path) -> str:
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise BundleValidationError(f"cannot hash evidence file {path}: {exc}") from exc
    # Source evidence is text in the starter adapters. Normalizing checkout
    # line endings makes the same pinned source produce one digest on Unix and
    # Windows while leaving binary inputs byte-exact.
    if b"\x00" not in content:
        content = content.replace(b"\r\n", b"\n")
    return sha256(content).hexdigest()


def _line_locator_is_valid(path: Path, locator: str) -> bool:
    match = _LINE_LOCATOR.fullmatch(locator)
    if match is None:
        return False
    try:
        content = path.read_bytes()
    except OSError:
        return False
    if b"\x00" in content:
        return False
    line_count = len(content.replace(b"\r\n", b"\n").splitlines())
    start = int(match.group(1))
    end = int(match.group(2) or start)
    return start <= end <= line_count


def _project_info(spec: Mapping[str, Any]) -> tuple[str, str, str]:
    project = spec.get("project")
    if not isinstance(project, Mapping):
        raise BundleValidationError("spec.project must be an object")
    name = str(project.get("name") or "").strip()
    namespace = str(project.get("namespace") or name).strip()
    revision = str(project.get("revision") or "").strip()
    if not name or not namespace or not revision:
        raise BundleValidationError(
            "spec.project requires name, namespace, and an immutable revision"
        )
    if not is_pinned_revision(revision):
        raise BundleValidationError(
            f"spec.project.revision must be immutable, not {revision!r}"
        )
    return name, namespace, revision


def _ontology_path(spec_path: Path, relative_name: Any, label: str) -> Path:
    if not isinstance(relative_name, str) or not relative_name.strip():
        raise BundleValidationError(
            f"spec.ontology.{label} must be a relative YAML or JSON path"
        )
    relative = PurePosixPath(relative_name)
    if relative.is_absolute():
        raise BundleValidationError(
            f"spec.ontology.{label} must not be an absolute path"
        )
    path = (spec_path.parent / relative_name).resolve()
    if not path.is_file():
        raise BundleValidationError(f"{label} ontology does not exist: {path}")
    return path


def _load_ontology(
    spec: Mapping[str, Any], *, spec_path: Path
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, str],
]:
    ontology_value = spec.get("ontology")
    if not isinstance(ontology_value, Mapping):
        raise BundleValidationError(
            "spec.ontology must contain relative 'entities' and 'relations' paths"
        )
    entities_path = _ontology_path(
        spec_path, ontology_value.get("entities"), "entities"
    )
    relations_path = _ontology_path(
        spec_path, ontology_value.get("relations"), "relations"
    )
    entities_document = load_spec(entities_path)
    relations_document = load_spec(relations_path)

    entity_types = entities_document.get("entity_types")
    if not isinstance(entity_types, Mapping) or not entity_types:
        raise BundleValidationError(
            "entity ontology must contain a non-empty entity_types object"
        )
    normalized_entities: dict[str, dict[str, Any]] = {}
    for name, definition in entity_types.items():
        if not isinstance(definition, Mapping):
            raise BundleValidationError(
                f"ontology entity type {name!r} must be an object"
            )
        identity = definition.get("identity")
        if not isinstance(identity, list) or not identity:
            raise BundleValidationError(
                f"ontology entity type {name!r} must declare identity fields"
            )
        normalized_entities[str(name)] = dict(definition)

    relations = relations_document.get("relations")
    if not isinstance(relations, Mapping) or not relations:
        raise BundleValidationError(
            "relation ontology must contain a non-empty relations object"
        )
    normalized_relations: dict[str, dict[str, Any]] = {}
    for name, definition in relations.items():
        if not isinstance(definition, Mapping):
            raise BundleValidationError(
                f"ontology relation {name!r} must be an object"
            )
        direction = str(definition.get("dependency_direction", "")).lower()
        if direction not in {"subject_to_object", "object_to_subject"}:
            raise BundleValidationError(
                f"ontology relation {name!r} has invalid dependency_direction"
            )
        include = definition.get("include_in_lineage")
        if not isinstance(include, bool):
            raise BundleValidationError(
                f"ontology relation {name!r} must declare include_in_lineage"
            )
        normalized_relations[str(name).upper()] = dict(definition)

    entity_name = str(entities_document.get("name") or "").strip()
    relation_name = str(relations_document.get("name") or "").strip()
    entity_version = str(entities_document.get("version") or "").strip()
    relation_version = str(relations_document.get("version") or "").strip()
    if not entity_name or entity_name != relation_name:
        raise BundleValidationError(
            "entity and relation ontologies must declare the same non-empty name"
        )
    if not entity_version or entity_version != relation_version:
        raise BundleValidationError(
            "entity and relation ontologies must declare the same version"
        )
    summary = {
        "name": entity_name,
        "version": entity_version,
        "entities_sha256": f"sha256:{_file_hash(entities_path)}",
        "relations_sha256": f"sha256:{_file_hash(relations_path)}",
    }
    return normalized_entities, normalized_relations, summary


def _validate_node_identity(
    node: Node, entity_types: Mapping[str, Mapping[str, Any]]
) -> None:
    definition = entity_types.get(node.node_type)
    if definition is None:
        raise BundleValidationError(
            f"node {node.node_id} has entity type {node.node_type!r} "
            "which is absent from the entity ontology"
        )
    identity = definition.get("identity")
    missing: list[str] = []
    for field_name in identity:
        if field_name == "name":
            value: Any = node.name
        else:
            value = node.attributes.get(str(field_name))
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(str(field_name))
    if missing:
        raise BundleValidationError(
            f"node {node.node_id} is missing identity attributes: "
            + ", ".join(missing)
        )


def _evidence_from_embedded(
    value: Mapping[str, Any],
    *,
    spec_dir: Path,
    repository: str,
    revision: str,
) -> Evidence:
    relative_path = str(value.get("path") or "").strip()
    locator = str(value.get("locator") or value.get("symbol") or "").strip()
    if not relative_path or not locator:
        raise BundleValidationError("embedded evidence requires path and locator")
    source_path = _source_path(spec_dir, relative_path)
    actual_hash = _file_hash(source_path)
    expected_hash = str(
        value.get("content_hash", value.get("sha256", ""))
    ).removeprefix("sha256:")
    if expected_hash and expected_hash.lower() != actual_hash:
        raise BundleValidationError(
            f"source hash mismatch for {relative_path}: "
            f"expected {expected_hash}, got {actual_hash}"
        )
    attributes = dict(value.get("attributes") or {})
    attributes["locator_verified"] = _line_locator_is_valid(
        source_path, locator
    )
    if value.get("note") is not None:
        attributes["note"] = str(value["note"])
    return Evidence.create(
        evidence_id=value.get("evidence_id", value.get("id")),
        source_type=str(value.get("source_type") or "source"),
        repository=str(value.get("repository") or repository),
        revision=str(value.get("revision") or revision),
        path=relative_path,
        locator=locator,
        content_hash=actual_hash,
        extractor=str(value.get("extractor") or "palgwae build"),
        observed_at=value.get("observed_at"),
        environment=value.get("environment"),
        artifact_uri=value.get("artifact_uri"),
        excerpt=value.get("excerpt"),
        attributes=attributes,
    )


def compile_spec(path: str | Path) -> tuple[GraphBundle, dict[str, Any]]:
    """Compile entities and evidence-backed claims from a project spec."""

    spec_path = Path(path).expanduser().resolve()
    spec = load_spec(spec_path)
    version = spec.get("version", 1)
    if version not in (1, "1"):
        raise BundleValidationError(f"unsupported spec version: {version!r}")
    repository, namespace, revision = _project_info(spec)
    entity_ontology, relation_ontology, ontology_summary = _load_ontology(
        spec, spec_path=spec_path
    )

    entity_values = spec.get("entities", spec.get("nodes"))
    if not isinstance(entity_values, list):
        raise BundleValidationError("spec.entities must be a list")
    nodes = tuple(Node.from_dict(value) for value in entity_values)
    for node in nodes:
        _validate_node_identity(node, entity_ontology)

    evidence_by_id: dict[str, Evidence] = {}
    top_level_evidence = spec.get("evidence", [])
    if not isinstance(top_level_evidence, list):
        raise BundleValidationError("spec.evidence must be a list when present")
    for value in top_level_evidence:
        if not isinstance(value, Mapping):
            raise BundleValidationError("every evidence entry must be an object")
        item = _evidence_from_embedded(
            value,
            spec_dir=spec_path.parent,
            repository=repository,
            revision=revision,
        )
        existing = evidence_by_id.get(item.evidence_id)
        if existing and existing.to_dict() != item.to_dict():
            raise BundleValidationError(
                f"evidence ID collision: {item.evidence_id}"
            )
        evidence_by_id[item.evidence_id] = item

    claim_values = spec.get("claims")
    if not isinstance(claim_values, list):
        raise BundleValidationError("spec.claims must be a list")
    claims: list[Claim] = []
    for value in claim_values:
        if not isinstance(value, Mapping):
            raise BundleValidationError("every claim entry must be an object")
        evidence_ids: list[str] = []
        embedded_values = value.get("evidence", value.get("evidence_ids", ()))
        if isinstance(embedded_values, str):
            embedded_values = [embedded_values]
        if not isinstance(embedded_values, list):
            raise BundleValidationError("claim.evidence must be a list")
        for embedded in embedded_values:
            if isinstance(embedded, str):
                evidence_ids.append(embedded)
                continue
            if not isinstance(embedded, Mapping):
                raise BundleValidationError(
                    "claim evidence must be an evidence ID or object"
                )
            item = _evidence_from_embedded(
                embedded,
                spec_dir=spec_path.parent,
                repository=repository,
                revision=revision,
            )
            existing = evidence_by_id.get(item.evidence_id)
            if existing and existing.to_dict() != item.to_dict():
                raise BundleValidationError(
                    f"evidence ID collision: {item.evidence_id}"
                )
            evidence_by_id[item.evidence_id] = item
            evidence_ids.append(item.evidence_id)

        predicate = str(
            value.get("predicate", value.get("relation", ""))
        ).upper()
        claim_attributes = dict(value.get("attributes") or {})
        relation = relation_ontology.get(predicate)
        if relation is None:
            raise BundleValidationError(
                f"predicate {predicate!r} is absent from the relation ontology"
            )
        claim_attributes["lineage_orientation"] = relation[
            "dependency_direction"
        ]
        claim_attributes["include_in_lineage"] = relation[
            "include_in_lineage"
        ]
        if relation.get("category") is not None:
            claim_attributes["relation_category"] = relation["category"]

        scope = {"namespace": namespace, "revision": revision}
        scope.update(dict(value.get("scope") or {}))
        review_status = str(
            value.get("review_status", value.get("status", "CANDIDATE"))
        ).upper()
        if review_status == "AUTO_VERIFIED":
            unverifiable = [
                evidence_id
                for evidence_id in evidence_ids
                if evidence_id not in evidence_by_id
                or evidence_by_id[evidence_id].attributes.get(
                    "locator_verified"
                )
                is not True
            ]
            if unverifiable:
                raise BundleValidationError(
                    "AUTO_VERIFIED claims require valid line locators; "
                    f"claim {value.get('id') or predicate} has unverified "
                    "evidence: "
                    + ", ".join(unverifiable)
                )
        claims.append(
            Claim.create(
                claim_id=value.get("claim_id", value.get("id")),
                subject=value.get(
                    "subject", value.get("source", value.get("source_node_id"))
                ),
                predicate=predicate,
                object=value.get(
                    "object", value.get("target", value.get("target_node_id"))
                ),
                evidence_ids=evidence_ids,
                assertion_kind=str(
                    value.get("assertion_kind", "DECLARED")
                ).upper(),
                review_status=review_status,
                confidence=float(value.get("confidence", 1.0)),
                scope=scope,
                valid_from=value.get("valid_from"),
                valid_to=value.get("valid_to"),
                observed_at=value.get("observed_at"),
                attributes=claim_attributes,
            )
        )

    unresolved_values = spec.get("unresolved", [])
    if not isinstance(unresolved_values, list):
        raise BundleValidationError("spec.unresolved must be a list when present")
    unresolved: list[Unresolved] = []
    for value in unresolved_values:
        if not isinstance(value, Mapping):
            raise BundleValidationError("every unresolved entry must be an object")
        evidence_ids: list[str] = []
        embedded_values = value.get("evidence", value.get("evidence_ids", ()))
        if isinstance(embedded_values, str):
            embedded_values = [embedded_values]
        if not isinstance(embedded_values, list):
            raise BundleValidationError("unresolved.evidence must be a list")
        for embedded in embedded_values:
            if isinstance(embedded, str):
                evidence_ids.append(embedded)
                continue
            if not isinstance(embedded, Mapping):
                raise BundleValidationError(
                    "unresolved evidence must be an evidence ID or object"
                )
            item = _evidence_from_embedded(
                embedded,
                spec_dir=spec_path.parent,
                repository=repository,
                revision=revision,
            )
            existing = evidence_by_id.get(item.evidence_id)
            if existing and existing.to_dict() != item.to_dict():
                raise BundleValidationError(
                    f"evidence ID collision: {item.evidence_id}"
                )
            evidence_by_id[item.evidence_id] = item
            evidence_ids.append(item.evidence_id)
        unresolved.append(
            Unresolved.create(
                unresolved_id=value.get("unresolved_id", value.get("id")),
                source_node_id=value.get(
                    "source_node_id", value.get("source")
                ),
                target_hint=value.get("target_hint"),
                reason=value.get("reason"),
                evidence_ids=evidence_ids,
                attributes=dict(value.get("attributes") or {}),
            )
        )

    bundle = GraphBundle(
        nodes=nodes,
        evidence=tuple(evidence_by_id.values()),
        claims=tuple(claims),
        unresolved=tuple(unresolved),
    )
    errors, _ = bundle.validation_messages()
    if errors:
        raise BundleValidationError(errors)
    metadata = {
        "project": repository,
        "namespace": namespace,
        "source_revision": revision,
        "spec": spec_path.name,
        "method": "evidence-bounded-static-analysis",
        "ontology": ontology_summary,
    }
    return bundle, metadata


def build_bundle(
    spec_path: str | Path,
    output: str | Path,
    *,
    snapshot_id: str | None = None,
) -> GraphBundle:
    """Compile and write a spec, then reload it with full hash validation."""

    bundle, metadata = compile_spec(spec_path)
    bundle.write(output, snapshot_id=snapshot_id, metadata=metadata)
    return GraphBundle.load(output)
