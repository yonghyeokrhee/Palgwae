"""Check the actual loopback HTTP transport used by MCP gateways."""

import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import anyio
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from palgwae.demo import create_demo_bundle


class HttpMcpTest(unittest.TestCase):
    def test_http_initialization_and_read_only_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "bundle"
            create_demo_bundle(bundle)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            with subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "palgwae",
                    "mcp",
                    "--bundle",
                    str(bundle),
                    "--transport",
                    "http",
                    "--port",
                    str(port),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ) as server:
                try:
                    base = f"http://127.0.0.1:{port}"
                    with httpx.Client(timeout=0.5) as client:
                        deadline = time.monotonic() + 15
                        while True:
                            try:
                                response = client.get(base + "/api/health")
                                response.raise_for_status()
                                self.assertEqual(response.json()["status"], "PASS")
                                break
                            except httpx.HTTPError:
                                if server.poll() is not None or time.monotonic() >= deadline:
                                    self.fail("Loopback MCP server did not become healthy")
                                time.sleep(0.1)

                    async def scenario():
                        async with streamable_http_client(base + "/mcp/") as (reader, writer, _):
                            async with ClientSession(reader, writer) as session:
                                await session.initialize()
                                result = await session.call_tool("graph_health", {})
                                self.assertFalse(result.isError)
                                self.assertEqual(result.structuredContent["status"], "PASS")

                    anyio.run(scenario)
                finally:
                    server.terminate()
                    try:
                        server.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait(timeout=5)
