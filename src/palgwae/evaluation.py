"""Structured Golden-set evaluation for graph retrieval contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .bundle import BundleValidationError, GraphBundle
from .builder import load_spec
from .graph import ContextGraph


SUPPORTED_GOLDEN_TOOLS = frozenset(
    {
        "find_entity",
        "get_upstream",
        "get_downstream",
        "find_dependency_path",
        "assess_change_impact",
    }
)
SUPPORTED_EXPECTATIONS = frozenset({"status", "contains_node_id"})


def _contains_scalar(value: Any, expected: str) -> bool:
    if value == expected:
        return True
    if isinstance(value, Mapping):
        return any(_contains_scalar(item, expected) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_scalar(item, expected) for item in value)
    return False


def _call(graph: ContextGraph, tool: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    if tool == "find_entity":
        return graph.find(
            str(arguments.get("query", "")),
            node_type=arguments.get("node_type"),
            limit=int(arguments.get("limit", 10)),
        )
    if tool == "get_upstream":
        return graph.upstream(
            str(arguments.get("node_id", "")),
            max_hops=int(arguments.get("max_hops", 6)),
        )
    if tool == "get_downstream":
        return graph.downstream(
            str(arguments.get("node_id", "")),
            max_hops=int(arguments.get("max_hops", 6)),
        )
    if tool == "find_dependency_path":
        return graph.path(
            str(arguments.get("source_node_id", "")),
            str(arguments.get("target_node_id", "")),
            max_hops=int(arguments.get("max_hops", 8)),
        )
    if tool == "assess_change_impact":
        return graph.impact(
            str(arguments.get("node_id", "")),
            change_type=str(arguments.get("change_type", "unspecified")),
            max_hops=int(arguments.get("max_hops", 6)),
        )
    raise ValueError(f"unsupported Golden tool: {tool}")


def evaluate_golden(
    bundle_path: str | Path,
    golden_path: str | Path,
) -> dict[str, Any]:
    """Execute a non-empty Golden set against structured graph results."""

    specification = load_spec(golden_path)
    if specification.get("version") not in (1, "1"):
        raise BundleValidationError("Golden set version must be 1")
    questions = specification.get("questions")
    if not isinstance(questions, list) or not questions:
        raise BundleValidationError("Golden set must contain at least one question")

    graph = ContextGraph(GraphBundle.load(bundle_path))
    cases: list[dict[str, Any]] = []
    case_ids: set[str] = set()
    passed = 0
    for index, question in enumerate(questions, 1):
        if not isinstance(question, Mapping):
            raise BundleValidationError(
                f"Golden question {index} must be an object"
            )
        case_id = str(question.get("id") or f"question-{index}")
        if case_id in case_ids:
            raise BundleValidationError(
                f"Golden question ID is duplicated: {case_id}"
            )
        case_ids.add(case_id)
        tool = str(question.get("tool") or "")
        arguments = question.get("arguments") or {}
        expected = question.get("expect") or {}
        if tool not in SUPPORTED_GOLDEN_TOOLS:
            raise BundleValidationError(
                f"Golden question {case_id} uses unsupported tool {tool!r}"
            )
        if not isinstance(arguments, Mapping) or not isinstance(expected, Mapping):
            raise BundleValidationError(
                f"Golden question {case_id} arguments/expect must be objects"
            )
        unknown_expectations = sorted(set(expected) - SUPPORTED_EXPECTATIONS)
        if unknown_expectations:
            raise BundleValidationError(
                f"Golden question {case_id} has unsupported expectations: "
                + ", ".join(unknown_expectations)
            )
        if "status" not in expected:
            raise BundleValidationError(
                f"Golden question {case_id} must expect a status"
            )
        errors: list[str] = []
        try:
            result = _call(graph, tool, arguments)
            expected_status = expected.get("status")
            if expected_status is not None and result.get("status") != expected_status:
                errors.append(
                    f"expected status {expected_status!r}, "
                    f"got {result.get('status')!r}"
                )
            expected_node = expected.get("contains_node_id")
            if expected_node is not None and not _contains_scalar(
                result, str(expected_node)
            ):
                errors.append(
                    f"result does not contain node ID {expected_node!r}"
                )
        except (KeyError, ValueError) as exc:
            result = {"status": "ERROR", "error": str(exc)}
            errors.append(str(exc))
        case_passed = not errors
        if case_passed:
            passed += 1
        cases.append(
            {
                "id": case_id,
                "tool": tool,
                "status": "PASS" if case_passed else "FAIL",
                "errors": errors,
                "actual_status": result.get("status"),
            }
        )

    total = len(cases)
    return {
        "status": "PASS" if passed == total else "FAIL",
        "snapshot_id": graph.bundle.snapshot_id,
        "golden_file": str(Path(golden_path).expanduser().resolve()),
        "summary": {"passed": passed, "failed": total - passed, "total": total},
        "cases": cases,
    }
