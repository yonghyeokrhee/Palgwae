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

    def cli(*args):
        subprocess.run(
            [sys.executable, "-m", "palgwae", *args],
            cwd=root,
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

    async def scenario():
        parameters = StdioServerParameters(
            command=sys.executable, args=["-m", "palgwae", "mcp", "--bundle", str(bundle)], cwd=root
        )
        async with stdio_client(parameters) as streams, ClientSession(*streams) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert len(tools.tools) == 7
            assert all(tool.annotations.readOnlyHint for tool in tools.tools)
            response = await session.call_tool(
                "get_downstream", {"node_id": "urn:example:palgwae:smoke/task/daily_orders/extract"}
            )
            assert not response.isError
            assert response.structuredContent["status"] == "ANSWERED"

    anyio.run(scenario)
print("Installed wheel: example, Airflow ingestion, cross-DAG traversal and MCP passed")
