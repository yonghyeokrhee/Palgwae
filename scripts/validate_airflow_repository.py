"""Local-only real repository validation. Output contains aggregate counts, not names."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import tempfile
from time import perf_counter

from palgwae.airflow import build_airflow
from palgwae.bundle import GraphBundle
from palgwae.graph import ContextGraph

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("source", type=Path)
parser.add_argument("--namespace", required=True)
args = parser.parse_args()
with tempfile.TemporaryDirectory() as temporary:
    first, second = (Path(temporary) / name for name in ("first", "second"))
    started = perf_counter()
    report = build_airflow(args.source, first, args.namespace)
    elapsed = perf_counter() - started
    repeated = build_airflow(args.source, second, args.namespace)
    assert repeated["bundle_digest"] == report["bundle_digest"], "Non-deterministic extraction"
    bundle = GraphBundle.load(first)
    graph = ContextGraph(bundle)
    dependencies = 0
    for claim in bundle.claims:
        if claim.predicate == "CONTAINS":
            continue
        upstream, downstream = (
            (claim.object, claim.subject)
            if claim.predicate == "WAITS_FOR"
            else (claim.subject, claim.object)
        )
        assert graph.path(upstream, downstream)["status"] == "ANSWERED"
        dependencies += 1
    for evidence in bundle.evidence:
        data = (args.source / evidence.path).read_bytes().replace(b"\r\n", b"\n")
        assert sha256(data).hexdigest() == evidence.content_hash.removeprefix("sha256:")
        match = re.fullmatch(r"L(\d+)-L(\d+)", evidence.locator)
        assert match and 1 <= int(match[1]) <= int(match[2]) <= len(data.splitlines())
    print(
        json.dumps(
            {
                "status": "PASS",
                "extraction": {
                    k: v for k, v in report["extraction"].items() if k != "source_revision"
                },
                "relations": dict(Counter(c.predicate for c in bundle.claims)),
                "unresolved_reasons": dict(Counter(u.reason for u in bundle.unresolved)),
                "verified_dependency_queries": dependencies,
                "verified_evidence_records": len(bundle.evidence),
                "deterministic_rebuild": True,
                "build_seconds": round(elapsed, 4),
                "caveat": "Static control-flow validation, not scheduler execution or a completeness benchmark.",
            },
            indent=2,
        )
    )
