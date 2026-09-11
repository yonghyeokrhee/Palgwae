"""Exercise an installed wheel from outside the checkout, with no Airflow installed."""

from pathlib import Path
import subprocess
import sys
import tempfile

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from palgwae.bundle import GraphBundle
from palgwae.graph import ContextGraph


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)

    def cli(*args, cwd=None):
        subprocess.run(
            [sys.executable, "-m", "palgwae", *args],
            cwd=cwd or root,
            check=True,
            stdout=subprocess.DEVNULL,
        )

    cli("example")
    cli("init", "--source", "palgwae-example", "--namespace", "urn:example:palgwae:smoke")
    cli("doctor", "--bundle", ".palgwae/bundle")
    bundle = root / ".palgwae/bundle"
    graph = ContextGraph(GraphBundle.load(bundle))
    assert (
        graph.path(
            "urn:example:palgwae:smoke/task/daily_orders/extract",
            "urn:example:palgwae:smoke/task/reporting/report",
        )["status"]
        == "ANSWERED"
    )

    # Exercise the source-only multi-repository workflow from an installed
    # wheel. These repositories are deliberately synthetic and require neither
    # Airflow nor Terraform to be installed.
    fixtures = {
        "pipeline/jobs.tf": 'resource "aws_glue_job" "daily" { name = "daily_load" }\n',
        "airflow/dag.py": '''from airflow import DAG
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
with DAG("daily"):
    load = GlueJobOperator(task_id="load", job_name="daily_load")
''',
        "backend/api.py": '''import boto3
glue = boto3.client("glue")
glue.start_job_run(JobName="daily_load")
''',
    }
    for relative, source in fixtures.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")
    owner = root / "pipeline"
    cli(
        "init",
        "--repo", "pipeline=.",
        "--repo", "airflow=../airflow",
        "--repo", "backend=../backend",
        "--namespace", "urn:example:palgwae:workspace-smoke",
        "--environment", "prd",
        cwd=owner,
    )
    cli("rebuild", cwd=owner)
    bundle = owner / ".palgwae/bundle"
    graph = ContextGraph(GraphBundle.load(bundle))

    def exact(name, node_type):
        matches = [item for item in graph.find(name, node_type=node_type)["matches"] if item["name"] == name]
        assert len(matches) == 1, matches
        return matches[0]["node_id"]

    task = exact("load", "Task")
    job = exact("daily_load", "Job")
    script = exact("api.py", "Script")
    assert graph.path(task, job)["status"] == "ANSWERED"
    assert graph.path(script, job)["status"] == "ANSWERED"

    async def scenario():
        parameters = StdioServerParameters(
            command=sys.executable, args=["-m", "palgwae", "mcp", "--bundle", str(bundle)], cwd=root
        )
        async with stdio_client(parameters) as streams, ClientSession(*streams) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert len(tools.tools) == 7
            assert all(tool.annotations.readOnlyHint for tool in tools.tools)
            for repository in ("pipeline", "airflow", "backend"):
                response = await session.call_tool(
                    "find_entity", {"query": repository, "node_type": "Repository"}
                )
                assert not response.isError
                assert any(item["name"] == repository for item in response.structuredContent["matches"])
            response = await session.call_tool("find_dependency_path", {
                "source_node_id": task, "target_node_id": job, "max_hops": 1
            })
            assert not response.isError
            assert response.structuredContent["status"] == "ANSWERED"

    anyio.run(scenario)
print("Installed wheel: legacy Airflow, multi-repository init/rebuild, resource paths and MCP passed")
