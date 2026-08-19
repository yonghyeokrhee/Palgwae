from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from palgwae.builder import build_bundle


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "examples" / "retail_pipeline" / "context-graph.yaml"


def _client_commands() -> dict[str, tuple[str, list[str]]]:
    codex = json.loads(
        (ROOT / "plugins" / "palgwae" / ".mcp.json").read_text()
    )["mcpServers"]["palgwae"]
    claude = json.loads(
        (ROOT / "plugins" / "claude" / "palgwae" / ".mcp.json").read_text()
    )["mcpServers"]["palgwae"]
    opencode = json.loads(
        (ROOT / "clients" / "opencode" / "opencode.json").read_text()
    )["mcp"]["palgwae"]["command"]
    return {
        "codex": (codex["command"], codex["args"]),
        "claude": (claude["command"], claude["args"]),
        "opencode": (opencode[0], opencode[1:]),
    }


class CrossAgentMcpTest(unittest.TestCase):
    def test_all_client_distributions_return_identical_structured_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "bundle"
            build_bundle(SPEC, bundle)

            async def call_client(command: str, configured_args: list[str]):
                args = [str(bundle) if item == ".palgwae/bundle" else item for item in configured_args]
                parameters = StdioServerParameters(
                    command=command,
                    args=args,
                    cwd=ROOT,
                    env=dict(os.environ),
                )
                async with stdio_client(parameters) as streams:
                    async with ClientSession(*streams) as session:
                        initialized = await session.initialize()
                        tools = await session.list_tools()
                        health = await session.call_tool("graph_health", {})
                        found = await session.call_tool(
                            "find_entity", {"query": "orders_daily"}
                        )
                        return {
                            "server": initialized.serverInfo.name,
                            "tools": sorted(tool.name for tool in tools.tools),
                            "health": health.structuredContent,
                            "found": found.structuredContent,
                        }

            async def scenario():
                results = []
                for command, args in _client_commands().values():
                    results.append(await call_client(command, args))
                return results

            results = anyio.run(scenario)

        self.assertEqual(results[0], results[1])
        self.assertEqual(results[1], results[2])
        self.assertEqual(results[0]["server"], "palgwae")
        self.assertEqual(results[0]["health"]["status"], "PASS")
        self.assertEqual(results[0]["found"]["status"], "ANSWERED")


if __name__ == "__main__":
    unittest.main()
