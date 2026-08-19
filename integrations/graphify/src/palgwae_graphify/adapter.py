from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


LEDGER_SCHEMA = "palgwae.graphify-candidate-ledger/v1"
ADAPTER_VERSION = "1"
PROMOTABLE_RELATIONS = {
    "calls": "INVOKES",
    "contains": "CONTAINS",
    "depends_on": "REQUIRES",
    "imports": "REQUIRES",
    "reads_from": "READS_FROM",
    "writes_to": "WRITES_TO",
}


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + sha256(_canonical_json(value)).hexdigest()


def _file_digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _relative_path(raw: Any) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"invalid source_file: {raw!r}")
    value = raw.replace("\\", "/")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"source_file must be repository-relative: {raw!r}")
    return str(path)


def _records(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"Graphify graph must contain {field}[]")
    if any(not isinstance(record, dict) for record in value):
        raise ValueError(f"Graphify {field} must contain objects")
    return value


def adapt_graph(
    graph: dict[str, Any],
    *,
    repository: str,
    revision: str,
    repo_root: Path,
    graphify_version: str,
) -> dict[str, Any]:
    """Convert Graphify output into non-authoritative Palgwae candidates."""

    if not repository.strip():
        raise ValueError("repository is required")
    if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("revision must be a lowercase 40-character Git SHA")
    repo_root = repo_root.resolve()
    nodes = _records(graph.get("nodes"), "nodes")
    edges = _records(graph.get("edges"), "edges")
    if graph.get("input_tokens", 0) or graph.get("output_tokens", 0):
        raise ValueError("code-only Graphify candidates must not record LLM tokens")

    node_ids: dict[str, str] = {}
    candidate_nodes: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for index, node in enumerate(nodes):
        raw_id = node.get("id")
        if not isinstance(raw_id, str) or not raw_id:
            raise ValueError(f"Graphify node {index}.id is required")
        if raw_id in node_ids:
            raise ValueError(f"duplicate Graphify node ID: {raw_id}")
        candidate_id = "candidate:graphify:" + sha256(
            f"{repository}\0{revision}\0{raw_id}".encode("utf-8")
        ).hexdigest()
        node_ids[raw_id] = candidate_id
        source_file = node.get("source_file")
        relative = _relative_path(source_file) if source_file else None
        resolution_status = "UNRESOLVED" if relative is None else "SOURCE_LOCATED"
        candidate_nodes.append(
            {
                "candidate_id": candidate_id,
                "extractor_id": raw_id,
                "label": str(node.get("label") or raw_id),
                "raw_type": str(node.get("file_type") or "unknown"),
                "source_file": relative,
                "source_locator": node.get("source_location"),
                "resolution_status": resolution_status,
            }
        )
        if relative is None:
            unresolved.append(
                {
                    "candidate_id": candidate_id,
                    "reason": "NO_SOURCE_LOCATION",
                }
            )

    for index, edge in enumerate(edges):
        for field in ("source", "target"):
            raw_id = edge.get(field)
            if not isinstance(raw_id, str) or not raw_id:
                raise ValueError(f"Graphify edge {index}.{field} is required")
            if raw_id in node_ids:
                continue
            candidate_id = "candidate:graphify:" + sha256(
                f"{repository}\0{revision}\0{raw_id}".encode("utf-8")
            ).hexdigest()
            node_ids[raw_id] = candidate_id
            candidate_nodes.append(
                {
                    "candidate_id": candidate_id,
                    "extractor_id": raw_id,
                    "label": raw_id,
                    "raw_type": "unknown",
                    "source_file": None,
                    "source_locator": None,
                    "resolution_status": "UNRESOLVED",
                }
            )
            unresolved.append(
                {
                    "candidate_id": candidate_id,
                    "reason": "DANGLING_EXTRACTOR_ENDPOINT",
                }
            )

    evidence: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    for index, edge in enumerate(edges):
        source = edge.get("source")
        target = edge.get("target")
        raw_relation = str(edge.get("relation") or "unknown").casefold()
        predicate = PROMOTABLE_RELATIONS.get(raw_relation)
        source_file = edge.get("source_file")
        evidence_id = None
        if source_file:
            relative = _relative_path(source_file)
            source_path = (repo_root / relative).resolve()
            try:
                source_path.relative_to(repo_root)
            except ValueError as exc:
                raise ValueError("source_file escapes repository root") from exc
            if not source_path.is_file():
                raise ValueError(f"evidence source does not exist: {relative}")
            evidence_record = {
                "repository": repository,
                "revision": revision,
                "path": relative,
                "locator": str(edge.get("source_location") or "UNKNOWN"),
                "content_hash": _file_digest(source_path),
                "extractor": f"graphify/{graphify_version}",
            }
            evidence_id = "candidate-evidence:" + _digest(evidence_record)[7:]
            evidence_record["evidence_id"] = evidence_id
            evidence.append(evidence_record)
        claim_record = {
            "subject_candidate_id": node_ids[source],
            "object_candidate_id": node_ids[target],
            "raw_relation": raw_relation,
            "proposed_predicate": predicate,
            "review_status": "CANDIDATE",
            "assertion_kind": str(edge.get("confidence") or "UNKNOWN").upper(),
            "evidence_ids": [evidence_id] if evidence_id else [],
            "promotion_eligible": bool(predicate and evidence_id),
        }
        claim_record["candidate_claim_id"] = (
            "candidate-claim:" + _digest(claim_record)[7:]
        )
        claims.append(claim_record)

    evidence_by_id = {item["evidence_id"]: item for item in evidence}
    result = {
        "schema_version": LEDGER_SCHEMA,
        "adapter_version": ADAPTER_VERSION,
        "extractor": "graphify",
        "extractor_version": graphify_version,
        "repository": repository,
        "revision": revision,
        "nodes": sorted(candidate_nodes, key=lambda item: item["candidate_id"]),
        "claims": sorted(claims, key=lambda item: item["candidate_claim_id"]),
        "evidence": sorted(evidence_by_id.values(), key=lambda item: item["evidence_id"]),
        "unresolved": sorted(unresolved, key=lambda item: item["candidate_id"]),
    }
    result["candidate_digest"] = _digest(
        {key: result[key] for key in ("nodes", "claims", "evidence", "unresolved")}
    )
    return result


def _write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> str:
    content = b"".join(_canonical_json(record) + b"\n" for record in records)
    path.write_bytes(content)
    return "sha256:" + sha256(content).hexdigest()


def write_candidate_ledger(ledger: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"candidate output is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "candidate-nodes.jsonl": _write_jsonl(
            output_dir / "candidate-nodes.jsonl", ledger["nodes"]
        ),
        "candidate-claims.jsonl": _write_jsonl(
            output_dir / "candidate-claims.jsonl", ledger["claims"]
        ),
        "candidate-evidence.jsonl": _write_jsonl(
            output_dir / "candidate-evidence.jsonl", ledger["evidence"]
        ),
        "unresolved.jsonl": _write_jsonl(
            output_dir / "unresolved.jsonl", ledger["unresolved"]
        ),
    }
    manifest = {
        key: ledger[key]
        for key in (
            "schema_version",
            "adapter_version",
            "extractor",
            "extractor_version",
            "repository",
            "revision",
            "candidate_digest",
        )
    }
    manifest["counts"] = {
        key: len(ledger[key]) for key in ("nodes", "claims", "evidence", "unresolved")
    }
    manifest["accepted_claim_count"] = 0
    manifest["files"] = files
    (output_dir / "manifest.json").write_bytes(_canonical_json(manifest) + b"\n")
    return manifest
