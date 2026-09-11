from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
import yaml

from palgwae.bundle import BundleValidationError, GraphBundle
from palgwae.demo import create_demo_bundle
from palgwae.graph import ContextGraph
from palgwae.workspace import build_workspace, initialize_workspace


ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = "https://example.org/team/data-platform"
TERRAFORM = '''resource "aws_glue_job" "daily" {
  name = "daily_load"
}
'''
AIRFLOW = '''from airflow import DAG
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator

with DAG("warehouse_daily"):
    load = GlueJobOperator(task_id="load", job_name="daily_load")
'''
BACKEND = '''import boto3

glue = boto3.client("glue")
glue.start_job_run(JobName="daily_load")
'''
UPSTREAM = '''from airflow import DAG
from airflow.operators.empty import EmptyOperator

with DAG("producer_daily"):
    publish = EmptyOperator(task_id="publish")
'''
DOWNSTREAM = '''from airflow import DAG
from airflow.sensors.external_task import ExternalTaskSensor
from airflow.operators.empty import EmptyOperator

with DAG("consumer_daily"):
    wait = ExternalTaskSensor(task_id="wait_for_publish", external_dag_id="producer_daily", external_task_id="publish")
    consume = EmptyOperator(task_id="consume")
    wait >> consume
'''


class WorkspaceIntegrationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def sources(self, root=None):
        root = root or self.root
        for project, filename, source in (
            ("etl", "jobs.tf", TERRAFORM),
            ("airflow", "pipeline.py", AIRFLOW),
            ("backend", "api.py", BACKEND),
        ):
            directory = root / project
            directory.mkdir(parents=True)
            (directory / filename).write_text(source, encoding="utf-8")
        return root / "etl"

    def initialize(self, owner=None):
        owner = owner or self.sources()
        return initialize_workspace(
            owner, [".", "airflow", "backend=../backend"], NAMESPACE, environment="prd"
        )

    def graph(self, config):
        report = build_workspace(config)
        bundle = GraphBundle.load(config.parent / "bundle")
        self.assertEqual(report["status"], "PASS")
        return report, bundle, ContextGraph(bundle)

    def exact(self, graph, name, node_type):
        response = graph.find(name, node_type=node_type)
        matches = [node for node in response["matches"] if node["name"] == name]
        self.assertEqual(len(matches), 1, response)
        return matches[0]["node_id"]

    def test_init_registers_local_names_and_portable_relative_paths(self):
        owner = self.sources()
        config = self.initialize(owner)
        self.assertEqual(config, owner.resolve() / ".palgwae" / "workspace.yaml")
        value = yaml.safe_load(config.read_text())
        self.assertEqual(value["environment"], "prd")
        self.assertEqual(value["namespace"], NAMESPACE)
        self.assertEqual({entry["name"]: entry["path"] for entry in value["projects"]}, {
            "etl": ".", "airflow": "../airflow", "backend": "../backend"
        })
        self.assertNotIn(str(self.root), config.read_text())
        original = config.read_bytes()
        with self.assertRaises(BundleValidationError):
            self.initialize(owner)
        self.assertEqual(config.read_bytes(), original)

    def test_three_repositories_produce_evidenced_resource_paths_in_one_bundle(self):
        config = self.initialize()
        report, bundle, graph = self.graph(config)
        job = self.exact(graph, "daily_load", "Job")
        task = self.exact(graph, "load", "Task")
        backend = self.exact(graph, "api.py", "Script")
        self.assertTrue(job.startswith(NAMESPACE + "/repo/etl/"))
        self.assertTrue(task.startswith(NAMESPACE + "/repo/airflow/"))
        self.assertTrue(backend.startswith(NAMESPACE + "/repo/backend/"))
        evidence = {item.evidence_id: item for item in bundle.evidence}
        for source, predicate, repositories in (
            (task, "STARTS", {"airflow", "etl"}),
            (backend, "INVOKES", {"backend", "etl"}),
        ):
            path = graph.path(source, job)
            self.assertEqual(path["status"], "ANSWERED", path)
            claims = [c for c in bundle.claims if c.subject == source and c.object == job]
            self.assertEqual([c.predicate for c in claims], [predicate])
            cited = [evidence[item] for item in claims[0].evidence_ids]
            self.assertEqual({item.repository.rsplit("/", 1)[-1] for item in cited}, repositories)
            self.assertTrue(all(item.locator.startswith("L") and item.content_hash for item in cited))
        self.assertEqual({item["project"] for item in report["coverage"]}, {"etl", "airflow", "backend"})
        self.assertEqual(set(report["mcp_config"]["mcpServers"]), {"palgwae"})
        self.assertIn(str((config.parent / "bundle").resolve()), report["mcp_config"]["mcpServers"]["palgwae"]["args"])

    def test_external_sensor_resolves_an_explicit_cross_repository_target(self):
        producer = self.root / "producer"
        consumer = self.root / "consumer"
        producer.mkdir()
        consumer.mkdir()
        (producer / "dag.py").write_text(UPSTREAM)
        (consumer / "dag.py").write_text(DOWNSTREAM)
        config = initialize_workspace(consumer, [".", "producer"], NAMESPACE)
        _, bundle, graph = self.graph(config)
        publish = self.exact(graph, "publish", "Task")
        wait = self.exact(graph, "wait_for_publish", "Task")
        consume = self.exact(graph, "consume", "Task")
        claims = [c for c in bundle.claims if c.subject == wait and c.object == publish]
        self.assertEqual([c.predicate for c in claims], ["WAITS_FOR"])
        self.assertEqual(graph.path(publish, consume)["status"], "ANSWERED")
        cited = {e.repository for e in bundle.evidence if e.evidence_id in claims[0].evidence_ids}
        self.assertEqual(cited, {NAMESPACE + "/repo/consumer", NAMESPACE + "/repo/producer"})

    def test_duplicate_resource_target_is_unresolved_without_guessed_edges(self):
        owner = self.sources()
        duplicate = self.root / "other-etl"
        duplicate.mkdir()
        (duplicate / "jobs.tf").write_text(TERRAFORM)
        config = initialize_workspace(
            owner, [".", "airflow", "backend", "other-etl"], NAMESPACE, environment="prd"
        )
        _, bundle, graph = self.graph(config)
        job_ids = {n.node_id for n in bundle.nodes if n.node_type == "Job" and n.name == "daily_load"}
        self.assertEqual(len(job_ids), 2)
        task = self.exact(graph, "load", "Task")
        backend = self.exact(graph, "api.py", "Script")
        self.assertFalse(any(c.subject in {task, backend} and c.object in job_ids for c in bundle.claims))
        gaps = [u for u in bundle.unresolved if u.source_node_id in {task, backend} and u.target_hint == "daily_load"]
        self.assertEqual({u.source_node_id for u in gaps}, {task, backend})
        self.assertTrue(all("ambiguous" in u.reason for u in gaps))

    def test_duplicate_external_sensor_target_is_unresolved(self):
        for project in ("producer-a", "producer-b", "consumer"):
            directory = self.root / project
            directory.mkdir()
            (directory / "dag.py").write_text(DOWNSTREAM if project == "consumer" else UPSTREAM)
        config = initialize_workspace(
            self.root / "consumer", [".", "producer-a", "producer-b"], NAMESPACE
        )
        _, bundle, graph = self.graph(config)
        wait = self.exact(graph, "wait_for_publish", "Task")
        self.assertFalse(any(c.subject == wait and c.predicate == "WAITS_FOR" for c in bundle.claims))
        self.assertTrue(any(u.source_node_id == wait and "ambiguous" in u.reason for u in bundle.unresolved))

    def test_unchanged_rebuild_and_relocated_checkouts_keep_the_same_bundle(self):
        config_a = self.initialize(self.sources(self.root / "checkout-one"))
        config_b = self.initialize(self.sources(self.root / "checkout-two"))
        _, first, _ = self.graph(config_a)
        _, rebuilt, _ = self.graph(config_a)
        _, relocated, _ = self.graph(config_b)
        for actual in (rebuilt, relocated):
            self.assertEqual(actual.bundle_digest, first.bundle_digest)
            self.assertEqual(actual.manifest_digest, first.manifest_digest)
            self.assertEqual(actual.snapshot_id, first.snapshot_id)
        manifest = json.dumps(first.manifest)
        self.assertNotIn(str(self.root), manifest)

    def test_missing_repository_preserves_previous_published_bundle(self):
        config = self.initialize()
        _, first, _ = self.graph(config)
        bundle_path = config.parent / "bundle"
        original = {p.name: p.read_bytes() for p in bundle_path.iterdir() if p.is_file()}
        (self.root / "backend").rename(self.root / "backend-unavailable")
        with self.assertRaises(BundleValidationError):
            build_workspace(config)
        self.assertEqual({p.name: p.read_bytes() for p in bundle_path.iterdir() if p.is_file()}, original)
        self.assertEqual(GraphBundle.load(bundle_path).bundle_digest, first.bundle_digest)

    def test_custom_output_inside_non_git_source_does_not_become_next_input(self):
        owner = self.sources()
        config = self.initialize(owner)
        output = owner / "generated-graph"
        first = build_workspace(config, output)
        rebuilt = build_workspace(config, output)
        self.assertEqual(first["bundle_digest"], rebuilt["bundle_digest"])
        self.assertEqual(first["coverage"], rebuilt["coverage"])

    def test_unrelated_bundle_is_not_overwritten(self):
        config = self.initialize()
        output = self.root / "unrelated"
        existing = create_demo_bundle(output)
        original = {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
        with self.assertRaisesRegex(BundleValidationError, "refusing to replace"):
            build_workspace(config, output)
        self.assertEqual({p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}, original)
        self.assertEqual(GraphBundle.load(output).bundle_digest, existing.bundle_digest)

    def test_unsupported_backend_records_coverage_instead_of_inventing_dependencies(self):
        backend = self.root / "backend"
        backend.mkdir()
        (backend / "Service.java").write_text('class Service { void start() { glue.startJobRun("daily_load"); } }')
        config = initialize_workspace(backend, ["."], NAMESPACE)
        report, bundle, _ = self.graph(config)
        self.assertEqual(report["coverage"][0]["unsupported_extensions"], [".java"])
        self.assertNotEqual(report["coverage"][0]["status"], "COMPLETE")
        self.assertTrue(bundle.unresolved)
        self.assertFalse(bundle.claims)
        self.assertFalse(any(n.name == "daily_load" for n in bundle.nodes))

    def test_single_stdio_mcp_serves_every_registered_repository_and_path(self):
        config = self.initialize()
        _, bundle, graph = self.graph(config)
        task = self.exact(graph, "load", "Task")
        job = self.exact(graph, "daily_load", "Job")

        async def scenario():
            env = {key: value for key, value in os.environ.items()
                   if not key.endswith("_TOKEN") and not key.endswith("_API_KEY")}
            env["PYTHONPATH"] = str(ROOT / "src")
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-m", "palgwae", "mcp", "--bundle", str(config.parent / "bundle")],
                cwd=ROOT,
                env=env,
            )
            async with stdio_client(parameters) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    for name in ("etl", "airflow", "backend"):
                        response = await session.call_tool("find_entity", {"query": name, "node_type": "Repository"})
                        self.assertFalse(response.isError)
                        self.assertTrue(any(n["name"] == name for n in response.structuredContent["matches"]))
                        self.assertEqual(response.structuredContent["snapshot_id"], bundle.snapshot_id)
                    response = await session.call_tool("find_dependency_path", {
                        "source_node_id": task, "target_node_id": job
                    })
                    self.assertFalse(response.isError)
                    self.assertEqual(response.structuredContent["status"], "ANSWERED")
                    self.assertEqual(response.structuredContent["snapshot_id"], bundle.snapshot_id)

        anyio.run(scenario)


if __name__ == "__main__":
    unittest.main()
