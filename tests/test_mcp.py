from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from palgwae.builder import build_bundle
from palgwae.mcp_server import _is_loopback


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "examples" / "retail_pipeline" / "context-graph.yaml"


class McpContractTest(unittest.TestCase):
    def test_stdio_initializes_lists_read_only_tools_and_returns_structured_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "bundle"
            build_bundle(SPEC, bundle)

            async def scenario():
                environment = {
                    key: value
                    for key, value in os.environ.items()
                    if not key.endswith("_TOKEN") and not key.endswith("_API_KEY")
                }
                parameters = StdioServerParameters(
                    command=sys.executable,
                    args=[
                        "-m",
                        "palgwae",
                        "mcp",
                        "--bundle",
                        str(bundle),
                        "--transport",
                        "stdio",
                    ],
                    cwd=ROOT,
                    env=environment,
                )
                async with stdio_client(parameters) as (read_stream, write_stream):
                    async with ClientSession(read_stream, write_stream) as session:
                        initialized = await session.initialize()
                        self.assertEqual(
                            initialized.serverInfo.name, "palgwae"
                        )
                        tools = await session.list_tools()
                        health = await session.call_tool("graph_health", {})
                        missing = await session.call_tool(
                            "find_entity", {"query": "notification_target"}
                        )
                        impact = await session.call_tool(
                            "assess_change_impact",
                            {
                                "node_id": "urn:example:palgwae:demo:dataset:orders-daily",
                                "max_hops": 3,
                            },
                        )
                        upstream = await session.call_tool(
                            "get_upstream",
                            {
                                "node_id": (
                                    "urn:example:palgwae:demo:dataset:orders-daily"
                                ),
                                "max_hops": 3,
                            },
                        )
                        downstream = await session.call_tool(
                            "get_downstream",
                            {
                                "node_id": "urn:example:palgwae:demo:dataset:raw-orders",
                                "max_hops": 5,
                            },
                        )
                        dependency_path = await session.call_tool(
                            "find_dependency_path",
                            {
                                "source_node_id": (
                                    "urn:example:palgwae:demo:trigger:"
                                    "daily-orders-schedule"
                                ),
                                "target_node_id": (
                                    "urn:example:palgwae:demo:contract:"
                                    "orders-daily-ready-v1"
                                ),
                                "max_hops": 8,
                            },
                        )
                        claim_id = dependency_path.structuredContent[
                            "paths"
                        ][0]["claim_ids"][0]
                        claim_evidence = await session.call_tool(
                            "get_claim_evidence", {"claim_id": claim_id}
                        )
                        invalid_node = await session.call_tool(
                            "get_downstream",
                            {"node_id": "urn:example:palgwae:demo:missing"},
                        )
                        invalid_hops = await session.call_tool(
                            "get_upstream",
                            {
                                "node_id": (
                                    "urn:example:palgwae:demo:dataset:orders-daily"
                                ),
                                "max_hops": 0,
                            },
                        )

                        expected = {
                            "graph_health",
                            "find_entity",
                            "get_upstream",
                            "get_downstream",
                            "find_dependency_path",
                            "assess_change_impact",
                            "get_claim_evidence",
                        }
                        self.assertEqual(
                            {tool.name for tool in tools.tools}, expected
                        )
                        self.assertFalse(health.isError)
                        self.assertNotIn(
                            "bundle_dir", health.structuredContent
                        )
                        self.assertEqual(
                            health.structuredContent["status"], "PASS"
                        )
                        self.assertEqual(
                            missing.structuredContent["status"], "UNKNOWN"
                        )
                        self.assertEqual(
                            impact.structuredContent["status"], "ANSWERED"
                        )
                        for result in (
                            upstream,
                            downstream,
                            dependency_path,
                            claim_evidence,
                        ):
                            self.assertFalse(result.isError)
                            self.assertEqual(
                                result.structuredContent["status"],
                                "ANSWERED",
                            )
                        self.assertTrue(invalid_node.isError)
                        self.assertTrue(invalid_hops.isError)

            anyio.run(scenario)

    def test_http_binding_is_loopback_only(self):
        self.assertTrue(_is_loopback("127.0.0.1"))
        self.assertTrue(_is_loopback("::1"))
        self.assertTrue(_is_loopback("localhost"))
        self.assertFalse(_is_loopback("0.0.0.0"))
        self.assertFalse(_is_loopback("192.168.1.10"))


if __name__ == "__main__":
    unittest.main()
