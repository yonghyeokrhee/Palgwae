"""Portable JSONL bundle loading, validation, and hashing."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from typing import Any, Iterable, Mapping

from .model import (
    Claim,
    Evidence,
    ModelValidationError,
    Node,
    Unresolved,
    is_pinned_revision,
    read_jsonl,
    write_jsonl,
)


SCHEMA_VERSION = "1"
DATA_FILES = (
    "nodes.jsonl",
    "evidence.jsonl",
    "claims.jsonl",
    "unresolved.jsonl",
)
_SHA256_VALUE_PREFIX = "sha256:"
_LOCAL_UNIX_PATH = re.compile(
    r"(?<![A-Za-z0-9_.-])/(?:Users|home)/[^/\s]+(?:/|$)"
    r"|(?<![A-Za-z0-9_.-])/private/(?:tmp|var)(?:/|$)"
)
_WINDOWS_USER_PATH = re.compile(
    r"(?i)(?<![A-Za-z0-9_.-])[A-Z]:[\\/]Users[\\/][^\\/\s]+(?:[\\/]|$)"
)


class BundleValidationError(ValueError):
    """Raised when a bundle is malformed, unpinned, or internally inconsistent."""

    def __init__(self, errors: str | Iterable[str]) -> None:
        if isinstance(errors, str):
            self.errors = (errors,)
        else:
            self.errors = tuple(str(error) for error in errors)
        super().__init__("; ".join(self.errors))


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_bundle_file(bundle_dir: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise BundleValidationError(f"unsafe bundle file path: {name!r}")
    path = bundle_dir.joinpath(*relative.parts)
    try:
        path.resolve().relative_to(bundle_dir.resolve())
    except ValueError as exc:
        raise BundleValidationError(f"bundle file escapes root: {name!r}") from exc
    return path


def _manifest_file_hash(value: Any) -> str | None:
    if isinstance(value, str):
        return value.removeprefix("sha256:")
    if isinstance(value, Mapping):
        digest = value.get("sha256", value.get("hash"))
        return str(digest).removeprefix("sha256:") if digest else None
    return None


def _looks_like_local_absolute_path(value: str) -> bool:
    """Return whether a manifest string contains a machine-local path.

    ``Path.is_absolute`` follows the host OS, so a bundle built on Unix would
    otherwise accept a Windows user path (and vice versa). The pure path
    implementations make the check independent of the builder's operating
    system. URI values such as ``s3://`` and ``https://`` are not filesystem
    paths under either syntax.
    """

    candidate = value.strip()
    return bool(
        (candidate and PurePosixPath(candidate).is_absolute())
        or (candidate and PureWindowsPath(candidate).is_absolute())
        or _LOCAL_UNIX_PATH.search(value)
        or _WINDOWS_USER_PATH.search(value)
    )


def _portable_manifest_errors(
    value: Any,
    field_path: str = "manifest",
) -> list[str]:
    """Find machine-local absolute paths anywhere in manifest metadata."""

    errors: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            errors.extend(
                _portable_manifest_errors(nested, f"{field_path}.{key}")
            )
    elif isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            errors.extend(
                _portable_manifest_errors(nested, f"{field_path}[{index}]")
            )
    elif isinstance(value, str) and _looks_like_local_absolute_path(value):
        errors.append(
            f"{field_path} must be portable; local absolute paths are not allowed"
        )
    return errors


def _is_portability_error(message: str) -> bool:
    return "must be portable" in message or "repository-relative" in message


def _validated_ontology(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise BundleValidationError(
            "manifest.ontology must identify the compiled ontology"
        )
    result: dict[str, str] = {}
    expected_fields = {
        "name",
        "version",
        "entities_sha256",
        "relations_sha256",
    }
    extra_fields = sorted(set(value) - expected_fields)
    if extra_fields:
        raise BundleValidationError(
            "manifest.ontology has unsupported fields: "
            + ", ".join(extra_fields)
        )
    for field_name in expected_fields:
        field_value = str(value.get(field_name) or "").strip()
        if not field_value:
            raise BundleValidationError(
                f"manifest.ontology.{field_name} is required"
            )
        result[field_name] = field_value
    for field_name in ("entities_sha256", "relations_sha256"):
        digest = result[field_name]
        if not digest.startswith(_SHA256_VALUE_PREFIX):
            raise BundleValidationError(
                f"manifest.ontology.{field_name} must start with sha256:"
            )
        raw_digest = digest.removeprefix(_SHA256_VALUE_PREFIX)
        if len(raw_digest) != 64 or any(
            character not in "0123456789abcdef" for character in raw_digest
        ):
            raise BundleValidationError(
                f"manifest.ontology.{field_name} must contain a lowercase SHA-256"
            )
    return result


def _resolve_bundle_dir(path: str | Path) -> Path:
    root = Path(path).expanduser().resolve()
    if (root / "nodes.jsonl").is_file():
        return root
    if (root / "graph" / "nodes.jsonl").is_file():
        return root / "graph"
    return root


def _stable_bundle_digest(file_hashes: Mapping[str, str]) -> str:
    encoded = json.dumps(
        dict(sorted(file_hashes.items())),
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class GraphBundle:
    """An immutable-in-practice graph snapshot loaded from portable JSONL."""

    nodes: tuple[Node, ...]
    evidence: tuple[Evidence, ...]
    claims: tuple[Claim, ...]
    unresolved: tuple[Unresolved, ...] = ()
    bundle_dir: Path | None = None
    manifest: dict[str, Any] = field(default_factory=dict)
    file_hashes: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_spec(cls, spec: Mapping[str, Any]) -> "GraphBundle":
        """Build an in-memory bundle from a single JSON-compatible document."""

        try:
            nodes = tuple(Node.from_dict(record) for record in spec.get("nodes", ()))
            evidence = tuple(
                Evidence.from_dict(record) for record in spec.get("evidence", ())
            )
            claims = tuple(
                Claim.from_dict(record) for record in spec.get("claims", ())
            )
            unresolved = tuple(
                Unresolved.from_dict(record)
                for record in spec.get("unresolved", ())
            )
        except (TypeError, ModelValidationError, ValueError) as exc:
            raise BundleValidationError(str(exc)) from exc
        bundle = cls(
            nodes=nodes,
            evidence=evidence,
            claims=claims,
            unresolved=unresolved,
        )
        errors, _ = bundle.validation_messages()
        if errors:
            raise BundleValidationError(errors)
        return bundle

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        verify_hashes: bool = True,
    ) -> "GraphBundle":
        bundle_dir = _resolve_bundle_dir(path)
        manifest_path = bundle_dir / "manifest.json"
        if not bundle_dir.is_dir():
            raise BundleValidationError(f"bundle directory does not exist: {bundle_dir}")
        if not manifest_path.is_file():
            raise BundleValidationError(f"missing bundle manifest: {manifest_path}")

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BundleValidationError(f"invalid manifest: {exc}") from exc
        if not isinstance(manifest, dict):
            raise BundleValidationError("manifest must be a JSON object")

        allowed_manifest_fields = {
            "schema_version",
            "snapshot_id",
            "files",
            "sources",
            "ontology",
            "build",
        }
        extra_manifest_fields = sorted(set(manifest) - allowed_manifest_fields)
        if extra_manifest_fields:
            raise BundleValidationError(
                "manifest has unsupported fields: "
                + ", ".join(extra_manifest_fields)
            )
        missing_manifest_fields = sorted(
            {
                "schema_version",
                "snapshot_id",
                "files",
                "sources",
                "ontology",
            }
            - set(manifest)
        )
        if missing_manifest_fields:
            raise BundleValidationError(
                "manifest is missing fields: "
                + ", ".join(missing_manifest_fields)
            )
        schema_version = str(manifest.get("schema_version", ""))
        if schema_version != SCHEMA_VERSION:
            raise BundleValidationError(
                f"unsupported schema_version {schema_version!r}; expected {SCHEMA_VERSION}"
            )
        snapshot_id = manifest.get("snapshot_id")
        if not isinstance(snapshot_id, str) or not snapshot_id.strip():
            raise BundleValidationError(
                "manifest.snapshot_id must be a non-empty string"
            )
        build_metadata = manifest.get("build")
        if build_metadata is not None and not isinstance(build_metadata, dict):
            raise BundleValidationError("manifest.build must be an object")
        manifest_portability_errors = _portable_manifest_errors(manifest)

        declared_files = manifest.get("files")
        if not isinstance(declared_files, dict):
            raise BundleValidationError("manifest.files must be an object")
        declared_names = set(declared_files)
        required_names = set(DATA_FILES)
        if declared_names != required_names:
            missing = sorted(required_names - declared_names)
            extra = sorted(declared_names - required_names)
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if extra:
                details.append("unsupported " + ", ".join(extra))
            raise BundleValidationError(
                "manifest.files must contain exactly the bundle files: "
                + "; ".join(details)
            )

        file_hashes: dict[str, str] = {}
        hash_errors: list[str] = list(manifest_portability_errors)
        for name in DATA_FILES:
            path_for_file = _safe_bundle_file(bundle_dir, name)
            if not path_for_file.is_file():
                hash_errors.append(f"missing required bundle file: {name}")
                continue
            actual = sha256_file(path_for_file)
            file_hashes[name] = actual
            declared_hash = declared_files.get(name)
            if not isinstance(declared_hash, str):
                hash_errors.append(
                    f"manifest SHA-256 for {name} must be a string"
                )
                expected = None
            else:
                expected = _manifest_file_hash(declared_hash)
            if expected is None:
                hash_errors.append(f"manifest has no SHA-256 for {name}")
            elif verify_hashes and expected.lower() != actual:
                hash_errors.append(
                    f"hash mismatch for {name}: expected {expected}, got {actual}"
                )

        sources = manifest.get("sources")
        if not isinstance(sources, list) or not sources:
            hash_errors.append("manifest.sources must contain at least one pinned source")
        elif isinstance(sources, list):
            for index, source in enumerate(sources):
                if not isinstance(source, dict):
                    hash_errors.append(
                        f"manifest.sources[{index}] must be an object"
                    )
                    continue
                extra_source_fields = sorted(
                    set(source) - {"name", "revision"}
                )
                if extra_source_fields:
                    hash_errors.append(
                        f"manifest.sources[{index}] has unsupported fields: "
                        + ", ".join(extra_source_fields)
                    )
                name = str(source.get("name") or "").strip()
                revision = str(source.get("revision") or "").strip()
                if not name:
                    hash_errors.append(
                        f"manifest.sources[{index}].name is required"
                    )
                if not is_pinned_revision(revision):
                    hash_errors.append(
                        f"manifest.sources[{index}].revision must be immutable"
                    )
        try:
            _validated_ontology(manifest.get("ontology"))
        except BundleValidationError as exc:
            hash_errors.extend(exc.errors)
        if hash_errors:
            raise BundleValidationError(hash_errors)

        try:
            nodes = tuple(
                Node.from_dict(value)
                for value in read_jsonl(str(bundle_dir / "nodes.jsonl"))
            )
            evidence = tuple(
                Evidence.from_dict(value)
                for value in read_jsonl(str(bundle_dir / "evidence.jsonl"))
            )
            claims = tuple(
                Claim.from_dict(value)
                for value in read_jsonl(str(bundle_dir / "claims.jsonl"))
            )
            unresolved = tuple(
                Unresolved.from_dict(value)
                for value in read_jsonl(str(bundle_dir / "unresolved.jsonl"))
            )
        except (OSError, json.JSONDecodeError, ModelValidationError, ValueError) as exc:
            raise BundleValidationError(f"invalid bundle record: {exc}") from exc

        bundle = cls(
            nodes=nodes,
            evidence=evidence,
            claims=claims,
            unresolved=unresolved,
            bundle_dir=bundle_dir,
            manifest=manifest,
            file_hashes=file_hashes,
        )
        errors, _ = bundle.validation_messages()
        if errors:
            raise BundleValidationError(errors)
        return bundle

    @property
    def node_index(self) -> dict[str, Node]:
        return {node.node_id: node for node in self.nodes}

    @property
    def evidence_index(self) -> dict[str, Evidence]:
        return {item.evidence_id: item for item in self.evidence}

    @property
    def claim_index(self) -> dict[str, Claim]:
        return {claim.claim_id: claim for claim in self.claims}

    @property
    def unresolved_index(self) -> dict[str, Unresolved]:
        return {item.unresolved_id: item for item in self.unresolved}

    @property
    def bundle_digest(self) -> str:
        hashes = self.file_hashes
        if not hashes and self.bundle_dir:
            hashes = {
                name: sha256_file(self.bundle_dir / name)
                for name in DATA_FILES
                if (self.bundle_dir / name).is_file()
            }
        return _stable_bundle_digest(hashes) if hashes else ""

    @property
    def manifest_digest(self) -> str:
        if self.bundle_dir and (self.bundle_dir / "manifest.json").is_file():
            return sha256_file(self.bundle_dir / "manifest.json")
        if self.manifest:
            encoded = json.dumps(
                self.manifest,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            return sha256(encoded.encode("utf-8")).hexdigest()
        return ""

    @property
    def snapshot_id(self) -> str:
        value = self.manifest.get("snapshot_id")
        return str(value) if value else f"snapshot:{self.bundle_digest[:16]}"

    def validation_messages(self) -> tuple[list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []

        for label, values in (
            ("node", self.nodes),
            ("evidence", self.evidence),
            ("claim", self.claims),
            ("unresolved", self.unresolved),
        ):
            for index, value in enumerate(values):
                try:
                    value.validate()
                except ModelValidationError as exc:
                    errors.append(f"invalid {label} record {index}: {exc}")

        node_ids = [node.node_id for node in self.nodes]
        evidence_ids = [item.evidence_id for item in self.evidence]
        claim_ids = [claim.claim_id for claim in self.claims]
        unresolved_ids = [item.unresolved_id for item in self.unresolved]
        for label, identifiers in (
            ("node", node_ids),
            ("evidence", evidence_ids),
            ("claim", claim_ids),
            ("unresolved", unresolved_ids),
        ):
            duplicates = sorted(
                identifier
                for identifier in set(identifiers)
                if identifiers.count(identifier) > 1
            )
            errors.extend(f"duplicate {label} ID: {identifier}" for identifier in duplicates)

        node_set = set(node_ids)
        evidence_set = set(evidence_ids)
        used_evidence: set[str] = set()
        accepted_edges: dict[tuple[str, str, str], str] = {}
        for claim in self.claims:
            if claim.subject not in node_set:
                errors.append(
                    f"claim {claim.claim_id} has missing subject node {claim.subject}"
                )
            if claim.object not in node_set:
                errors.append(
                    f"claim {claim.claim_id} has missing object node {claim.object}"
                )
            for evidence_id in claim.evidence_ids:
                used_evidence.add(evidence_id)
                if evidence_id not in evidence_set:
                    errors.append(
                        f"claim {claim.claim_id} references missing evidence {evidence_id}"
                    )
            if claim.accepted:
                orientation = claim.attributes.get("lineage_orientation")
                if orientation not in {
                    "subject_to_object",
                    "object_to_subject",
                }:
                    errors.append(
                        f"accepted claim {claim.claim_id} has no valid "
                        "ontology lineage_orientation"
                    )
                if not isinstance(
                    claim.attributes.get("include_in_lineage"), bool
                ):
                    errors.append(
                        f"accepted claim {claim.claim_id} has no boolean "
                        "ontology include_in_lineage"
                    )
                key = (claim.subject, claim.predicate, claim.object)
                previous = accepted_edges.get(key)
                if previous:
                    errors.append(
                        f"duplicate accepted edge {key!r}: {previous}, {claim.claim_id}"
                    )
                accepted_edges[key] = claim.claim_id

        for item in self.evidence:
            path = PurePosixPath(item.path)
            windows_path = PureWindowsPath(item.path)
            if (
                path.is_absolute()
                or windows_path.is_absolute()
                or ".." in path.parts
                or ".." in windows_path.parts
            ):
                errors.append(
                    f"evidence {item.evidence_id} path must be portable and "
                    "repository-relative"
                )

        errors.extend(_portable_manifest_errors(self.manifest))

        for item in self.unresolved:
            if item.source_node_id not in node_set:
                errors.append(
                    f"unresolved {item.unresolved_id} has missing source node "
                    f"{item.source_node_id}"
                )
            for evidence_id in item.evidence_ids:
                used_evidence.add(evidence_id)
                if evidence_id not in evidence_set:
                    errors.append(
                        f"unresolved {item.unresolved_id} references missing "
                        f"evidence {evidence_id}"
                    )

        unused = sorted(evidence_set - used_evidence)
        warnings.extend(f"unused evidence: {identifier}" for identifier in unused)
        if not any(claim.accepted for claim in self.claims):
            warnings.append("bundle has no accepted claims; traversal will return UNKNOWN")
        return errors, warnings

    def write(
        self,
        output: str | Path,
        *,
        snapshot_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> Path:
        """Write a deterministic bundle and a content-addressed manifest."""

        input_portability_errors = _portable_manifest_errors(
            {
                "snapshot_id": snapshot_id,
                "metadata": dict(metadata or {}),
            },
            "bundle",
        )
        if input_portability_errors:
            raise BundleValidationError(input_portability_errors)

        output_path = Path(output).expanduser().resolve()
        output_path.mkdir(parents=True, exist_ok=True)
        errors, _ = self.validation_messages()
        if errors:
            raise BundleValidationError(errors)

        ordered_records: dict[str, list[dict[str, Any]]] = {
            "nodes.jsonl": [
                item.to_dict()
                for item in sorted(self.nodes, key=lambda item: item.node_id)
            ],
            "evidence.jsonl": [
                item.to_dict()
                for item in sorted(
                    self.evidence, key=lambda item: item.evidence_id
                )
            ],
            "claims.jsonl": [
                item.to_dict()
                for item in sorted(self.claims, key=lambda item: item.claim_id)
            ],
            "unresolved.jsonl": [
                item.to_dict()
                for item in sorted(
                    self.unresolved, key=lambda item: item.unresolved_id
                )
            ],
        }
        for name, records in ordered_records.items():
            write_jsonl(str(output_path / name), records)

        file_hashes = {
            name: sha256_file(output_path / name) for name in DATA_FILES
        }
        digest = _stable_bundle_digest(file_hashes)
        metadata_value = dict(metadata or {})
        source_name = str(
            metadata_value.pop("project", metadata_value.pop("source_name", "graph-spec"))
        )
        source_revision = str(
            metadata_value.pop(
                "source_revision",
                metadata_value.pop("revision", f"snapshot:{digest[:16]}"),
            )
        )
        if not source_name:
            raise BundleValidationError("metadata project/source_name is required")
        if not is_pinned_revision(source_revision):
            raise BundleValidationError(
                f"metadata source revision must be immutable, not {source_revision!r}"
            )
        ontology = _validated_ontology(metadata_value.pop("ontology", None))
        sources = {
            (source_name, source_revision),
            *(
                (item.repository, item.revision)
                for item in self.evidence
            ),
        }
        manifest: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "snapshot_id": snapshot_id or f"snapshot:{digest[:16]}",
            "files": {
                name: f"sha256:{file_hashes[name]}"
                for name in DATA_FILES
            },
            "sources": [
                {"name": name, "revision": revision}
                for name, revision in sorted(sources)
            ],
            "ontology": ontology,
        }
        if metadata_value:
            manifest["build"] = metadata_value
        manifest_portability_errors = _portable_manifest_errors(manifest)
        if manifest_portability_errors:
            raise BundleValidationError(manifest_portability_errors)
        (output_path / "manifest.json").write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        self.bundle_dir = output_path
        self.manifest = manifest
        self.file_hashes = file_hashes
        return output_path

    def doctor(self) -> dict[str, Any]:
        errors, warnings = self.validation_messages()
        counts = {
            "nodes": len(self.nodes),
            "evidence": len(self.evidence),
            "claims": len(self.claims),
            "accepted_claims": sum(claim.accepted for claim in self.claims),
            "unresolved": len(self.unresolved),
            "review_queue": sum(
                not claim.accepted and claim.review_status != "REJECTED"
                for claim in self.claims
            ),
        }
        return {
            "status": "PASS" if not errors else "FAIL",
            "schema_version": SCHEMA_VERSION,
            "snapshot_id": self.snapshot_id,
            "bundle_digest": self.bundle_digest,
            "manifest_digest": self.manifest_digest,
            "ontology": dict(self.manifest.get("ontology") or {}),
            "counts": counts,
            "files": {
                name: {"sha256": f"sha256:{digest}"}
                for name, digest in sorted(self.file_hashes.items())
            },
            "checks": {
                "referential_integrity": "PASS" if not errors else "FAIL",
                "accepted_claims_are_evidenced": "PASS"
                if all(claim.evidence_ids for claim in self.claims if claim.accepted)
                else "FAIL",
                "content_hashes": "PASS",
                "portable_paths": "PASS"
                if not any(_is_portability_error(error) for error in errors)
                else "FAIL",
            },
            "warnings": warnings,
            "errors": errors,
        }


def doctor_bundle(path: str | Path) -> dict[str, Any]:
    """Validate a bundle without exposing a traceback to CLI or MCP clients."""

    try:
        return GraphBundle.load(path, verify_hashes=True).doctor()
    except BundleValidationError as exc:
        errors = list(exc.errors)
        result: dict[str, Any] = {
            "status": "FAIL",
            "errors": errors,
            "warnings": [],
        }
        if any(_is_portability_error(error) for error in errors):
            result["checks"] = {"portable_paths": "FAIL"}
        return result
