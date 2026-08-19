from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import tempfile
import unittest

import yaml

from palgwae.builder import build_bundle
from palgwae.bundle import (
    BundleValidationError,
    GraphBundle,
    doctor_bundle,
)
from palgwae.cli import main as cli_main
from palgwae.evaluation import evaluate_golden
from palgwae.graph import ContextGraph
from palgwae.model import Claim, Evidence, Node, is_pinned_revision


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "examples" / "retail_pipeline" / "context-graph.yaml"
GOLDEN = ROOT / "examples" / "retail_pipeline" / "golden.yaml"


class PortableMvpTest(unittest.TestCase):
    @staticmethod
    def _copy_public_fixture(root: Path) -> Path:
        shutil.copytree(
            ROOT / "examples" / "retail_pipeline",
            root / "examples" / "retail_pipeline",
        )
        shutil.copytree(ROOT / "ontology", root / "ontology")
        return root / "examples" / "retail_pipeline" / "context-graph.yaml"

    def test_build_is_deterministic_and_golden_is_non_empty(self):
        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "first"
            second = Path(temporary) / "second"
            first_bundle = build_bundle(SPEC, first)
            second_bundle = build_bundle(SPEC, second)

            self.assertEqual(first_bundle.bundle_digest, second_bundle.bundle_digest)
            for filename in (
                "nodes.jsonl",
                "claims.jsonl",
                "evidence.jsonl",
                "unresolved.jsonl",
                "manifest.json",
            ):
                self.assertEqual(
                    (first / filename).read_bytes(),
                    (second / filename).read_bytes(),
                )

            evaluation = evaluate_golden(first, GOLDEN)
            self.assertEqual(evaluation["status"], "PASS")
            self.assertGreaterEqual(evaluation["summary"]["total"], 5)

    def test_build_is_portable_across_checkout_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_spec = self._copy_public_fixture(root / "checkout-one")
            second_spec = self._copy_public_fixture(root / "checkout-two")

            first = build_bundle(first_spec, root / "first-bundle")
            second = build_bundle(second_spec, root / "second-bundle")

            self.assertEqual(first.bundle_digest, second.bundle_digest)
            self.assertEqual(first.snapshot_id, second.snapshot_id)
            self.assertEqual(first.manifest_digest, second.manifest_digest)
            self.assertEqual(first.manifest, second.manifest)

            source_spec = first.manifest["build"]["spec"]
            self.assertFalse(PurePosixPath(source_spec).is_absolute())
            self.assertFalse(PureWindowsPath(source_spec).is_absolute())

            serialized = json.dumps(first.manifest)
            forbidden_fragments = (
                "/" + "Users/example/",
                "/" + "home/example/",
                "/" + "private/tmp/",
                "C:" + "\\" + "Users\\example\\",
            )
            for fragment in forbidden_fragments:
                self.assertNotIn(fragment, serialized)

    def test_build_cli_reports_a_portable_source_spec(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundle"
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                status = cli_main(
                    ["build", str(SPEC.resolve()), "--output", str(output)]
                )

            self.assertEqual(status, 0)
            result = json.loads(stdout.getvalue())
            self.assertEqual(result["source_spec"], "context-graph.yaml")
            self.assertFalse(PurePosixPath(result["source_spec"]).is_absolute())
            self.assertFalse(PureWindowsPath(result["source_spec"]).is_absolute())

    def test_doctor_rejects_local_paths_in_manifest_build_metadata(self):
        local_paths = (
            "/" + "Users/example/project/context-graph.yaml",
            "/" + "home/example/project/context-graph.yaml",
            "/" + "private/tmp/project/context-graph.yaml",
            "C:" + "\\" + "Users\\example\\project\\context-graph.yaml",
        )
        for local_path in local_paths:
            with self.subTest(local_path=local_path):
                with tempfile.TemporaryDirectory() as temporary:
                    output = Path(temporary) / "bundle"
                    build_bundle(SPEC, output)
                    manifest_path = output / "manifest.json"
                    manifest = json.loads(
                        manifest_path.read_text(encoding="utf-8")
                    )
                    manifest["build"]["source_spec"] = local_path
                    manifest_path.write_text(
                        json.dumps(manifest), encoding="utf-8"
                    )

                    result = doctor_bundle(output)

                    self.assertEqual(result["status"], "FAIL")
                    self.assertEqual(
                        result["checks"]["portable_paths"], "FAIL"
                    )
                    self.assertTrue(
                        any("must be portable" in item for item in result["errors"])
                    )

    def test_data_flow_contract_and_unknown_boundary_are_retrievable(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = build_bundle(SPEC, Path(temporary) / "bundle")
            graph = ContextGraph(bundle)

            resolved = graph.find("orders_daily")
            self.assertEqual(resolved["status"], "ANSWERED")
            self.assertEqual(
                resolved["matches"][0]["node_id"],
                "urn:example:palgwae:demo:dataset:orders-daily",
            )

            impact = graph.impact(
                "urn:example:palgwae:demo:dataset:orders-daily", max_hops=3
            )
            self.assertEqual(impact["status"], "ANSWERED")
            affected = {item["node_id"] for item in impact["results"]}
            self.assertIn("urn:example:palgwae:demo:service:orders-api", affected)

            publish = graph.downstream(
                "urn:example:palgwae:demo:job:publish-orders", max_hops=2
            )
            self.assertTrue(publish["unresolved_boundaries"])
            self.assertEqual(
                publish["unresolved_boundaries"][0]["target_hint"],
                "notification_target",
            )

            missing = graph.find("notification_target")
            self.assertEqual(missing["status"], "UNKNOWN")
            self.assertIn("unproven", missing["reason"])

            no_path = graph.path(
                "urn:example:palgwae:demo:trigger:daily-orders-schedule",
                "urn:example:palgwae:demo:environment:local",
                max_hops=8,
            )
            self.assertEqual(no_path["status"], "UNKNOWN")
            self.assertTrue(no_path["unresolved_boundaries"])
            self.assertEqual(
                no_path["unresolved_boundaries"][0]["target_hint"],
                "notification_target",
            )

    def test_claim_evidence_is_pinned_and_repository_relative(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = build_bundle(SPEC, Path(temporary) / "bundle")
            graph = ContextGraph(bundle)
            claim = next(item for item in bundle.claims if item.accepted)

            result = graph.claim_evidence(claim.claim_id)

            self.assertEqual(result["status"], "ANSWERED")
            self.assertTrue(result["evidence"])
            for evidence in result["evidence"]:
                self.assertFalse(Path(evidence["path"]).is_absolute())
                self.assertTrue(evidence["content_hash"].startswith("sha256:"))
                self.assertTrue(evidence["revision"])
                self.assertTrue(evidence["locator"])

    def test_candidate_and_inferred_claims_do_not_enter_traversal(self):
        digest = "0" * 64
        evidence = Evidence.create(
            source_type="fixture",
            repository="synthetic",
            revision="fixture-v1",
            path="fixture.txt",
            locator="L1",
            content_hash=digest,
            extractor="test",
        )
        nodes = (
            Node("urn:example:palgwae:test:a", "Job", "a"),
            Node("urn:example:palgwae:test:b", "Job", "b"),
            Node("urn:example:palgwae:test:c", "Job", "c"),
        )
        claims = (
            Claim.create(
                subject=nodes[0].node_id,
                predicate="STARTS",
                object=nodes[1].node_id,
                evidence_ids=[evidence.evidence_id],
                assertion_kind="DECLARED",
                review_status="CANDIDATE",
            ),
            Claim.create(
                subject=nodes[1].node_id,
                predicate="STARTS",
                object=nodes[2].node_id,
                evidence_ids=[evidence.evidence_id],
                assertion_kind="INFERRED",
                review_status="AUTO_VERIFIED",
            ),
        )
        graph = ContextGraph(
            GraphBundle(nodes=nodes, evidence=(evidence,), claims=claims)
        )

        result = graph.downstream(nodes[0].node_id)

        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["paths"], [])

    def test_doctor_fails_closed_after_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundle"
            build_bundle(SPEC, output)
            claims = output / "claims.jsonl"
            claims.write_text(
                claims.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )

            result = doctor_bundle(output)

            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(
                any("hash mismatch" in error for error in result["errors"])
            )

    def test_duplicate_top_level_evidence_id_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "one.txt").write_text("one", encoding="utf-8")
            (root / "two.txt").write_text("two", encoding="utf-8")
            for ontology_name in ("entities.yaml", "relations.yaml"):
                (root / ontology_name).write_text(
                    (ROOT / "ontology" / ontology_name).read_text(
                        encoding="utf-8"
                    ),
                    encoding="utf-8",
                )
            spec = root / "context-graph.yaml"
            spec.write_text(
                """
version: 1
ontology:
  entities: entities.yaml
  relations: relations.yaml
project:
  name: collision-fixture
  namespace: urn:example:palgwae:collision
  revision: collision-v1
entities: []
evidence:
  - id: evidence:duplicate
    path: one.txt
    locator: L1
  - id: evidence:duplicate
    path: two.txt
    locator: L1
claims: []
""".strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                BundleValidationError, "evidence ID collision"
            ):
                build_bundle(spec, root / "bundle")

    def test_moving_revisions_are_not_accepted_as_pinned(self):
        for revision in (
            "main",
            "origin/main",
            "refs/heads/release-1",
            "tip",
            "production",
        ):
            self.assertFalse(is_pinned_revision(revision), revision)
        for revision in (
            "retail-demo-v1",
            "snapshot:0123456789abcdef",
            "abcdef1",
            "sha256:" + "a" * 64,
        ):
            self.assertTrue(is_pinned_revision(revision), revision)

    def test_unknown_golden_expectation_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "bundle"
            build_bundle(SPEC, bundle)
            golden = root / "golden.yaml"
            golden.write_text(
                """
version: 1
questions:
  - id: typo-must-not-pass
    tool: find_entity
    arguments: {query: orders_daily}
    expect: {sttaus: ANSWERED}
""".strip(),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                BundleValidationError, "unsupported expectations"
            ):
                evaluate_golden(bundle, golden)

    def test_ontology_gates_entity_identity_and_predicates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec_path = self._copy_public_fixture(root)
            original = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
            cases = {}

            missing_ontology = deepcopy(original)
            del missing_ontology["ontology"]
            cases["spec.ontology"] = missing_ontology

            unknown_entity = deepcopy(original)
            unknown_entity["entities"][2]["type"] = "MysteryTrigger"
            cases["absent from the entity ontology"] = unknown_entity

            missing_identity = deepcopy(original)
            del missing_identity["entities"][2]["attributes"]["kind"]
            cases["missing identity attributes"] = missing_identity

            unknown_predicate = deepcopy(original)
            unknown_predicate["claims"][0]["predicate"] = "MAYBE_TRIGGERS"
            cases["absent from the relation ontology"] = unknown_predicate

            invalid_locator = deepcopy(original)
            invalid_locator["claims"][0]["evidence"][0]["locator"] = "L999"
            cases["AUTO_VERIFIED claims require valid line locators"] = (
                invalid_locator
            )

            for expected_error, specification in cases.items():
                with self.subTest(expected_error=expected_error):
                    case_path = spec_path.with_name(
                        expected_error.split()[0].replace(".", "-") + ".yaml"
                    )
                    case_path.write_text(
                        yaml.safe_dump(specification, sort_keys=False),
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(
                        BundleValidationError, expected_error
                    ):
                        build_bundle(
                            case_path,
                            root / ("out-" + case_path.stem),
                        )

    def test_manifest_records_every_evidence_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec_path = self._copy_public_fixture(root)
            specification = yaml.safe_load(
                spec_path.read_text(encoding="utf-8")
            )
            evidence = specification["claims"][0]["evidence"][0]
            evidence["repository"] = "shared-orchestration-fixture"
            evidence["revision"] = "shared-fixture-v2"
            spec_path.write_text(
                yaml.safe_dump(specification, sort_keys=False),
                encoding="utf-8",
            )

            bundle = build_bundle(spec_path, root / "bundle")
            sources = {
                (item["name"], item["revision"])
                for item in bundle.manifest["sources"]
            }

            self.assertIn(("retail-pipeline", "retail-demo-v1"), sources)
            self.assertIn(
                ("shared-orchestration-fixture", "shared-fixture-v2"),
                sources,
            )

    def test_text_evidence_hashes_are_stable_across_line_endings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            unix_spec = self._copy_public_fixture(root / "unix")
            windows_spec = self._copy_public_fixture(root / "windows")
            windows_source = windows_spec.parent / "source"
            for path in windows_source.iterdir():
                if path.is_file():
                    text = path.read_text(encoding="utf-8")
                    path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))

            unix_bundle = build_bundle(unix_spec, root / "unix-bundle")
            windows_bundle = build_bundle(
                windows_spec, root / "windows-bundle"
            )

            self.assertEqual(
                unix_bundle.bundle_digest, windows_bundle.bundle_digest
            )

    def test_manifest_shape_fails_closed(self):
        mutations = {
            "missing fields": lambda value: value.pop("snapshot_id"),
            "unsupported fields": lambda value: value.update(
                {"local_path": "/not-portable"}
            ),
        }
        for expected_error, mutate in mutations.items():
            with self.subTest(expected_error=expected_error):
                with tempfile.TemporaryDirectory() as temporary:
                    output = Path(temporary) / "bundle"
                    build_bundle(SPEC, output)
                    manifest_path = output / "manifest.json"
                    manifest = json.loads(
                        manifest_path.read_text(encoding="utf-8")
                    )
                    mutate(manifest)
                    manifest_path.write_text(
                        json.dumps(manifest),
                        encoding="utf-8",
                    )

                    result = doctor_bundle(output)

                    self.assertEqual(result["status"], "FAIL")
                    self.assertTrue(
                        any(
                            expected_error in error
                            for error in result["errors"]
                        )
                    )

    def test_public_files_do_not_contain_private_project_markers(self):
        forbidden = (
            "corp-internal.example",
            "private-repository-name",
            "customer-account-id",
            "example-secret-token",
            str(Path.home()),
            str(Path(tempfile.gettempdir())),
        )
        included_suffixes = {
            ".json",
            ".jsonl",
            ".md",
            ".py",
            ".toml",
            ".yaml",
            ".yml",
            ".html",
            ".css",
            ".js",
        }
        for path in ROOT.rglob("*"):
            if not path.is_file() or path.suffix not in included_suffixes:
                continue
            if path.resolve() == Path(__file__).resolve():
                continue
            if any(part in {".git", ".venv", "__pycache__"} for part in path.parts):
                continue
            text = path.read_text(encoding="utf-8")
            for marker in forbidden:
                self.assertNotIn(marker, text, f"{marker!r} leaked into {path}")

        with tempfile.TemporaryDirectory() as temporary:
            bundle = build_bundle(SPEC, Path(temporary) / "bundle")
            manifest = json.loads(
                (bundle.bundle_dir / "manifest.json").read_text(encoding="utf-8")
            )
            serialized = json.dumps(manifest)
            self.assertNotIn(str(Path.home()), serialized)
            self.assertNotIn(str(Path(tempfile.gettempdir())), serialized)

            health = bundle.doctor()
            self.assertNotIn("bundle_dir", health)


if __name__ == "__main__":
    unittest.main()
