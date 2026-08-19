"""Palgwae: evidence-bounded context graphs for data-engineering projects."""

from .builder import build_bundle, compile_spec, load_spec
from .bundle import (
    BundleValidationError,
    GraphBundle,
    doctor_bundle,
    sha256_file,
)
from .graph import (
    ANSWERED,
    CONFIRMED,
    UNKNOWN,
    ContextGraph,
    EvidenceGraph,
    PathStep,
    lineage_orientation,
)
from .evaluation import SUPPORTED_GOLDEN_TOOLS, evaluate_golden
from .model import (
    ACCEPTED_REVIEW_STATUSES,
    ASSERTION_KINDS,
    REVIEW_STATUSES,
    Claim,
    Evidence,
    ModelValidationError,
    Node,
    Unresolved,
    stable_id,
)

__all__ = [
    "ACCEPTED_REVIEW_STATUSES",
    "ASSERTION_KINDS",
    "REVIEW_STATUSES",
    "SUPPORTED_GOLDEN_TOOLS",
    "BundleValidationError",
    "ANSWERED",
    "Claim",
    "CONFIRMED",
    "ContextGraph",
    "Evidence",
    "EvidenceGraph",
    "GraphBundle",
    "ModelValidationError",
    "Node",
    "PathStep",
    "UNKNOWN",
    "Unresolved",
    "build_bundle",
    "compile_spec",
    "doctor_bundle",
    "evaluate_golden",
    "lineage_orientation",
    "load_spec",
    "sha256_file",
    "stable_id",
]

__version__ = "0.1.0"
