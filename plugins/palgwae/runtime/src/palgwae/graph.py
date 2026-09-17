"""Evidence-bounded graph retrieval for data-engineering dependencies."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Iterable

from .bundle import GraphBundle
from .model import Claim, Node


ANSWERED = "ANSWERED"
# Backward-compatible semantic alias.  Public structured output uses ANSWERED
# to distinguish "the snapshot can answer this" from a stronger truth claim.
CONFIRMED = ANSWERED
UNKNOWN = "UNKNOWN"
UNKNOWN_EXPLANATION = (
    "No accepted, evidence-backed relationship was found. UNKNOWN means "
    "unproven in this snapshot, not proof that no relationship exists."
)

# These predicates describe a consumer as their grammatical subject.  Lineage
# therefore runs from object to subject.  All other relations default to the
# written subject -> object direction.  A claim may override this through
# attributes.lineage_orientation.
OBJECT_TO_SUBJECT_RELATIONS = frozenset(
    {
        "READS_FROM",
        "CONSUMES",
        "DEPENDS_ON",
        "REQUIRES",
        "GATED_BY",
        "SUBSCRIBES_TO",
        "QUERIES",
    }
)


def lineage_orientation(claim: Claim) -> tuple[str, str]:
    """Return ``(upstream, downstream)`` for a relation claim."""

    override = str(claim.attributes.get("lineage_orientation", "")).lower()
    if override in {"object_to_subject", "reverse"}:
        return claim.object, claim.subject
    if override in {"subject_to_object", "forward"}:
        return claim.subject, claim.object
    if claim.predicate in OBJECT_TO_SUBJECT_RELATIONS:
        return claim.object, claim.subject
    return claim.subject, claim.object


@dataclass(frozen=True, slots=True)
class PathStep:
    """One accepted claim as traversed in dependency-flow order."""

    claim_id: str
    from_node: str
    to_node: str
    subject: str
    predicate: str
    object: str
    evidence_ids: tuple[str, ...]
    confidence: float
    assertion_kind: str
    review_status: str

    @classmethod
    def from_claim(
        cls, claim: Claim, *, from_node: str, to_node: str
    ) -> "PathStep":
        return cls(
            claim_id=claim.claim_id,
            from_node=from_node,
            to_node=to_node,
            subject=claim.subject,
            predicate=claim.predicate,
            object=claim.object,
            evidence_ids=claim.evidence_ids,
            confidence=claim.confidence,
            assertion_kind=claim.assertion_kind,
            review_status=claim.review_status,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "from_node": self.from_node,
            "to_node": self.to_node,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "evidence_ids": list(self.evidence_ids),
            "confidence": self.confidence,
            "assertion_kind": self.assertion_kind,
            "review_status": self.review_status,
        }


def _path_dict(steps: Iterable[PathStep], start: str) -> dict[str, Any]:
    values = list(steps)
    node_ids = [start, *(step.to_node for step in values)]
    evidence_ids = sorted(
        {evidence_id for step in values for evidence_id in step.evidence_ids}
    )
    return {
        "hops": len(values),
        "node_ids": node_ids,
        "claim_ids": [step.claim_id for step in values],
        "evidence_ids": evidence_ids,
        "steps": [step.to_dict() for step in values],
    }


class ContextGraph:
    """Read-only query facade over a validated :class:`GraphBundle`."""

    def __init__(self, bundle: GraphBundle) -> None:
        self.bundle = bundle
        self.nodes = bundle.node_index
        self.evidence = bundle.evidence_index
        self.claims = bundle.claim_index
        self._downstream: dict[str, list[tuple[Claim, str]]] = defaultdict(list)
        self._upstream: dict[str, list[tuple[Claim, str]]] = defaultdict(list)
        for claim in bundle.claims:
            if not claim.accepted or claim.attributes.get("include_in_lineage") is False:
                continue
            upstream, downstream = lineage_orientation(claim)
            self._downstream[upstream].append((claim, downstream))
            self._upstream[downstream].append((claim, upstream))
        for adjacency in (self._downstream, self._upstream):
            for node_id in adjacency:
                adjacency[node_id].sort(
                    key=lambda pair: (
                        pair[0].predicate,
                        pair[1],
                        pair[0].claim_id,
                    )
                )

    @classmethod
    def load(cls, path: str, *, verify_hashes: bool = True) -> "ContextGraph":
        return cls(GraphBundle.load(path, verify_hashes=verify_hashes))

    def health(self) -> dict[str, Any]:
        return self.bundle.doctor()

    def find(
        self,
        query: str,
        *,
        node_type: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Resolve a human name or alias before performing graph traversal."""

        query_text = query.strip()
        if not query_text:
            raise ValueError("query must not be empty")
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        lowered = query_text.casefold()
        query_tokens = set(lowered.replace(":", " ").replace("/", " ").split())
        requested_type = node_type.casefold() if node_type else None
        scored: list[tuple[float, Node]] = []

        for node in self.bundle.nodes:
            if requested_type and node.node_type.casefold() != requested_type:
                continue
            fields = (node.node_id, node.name, *node.aliases)
            folded = [field.casefold() for field in fields]
            if lowered in folded:
                score = 100.0
            elif any(field.startswith(lowered) for field in folded):
                score = 85.0
            elif any(lowered in field for field in folded):
                score = 70.0
            else:
                searchable = " ".join((*fields, node.node_type)).casefold()
                field_tokens = set(
                    searchable.replace(":", " ").replace("/", " ").split()
                )
                overlap = len(query_tokens & field_tokens)
                fuzzy = max(
                    SequenceMatcher(None, lowered, field).ratio() for field in folded
                )
                if overlap:
                    score = 45.0 + min(overlap, 4) * 5.0
                elif fuzzy >= 0.58:
                    score = fuzzy * 60.0
                else:
                    continue
            scored.append((score, node))

        scored.sort(
            key=lambda pair: (-pair[0], pair[1].node_type, pair[1].name, pair[1].node_id)
        )
        matches = [
            {"score": round(score, 3), **node.to_dict()}
            for score, node in scored[:limit]
        ]
        return {
            "status": CONFIRMED if matches else UNKNOWN,
            "query": query_text,
            "node_type": node_type,
            "matches": matches,
            "reason": None if matches else UNKNOWN_EXPLANATION,
            "snapshot_id": self.bundle.snapshot_id,
        }

    # Compatibility alias for MCP-oriented callers.
    find_entity = find

    def _require_node(self, node_id: str) -> Node:
        try:
            return self.nodes[node_id]
        except KeyError as exc:
            raise KeyError(
                f"unknown canonical node_id {node_id!r}; call find first"
            ) from exc

    @staticmethod
    def _validate_hops(max_hops: int) -> None:
        if not 1 <= max_hops <= 20:
            raise ValueError("max_hops must be between 1 and 20")

    def _reachable_paths(
        self,
        start: str,
        *,
        direction: str,
        max_hops: int,
        max_paths: int = 500,
    ) -> list[list[PathStep]]:
        self._validate_hops(max_hops)
        self._require_node(start)
        adjacency = (
            self._downstream if direction == "downstream" else self._upstream
        )
        queue: deque[tuple[str, tuple[PathStep, ...], frozenset[str]]] = deque(
            [(start, (), frozenset({start}))]
        )
        found: list[list[PathStep]] = []
        # Retain only the shortest proven path to each resource.  This makes
        # impact output stable and prevents combinatorial growth in cyclic
        # orchestration graphs.
        best_depth: dict[str, int] = {}
        while queue and len(found) < max_paths:
            current, path, seen = queue.popleft()
            if len(path) >= max_hops:
                continue
            for claim, next_node in adjacency.get(current, ()):
                if next_node in seen:
                    continue
                next_depth = len(path) + 1
                if next_node in best_depth and best_depth[next_node] <= next_depth:
                    continue
                best_depth[next_node] = next_depth
                step = PathStep.from_claim(
                    claim, from_node=current, to_node=next_node
                )
                next_path = (*path, step)
                found.append(list(next_path))
                queue.append((next_node, next_path, seen | {next_node}))
        return found

    def _traversal(
        self, node_id: str, *, direction: str, max_hops: int
    ) -> dict[str, Any]:
        origin = self._require_node(node_id)
        paths = self._reachable_paths(
            node_id, direction=direction, max_hops=max_hops
        )
        path_values = [_path_dict(path, node_id) for path in paths]
        affected = []
        for path, value in zip(paths, path_values):
            terminal_id = path[-1].to_node
            affected.append(
                {
                    **self.nodes[terminal_id].to_dict(),
                    "hops": len(path),
                    "via_claim_id": path[-1].claim_id,
                }
            )
        visited_ids = {node_id, *(node["node_id"] for node in affected)}
        unresolved = [
            item.to_dict()
            for item in self.bundle.unresolved
            if item.source_node_id in visited_ids
        ]
        return {
            "status": CONFIRMED if paths else UNKNOWN,
            "direction": direction,
            "origin": origin.to_dict(),
            "max_hops": max_hops,
            "results": affected,
            "paths": path_values,
            "unresolved_boundaries": unresolved,
            "reason": None if paths else UNKNOWN_EXPLANATION,
            "snapshot_id": self.bundle.snapshot_id,
        }

    def upstream(self, node_id: str, *, max_hops: int = 6) -> dict[str, Any]:
        return self._traversal(
            node_id, direction="upstream", max_hops=max_hops
        )

    get_upstream = upstream

    def downstream(self, node_id: str, *, max_hops: int = 6) -> dict[str, Any]:
        return self._traversal(
            node_id, direction="downstream", max_hops=max_hops
        )

    get_downstream = downstream

    def path(
        self,
        source_node_id: str,
        target_node_id: str,
        *,
        max_hops: int = 8,
        max_paths: int = 10,
    ) -> dict[str, Any]:
        """Find shortest accepted dependency paths in either direction of flow."""

        self._validate_hops(max_hops)
        source = self._require_node(source_node_id)
        target = self._require_node(target_node_id)
        if source_node_id == target_node_id:
            return {
                "status": CONFIRMED,
                "source": source.to_dict(),
                "target": target.to_dict(),
                "paths": [
                    {
                        "hops": 0,
                        "node_ids": [source_node_id],
                        "claim_ids": [],
                        "evidence_ids": [],
                        "steps": [],
                    }
                ],
                "reason": None,
                "unresolved_boundaries": [
                    item.to_dict()
                    for item in self.bundle.unresolved
                    if item.source_node_id == source_node_id
                ],
                "snapshot_id": self.bundle.snapshot_id,
            }

        queue: deque[tuple[str, tuple[PathStep, ...], frozenset[str]]] = deque(
            [(source_node_id, (), frozenset({source_node_id}))]
        )
        explored_node_ids = {source_node_id}
        found: list[list[PathStep]] = []
        shortest: int | None = None
        while queue and len(found) < max_paths:
            current, path, seen = queue.popleft()
            if len(path) >= max_hops or (
                shortest is not None and len(path) >= shortest
            ):
                continue
            for claim, next_node in self._downstream.get(current, ()):
                if next_node in seen:
                    continue
                explored_node_ids.add(next_node)
                step = PathStep.from_claim(
                    claim, from_node=current, to_node=next_node
                )
                next_path = (*path, step)
                if next_node == target_node_id:
                    shortest = len(next_path)
                    found.append(list(next_path))
                    continue
                queue.append((next_node, next_path, seen | {next_node}))

        unresolved = [
            item.to_dict()
            for item in self.bundle.unresolved
            if item.source_node_id in explored_node_ids
        ]
        return {
            "status": CONFIRMED if found else UNKNOWN,
            "source": source.to_dict(),
            "target": target.to_dict(),
            "max_hops": max_hops,
            "paths": [_path_dict(path, source_node_id) for path in found],
            "unresolved_boundaries": unresolved,
            "reason": None if found else UNKNOWN_EXPLANATION,
            "snapshot_id": self.bundle.snapshot_id,
        }

    find_dependency_path = path

    def impact(
        self,
        node_id: str,
        *,
        change_type: str = "unspecified",
        max_hops: int = 6,
    ) -> dict[str, Any]:
        """Summarize the evidence-backed downstream blast radius of a change."""

        result = self.downstream(node_id, max_hops=max_hops)
        type_counts = Counter(
            node["node_type"] for node in result["results"]
        )
        direct = sum(node["hops"] == 1 for node in result["results"])
        result.update(
            {
                "change_type": change_type,
                "impact_summary": {
                    "direct": direct,
                    "transitive": len(result["results"]) - direct,
                    "total": len(result["results"]),
                    "by_node_type": dict(sorted(type_counts.items())),
                },
                "interpretation": (
                    "Only accepted claims in this snapshot are included. "
                    "Review code, deployment configuration, and runtime evidence "
                    "for unresolved boundaries before making a production change."
                ),
            }
        )
        return result

    assess_change_impact = impact

    def claim_evidence(self, claim_id: str) -> dict[str, Any]:
        claim = self.claims.get(claim_id)
        if claim is None:
            return {
                "status": UNKNOWN,
                "claim_id": claim_id,
                "evidence": [],
                "reason": UNKNOWN_EXPLANATION,
                "snapshot_id": self.bundle.snapshot_id,
            }
        values = [
            self.evidence[evidence_id].to_dict()
            for evidence_id in claim.evidence_ids
            if evidence_id in self.evidence
        ]
        return {
            "status": CONFIRMED if values else UNKNOWN,
            "claim": claim.to_dict(),
            "evidence": values,
            "reason": None if values else UNKNOWN_EXPLANATION,
            "snapshot_id": self.bundle.snapshot_id,
        }

    get_claim_evidence = claim_evidence


# A discoverable name for users coming from graph libraries.
EvidenceGraph = ContextGraph
