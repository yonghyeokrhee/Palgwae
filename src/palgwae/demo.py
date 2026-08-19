"""Generate a tiny vendor-neutral graph that demonstrates the methodology."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from .bundle import BundleValidationError, GraphBundle
from .model import Claim, Evidence, Node, Unresolved


DEMO_SOURCE = """\
def extract_orders(api_client, raw_writer):
    records = api_client.fetch("/orders")
    raw_writer.write("orders_raw", records)


def transform_orders(raw_reader, curated_writer):
    rows = raw_reader.read("orders_raw")
    curated_writer.write("orders_curated", normalize(rows))


def publish_revenue(dashboard, curated_reader):
    dashboard.refresh(curated_reader.read("orders_curated"))
"""

DEMO_ENTITY_ONTOLOGY = {
    "Job": ["environment", "name"],
    "PhysicalDataset": ["environment", "platform", "namespace", "name"],
    "Service": ["repository", "name"],
}
DEMO_RELATION_ONTOLOGY = {
    "READS_FROM": {
        "dependency_direction": "object_to_subject",
        "include_in_lineage": True,
    },
    "TRIGGERS": {
        "dependency_direction": "subject_to_object",
        "include_in_lineage": True,
    },
    "WRITES_TO": {
        "dependency_direction": "subject_to_object",
        "include_in_lineage": True,
    },
}


def _ontology_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return f"sha256:{sha256(encoded.encode('utf-8')).hexdigest()}"


def create_demo_bundle(output: str | Path) -> GraphBundle:
    output_path = Path(output).expanduser().resolve()
    if (output_path / "manifest.json").exists():
        raise BundleValidationError(
            f"refusing to overwrite existing bundle: {output_path}"
        )
    source_dir = output_path / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    source_path = source_dir / "pipeline.py"
    if source_path.exists() and source_path.read_text(encoding="utf-8") != DEMO_SOURCE:
        raise BundleValidationError(
            f"refusing to overwrite existing source: {source_path}"
        )
    source_path.write_text(DEMO_SOURCE, encoding="utf-8", newline="\n")
    digest = sha256(DEMO_SOURCE.encode("utf-8")).hexdigest()
    revision = "demo-revision-0001"

    nodes = (
        Node(
            "urn:example:palgwae:demo:service:orders-api",
            "Service",
            "Orders API",
            attributes={"repository": "example-retail-pipeline"},
        ),
        Node(
            "urn:example:palgwae:demo:job:extract-orders",
            "Job",
            "Extract orders",
            attributes={"environment": "example"},
        ),
        Node(
            "urn:example:palgwae:demo:dataset:orders-raw",
            "PhysicalDataset",
            "Raw orders",
            attributes={
                "environment": "example",
                "platform": "object-store",
                "namespace": "retail",
            },
        ),
        Node(
            "urn:example:palgwae:demo:job:transform-orders",
            "Job",
            "Transform orders",
            attributes={"environment": "example"},
        ),
        Node(
            "urn:example:palgwae:demo:dataset:orders-curated",
            "PhysicalDataset",
            "Curated orders",
            aliases=("orders_gold",),
            attributes={
                "environment": "example",
                "platform": "warehouse",
                "namespace": "retail",
            },
        ),
        Node(
            "urn:example:palgwae:demo:service:revenue-dashboard",
            "Service",
            "Revenue dashboard",
            attributes={"repository": "example-retail-pipeline"},
        ),
    )

    def evidence(locator: str) -> Evidence:
        return Evidence.create(
            source_type="code",
            repository="example-retail-pipeline",
            revision=revision,
            path="sources/pipeline.py",
            locator=locator,
            content_hash=digest,
            extractor="palgwae demo",
            attributes={"locator_verified": True},
        )

    evidence_records = (
        evidence("extract_orders:2"),
        evidence("extract_orders:3"),
        evidence("transform_orders:7"),
        evidence("transform_orders:8"),
        evidence("publish_revenue:12"),
    )
    evidence_by_locator = {item.locator: item for item in evidence_records}

    def claim(
        subject: str,
        predicate: str,
        object_: str,
        locator: str,
    ) -> Claim:
        relation = DEMO_RELATION_ONTOLOGY[predicate]
        return Claim.create(
            subject=subject,
            predicate=predicate,
            object=object_,
            assertion_kind="DECLARED",
            review_status="AUTO_VERIFIED",
            evidence_ids=(evidence_by_locator[locator].evidence_id,),
            confidence=1.0,
            scope={"revision": revision, "environment": "example"},
            attributes={
                "lineage_orientation": relation["dependency_direction"],
                "include_in_lineage": relation["include_in_lineage"],
                "relation_category": "demo",
            },
        )

    claims = (
        claim(
            "urn:example:palgwae:demo:service:orders-api",
            "TRIGGERS",
            "urn:example:palgwae:demo:job:extract-orders",
            "extract_orders:2",
        ),
        claim(
            "urn:example:palgwae:demo:job:extract-orders",
            "WRITES_TO",
            "urn:example:palgwae:demo:dataset:orders-raw",
            "extract_orders:3",
        ),
        # READS_FROM is grammatically job -> dataset, but dependency flow is
        # oriented dataset -> job by the graph relation registry.
        claim(
            "urn:example:palgwae:demo:job:transform-orders",
            "READS_FROM",
            "urn:example:palgwae:demo:dataset:orders-raw",
            "transform_orders:7",
        ),
        claim(
            "urn:example:palgwae:demo:job:transform-orders",
            "WRITES_TO",
            "urn:example:palgwae:demo:dataset:orders-curated",
            "transform_orders:8",
        ),
        claim(
            "urn:example:palgwae:demo:service:revenue-dashboard",
            "READS_FROM",
            "urn:example:palgwae:demo:dataset:orders-curated",
            "publish_revenue:12",
        ),
    )
    unresolved = (
        Unresolved.create(
            source_node_id="urn:example:palgwae:demo:job:transform-orders",
            target_hint="alert_sink",
            reason="The alert target is supplied dynamically at deployment time.",
            evidence_ids=(
                evidence_by_locator["transform_orders:8"].evidence_id,
            ),
        ),
    )
    bundle = GraphBundle(
        nodes=nodes,
        evidence=evidence_records,
        claims=claims,
        unresolved=unresolved,
    )
    bundle.write(
        output_path,
        snapshot_id="demo-retail-pipeline-v1",
        metadata={
            "project": "example-retail-pipeline",
            "source_revision": revision,
            "purpose": "public methodology demo",
            "ontology": {
                "name": "palgwae-demo",
                "version": "1",
                "entities_sha256": _ontology_hash(DEMO_ENTITY_ONTOLOGY),
                "relations_sha256": _ontology_hash(DEMO_RELATION_ONTOLOGY),
            },
        },
    )
    return GraphBundle.load(output_path)
