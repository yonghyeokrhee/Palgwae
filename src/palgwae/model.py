"""Core, dependency-free data model for an evidence-bounded context graph.

The graph deliberately separates *observations* (``Evidence``) from statements
derived from them (``Claim``).  Only accepted, non-inferred claims participate
in dependency traversal.  Candidate and rejected claims remain available for
review without silently becoming runtime truth.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
import re
from typing import Any, Iterable, Mapping


ASSERTION_KINDS = frozenset(
    {
        "DECLARED",
        "OBSERVED",
        "INFERRED",
        "HUMAN_APPROVED",
    }
)
REVIEW_STATUSES = frozenset(
    {
        "AUTO_VERIFIED",
        "CANDIDATE",
        "HUMAN_APPROVED",
        "REJECTED",
    }
)
ACCEPTED_REVIEW_STATUSES = frozenset(
    {"AUTO_VERIFIED", "HUMAN_APPROVED"}
)

_HEX_SHA256 = re.compile(r"^(?:sha256:)?[0-9a-fA-F]{64}$")
_MUTABLE_REVISIONS = frozenset(
    {
        "current",
        "develop",
        "dev",
        "head",
        "latest",
        "main",
        "master",
        "prd",
        "prod",
        "production",
        "stage",
        "stg",
        "tip",
        "trunk",
        "working-tree",
    }
)
_HEX_REVISION = re.compile(r"^[0-9a-fA-F]{7,64}$")


class ModelValidationError(ValueError):
    """Raised when a graph record violates the public bundle contract."""


def stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    """Create a deterministic, human-prefixable ID from a JSON payload."""

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return f"{prefix}:{sha256(encoded.encode('utf-8')).hexdigest()[:24]}"


def _required_text(value: Any, field_name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ModelValidationError(f"{field_name} is required")
    return text


def _canonical_id(value: Any, field_name: str) -> str:
    text = _required_text(value, field_name)
    if any(character.isspace() for character in text):
        raise ModelValidationError(f"{field_name} must not contain whitespace: {text!r}")
    return text


def _tuple_of_text(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Iterable):
        raise ModelValidationError("expected a string or iterable of strings")
    return tuple(str(item).strip() for item in value if str(item).strip())


def is_pinned_revision(revision: str) -> bool:
    """Return whether a source revision is sufficiently immutable.

    Git SHAs, content digests, version tags, release IDs, and immutable object
    versions are accepted.  Obvious moving branch names are rejected.  This is
    intentionally technology-neutral: a context graph may cite Terraform,
    SQL, a catalog export, or a runtime observation rather than only Git.
    """

    value = revision.strip()
    lowered = value.lower()
    if not value or lowered in _MUTABLE_REVISIONS:
        return False
    if lowered.startswith(("refs/heads/", "origin/", "remotes/")):
        return False
    if _HEX_REVISION.fullmatch(value) or _HEX_SHA256.fullmatch(value):
        return True
    # Version tags, immutable object versions, snapshot IDs, and release IDs
    # normally contain a numeric component. Rejecting bare words keeps moving
    # aliases such as "candidate" or "stable" out of accepted evidence.
    return any(character.isdigit() for character in value)


@dataclass(frozen=True, slots=True)
class Node:
    """An addressable resource, service, script, dataset, or contract."""

    node_id: str
    node_type: str
    name: str
    aliases: tuple[str, ...] = ()
    attributes: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Node":
        node = cls(
            node_id=_canonical_id(
                value.get("node_id", value.get("id")), "node_id"
            ),
            node_type=_required_text(
                value.get("node_type", value.get("type", value.get("kind"))),
                "node_type",
            ),
            name=_required_text(value.get("name"), "name"),
            aliases=_tuple_of_text(value.get("aliases")),
            attributes=dict(value.get("attributes") or {}),
        )
        node.validate()
        return node

    def validate(self) -> None:
        _canonical_id(self.node_id, "node_id")
        _required_text(self.node_type, "node_type")
        _required_text(self.name, "name")
        if self.node_id in self.aliases:
            raise ModelValidationError("a node ID must not also be one of its aliases")
        if len(set(self.aliases)) != len(self.aliases):
            raise ModelValidationError("node aliases must be unique")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        value = asdict(self)
        value["aliases"] = list(self.aliases)
        return value


@dataclass(frozen=True, slots=True)
class Evidence:
    """A pinned source locator supporting one or more graph claims."""

    evidence_id: str
    source_type: str
    repository: str
    revision: str
    path: str
    locator: str
    content_hash: str
    extractor: str = "manual"
    observed_at: str | None = None
    environment: str | None = None
    artifact_uri: str | None = None
    excerpt: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def source_name(self) -> str:
        """Public-schema name for the repository or observation source."""

        return self.repository

    @classmethod
    def create(cls, **kwargs: Any) -> "Evidence":
        payload = {
            key: kwargs.get(key)
            for key in ("repository", "revision", "path", "locator", "content_hash")
        }
        kwargs["evidence_id"] = kwargs.get("evidence_id") or stable_id(
            "evidence", payload
        )
        evidence = cls(**kwargs)
        evidence.validate()
        return evidence

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Evidence":
        attributes = dict(value.get("attributes") or {})
        kwargs: dict[str, Any] = {
            "source_type": _required_text(
                value.get("source_type", value.get("type", "source")),
                "source_type",
            ),
            "repository": _required_text(
                value.get(
                    "repository",
                    value.get("source_name", value.get("source", "local")),
                ),
                "repository",
            ),
            "revision": _required_text(value.get("revision"), "revision"),
            "path": _required_text(value.get("path"), "path"),
            "locator": _required_text(
                value.get("locator", value.get("line", value.get("symbol"))),
                "locator",
            ),
            "content_hash": _required_text(
                value.get("content_hash", value.get("sha256")), "content_hash"
            ),
            "extractor": str(value.get("extractor") or "manual"),
            "observed_at": value.get(
                "observed_at",
                value.get("extracted_at", attributes.get("observed_at")),
            ),
            "environment": value.get("environment"),
            "artifact_uri": value.get(
                "artifact_uri", attributes.get("artifact_uri")
            ),
            "excerpt": value.get("excerpt", attributes.get("excerpt")),
            "attributes": attributes,
        }
        evidence_id = value.get("evidence_id", value.get("id"))
        if evidence_id:
            kwargs["evidence_id"] = _canonical_id(evidence_id, "evidence_id")
        return cls.create(**kwargs)

    def validate(self) -> None:
        _canonical_id(self.evidence_id, "evidence_id")
        _required_text(self.source_type, "source_type")
        _required_text(self.repository, "repository")
        if not is_pinned_revision(self.revision):
            raise ModelValidationError(
                f"evidence revision must be immutable, not {self.revision!r}"
            )
        _required_text(self.path, "path")
        _required_text(self.locator, "locator")
        if not _HEX_SHA256.fullmatch(self.content_hash):
            raise ModelValidationError(
                "content_hash must be a 64-character SHA-256, optionally "
                "prefixed with 'sha256:'"
            )

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        # Keep the on-disk record deliberately small and schema-stable.  Less
        # common provenance fields can travel in attributes without changing
        # the public JSONL contract.
        attributes = dict(self.attributes)
        for key, value in (
            ("observed_at", self.observed_at),
            ("artifact_uri", self.artifact_uri),
            ("excerpt", self.excerpt),
        ):
            if value is not None:
                attributes.setdefault(key, value)
        normalized_hash = self.content_hash.lower()
        return {
            "evidence_id": self.evidence_id,
            "source_type": self.source_type,
            "source_name": self.repository,
            "revision": self.revision,
            "path": self.path,
            "locator": self.locator,
            "content_hash": (
                normalized_hash
                if normalized_hash.startswith("sha256:")
                else f"sha256:{normalized_hash}"
            ),
            "extractor": self.extractor,
            "environment": self.environment,
            "attributes": attributes,
        }


@dataclass(frozen=True, slots=True)
class Claim:
    """A directed statement connecting two canonical nodes.

    ``subject`` and ``object`` retain the natural language relation syntax.
    Dependency traversal may reverse a relation such as ``READS_FROM``; see
    :func:`palgwae.graph.lineage_orientation`.
    """

    claim_id: str
    subject: str
    predicate: str
    object: str
    evidence_ids: tuple[str, ...]
    assertion_kind: str = "DECLARED"
    review_status: str = "CANDIDATE"
    confidence: float = 1.0
    scope: dict[str, Any] = field(default_factory=dict)
    valid_from: str | None = None
    valid_to: str | None = None
    observed_at: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, **kwargs: Any) -> "Claim":
        evidence_ids = _tuple_of_text(kwargs.pop("evidence_ids", ()))
        payload = {
            key: kwargs.get(key)
            for key in (
                "subject",
                "predicate",
                "object",
                "assertion_kind",
                "scope",
                "valid_from",
                "valid_to",
            )
        }
        kwargs["claim_id"] = kwargs.get("claim_id") or stable_id("claim", payload)
        claim = cls(evidence_ids=evidence_ids, **kwargs)
        claim.validate()
        return claim

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Claim":
        attributes = dict(value.get("attributes") or {})
        status = str(
            value.get("review_status", value.get("status", "CANDIDATE"))
        ).upper()
        kwargs: dict[str, Any] = {
            "subject": _canonical_id(
                value.get(
                    "subject", value.get("source", value.get("source_node_id"))
                ),
                "subject",
            ),
            "predicate": _required_text(
                value.get("predicate", value.get("relation")), "predicate"
            ).upper(),
            "object": _canonical_id(
                value.get(
                    "object", value.get("target", value.get("target_node_id"))
                ),
                "object",
            ),
            "evidence_ids": value.get(
                "evidence_ids", value.get("evidence", ())
            ),
            "assertion_kind": str(
                value.get("assertion_kind", "DECLARED")
            ).upper(),
            "review_status": status,
            "confidence": float(
                value.get("confidence", attributes.get("confidence", 1.0))
            ),
            "scope": dict(value.get("scope") or {}),
            "valid_from": value.get("valid_from"),
            "valid_to": value.get("valid_to"),
            "observed_at": value.get(
                "observed_at", attributes.get("observed_at")
            ),
            "attributes": attributes,
        }
        claim_id = value.get("claim_id", value.get("id"))
        if claim_id:
            kwargs["claim_id"] = _canonical_id(claim_id, "claim_id")
        return cls.create(**kwargs)

    @property
    def accepted(self) -> bool:
        """Whether this claim may participate in dependency traversal."""

        return (
            self.review_status in ACCEPTED_REVIEW_STATUSES
            and self.assertion_kind != "INFERRED"
        )

    def validate(self) -> None:
        _canonical_id(self.claim_id, "claim_id")
        _canonical_id(self.subject, "subject")
        _canonical_id(self.object, "object")
        if self.subject == self.object:
            raise ModelValidationError("self-referential claims are not supported")
        _required_text(self.predicate, "predicate")
        if self.assertion_kind not in ASSERTION_KINDS:
            raise ModelValidationError(
                f"unsupported assertion_kind: {self.assertion_kind!r}"
            )
        if self.review_status not in REVIEW_STATUSES:
            raise ModelValidationError(
                f"unsupported review_status: {self.review_status!r}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ModelValidationError("confidence must be between 0 and 1")
        if not self.evidence_ids:
            raise ModelValidationError(
                "claims require at least one evidence_id; use unresolved "
                "for an unproven boundary"
            )
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ModelValidationError("claim evidence_ids must be unique")
        revision = self.scope.get("revision")
        if revision is not None and not is_pinned_revision(str(revision)):
            raise ModelValidationError("claim scope revision must be immutable")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        attributes = dict(self.attributes)
        if self.observed_at is not None:
            attributes.setdefault("observed_at", self.observed_at)
        if self.confidence != 1.0:
            attributes.setdefault("confidence", self.confidence)
        return {
            "claim_id": self.claim_id,
            "subject": self.subject,
            "predicate": self.predicate,
            "object": self.object,
            "assertion_kind": self.assertion_kind,
            "review_status": self.review_status,
            "evidence_ids": list(self.evidence_ids),
            "scope": dict(self.scope),
            "attributes": attributes,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
        }


@dataclass(frozen=True, slots=True)
class Unresolved:
    """An explicit boundary where the snapshot cannot prove a target edge."""

    unresolved_id: str
    source_node_id: str
    reason: str
    evidence_ids: tuple[str, ...] = ()
    target_hint: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, **kwargs: Any) -> "Unresolved":
        evidence_ids = _tuple_of_text(kwargs.pop("evidence_ids", ()))
        payload = {
            key: kwargs.get(key)
            for key in ("source_node_id", "target_hint", "reason")
        }
        kwargs["unresolved_id"] = kwargs.get("unresolved_id") or stable_id(
            "unresolved", payload
        )
        value = cls(evidence_ids=evidence_ids, **kwargs)
        value.validate()
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Unresolved":
        return cls.create(
            unresolved_id=value.get("unresolved_id", value.get("id")),
            source_node_id=_canonical_id(
                value.get("source_node_id", value.get("source")),
                "source_node_id",
            ),
            target_hint=value.get("target_hint"),
            reason=_required_text(value.get("reason"), "reason"),
            evidence_ids=value.get(
                "evidence_ids", value.get("evidence", ())
            ),
            attributes=dict(value.get("attributes") or {}),
        )

    def validate(self) -> None:
        _canonical_id(self.unresolved_id, "unresolved_id")
        _canonical_id(self.source_node_id, "source_node_id")
        _required_text(self.reason, "reason")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ModelValidationError("unresolved evidence_ids must be unique")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "unresolved_id": self.unresolved_id,
            "source_node_id": self.source_node_id,
            "target_hint": self.target_hint,
            "reason": self.reason,
            "evidence_ids": list(self.evidence_ids),
            "attributes": dict(self.attributes),
        }


def read_jsonl(path: str) -> list[dict[str, Any]]:
    """Read non-empty JSON objects from a JSONL file."""

    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ModelValidationError(
                    f"{path}:{line_number}: every JSONL record must be an object"
                )
            records.append(value)
    return records


def write_jsonl(path: str, records: Iterable[Mapping[str, Any]]) -> None:
    """Write deterministic JSONL suitable for hashing and code review."""

    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(
                json.dumps(
                    dict(record),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
