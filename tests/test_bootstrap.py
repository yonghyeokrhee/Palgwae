from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import tempfile
import unittest

from palgwae.bootstrap import bootstrap_project, discover_project_spec
from palgwae.bundle import BundleValidationError, GraphBundle


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "examples" / "retail_pipeline" / "context-graph.yaml"


class ProjectBootstrapTest(unittest.TestCase):
    def test_missing_spec_creates_fail_closed_starter(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "random-etl"
            project.mkdir()
            (project / "job.py").write_text("print('etl')\n", encoding="utf-8")
            output = project / ".palgwae" / "bundle"

            result = bootstrap_project(project, output)
            bundle = GraphBundle.load(output)

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["bootstrap_mode"], "starter")
        self.assertEqual(result["counts"]["nodes"], 1)
        self.assertEqual(result["counts"]["accepted_claims"], 0)
        self.assertEqual(result["counts"]["unresolved"], 1)
        self.assertEqual(bundle.nodes[0].name, "random-etl")
        self.assertIn("No Palgwae context spec", bundle.unresolved[0].reason)

    def test_conventional_spec_is_discovered_and_built(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "owner"
            project.mkdir()
            fixture = SPEC.parent
            for path in fixture.rglob("*"):
                if path.is_file():
                    destination = project / path.relative_to(fixture)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(path.read_bytes())
            ontology = ROOT / "ontology"
            target_ontology = project.parent / "ontology"
            target_ontology.mkdir()
            for path in ontology.iterdir():
                if path.is_file():
                    (target_ontology / path.name).write_bytes(path.read_bytes())
            conventional = project / "palgwae-context-graph.yaml"
            original = project / "context-graph.yaml"
            conventional.write_text(
                original.read_text(encoding="utf-8").replace(
                    "../../ontology/", "../ontology/"
                ),
                encoding="utf-8",
            )
            original.unlink()

            result = bootstrap_project(project, ".palgwae/bundle")

        self.assertEqual(result["bootstrap_mode"], "spec")
        self.assertEqual(result["status"], "PASS")
        self.assertGreater(result["counts"]["accepted_claims"], 0)

    def test_existing_bundle_is_validated_without_rebuild(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "owner"
            project.mkdir()
            first = bootstrap_project(project, ".palgwae/bundle")
            second = bootstrap_project(project, ".palgwae/bundle")

        self.assertEqual(second["bootstrap_mode"], "existing")
        self.assertEqual(first["bundle_digest"], second["bundle_digest"])

    def test_concurrent_first_start_serializes_to_one_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "owner"
            project.mkdir()

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(
                    executor.map(
                        lambda _: bootstrap_project(
                            project, ".palgwae/bundle"
                        ),
                        range(2),
                    )
                )

        self.assertEqual(
            {result["bootstrap_mode"] for result in results},
            {"starter", "existing"},
        )
        self.assertEqual(
            len({result["bundle_digest"] for result in results}), 1
        )

    def test_partial_bundle_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "owner"
            bundle = project / ".palgwae" / "bundle"
            bundle.mkdir(parents=True)
            (bundle / "notes.txt").write_text("preserve me", encoding="utf-8")

            with self.assertRaisesRegex(
                BundleValidationError, "refusing to replace partial"
            ):
                bootstrap_project(project, bundle)

    def test_git_revision_is_pinned_to_head(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "owner"
            project.mkdir()
            subprocess.run(["git", "init", "-q", str(project)], check=True)
            subprocess.run(
                ["git", "-C", str(project), "config", "user.email", "test@example.com"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(project), "config", "user.name", "Test"],
                check=True,
            )
            (project / "job.py").write_text("pass\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(project), "add", "job.py"], check=True)
            subprocess.run(
                ["git", "-C", str(project), "commit", "-qm", "fixture"],
                check=True,
            )
            head = subprocess.run(
                ["git", "-C", str(project), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            bootstrap_project(project, ".palgwae/bundle")
            manifest = json.loads(
                (project / ".palgwae" / "bundle" / "manifest.json").read_text()
            )

        self.assertEqual(manifest["sources"], [{"name": "owner", "revision": head}])

    def test_discovery_order_prefers_repository_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            nested = project / ".palgwae" / "context-graph.yaml"
            nested.parent.mkdir()
            nested.write_text("nested\n", encoding="utf-8")
            root = project / "palgwae-context-graph.yaml"
            root.write_text("root\n", encoding="utf-8")

            found = discover_project_spec(project)

        self.assertEqual(found, root.resolve())


if __name__ == "__main__":
    unittest.main()
