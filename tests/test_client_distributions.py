from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ARGS = [
    "mcp",
    "--bundle",
    ".palgwae/bundle",
    "--transport",
    "stdio",
]


class ClientDistributionTest(unittest.TestCase):
    def test_repo_marketplace_exposes_the_codex_plugin(self):
        marketplace = json.loads(
            (ROOT / ".agents" / "plugins" / "marketplace.json").read_text()
        )
        self.assertEqual(marketplace["name"], "palgwae")
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], "palgwae")
        self.assertEqual(entry["source"]["path"], "./plugins/palgwae")
        self.assertEqual(entry["policy"]["installation"], "AVAILABLE")
        self.assertEqual(entry["policy"]["authentication"], "ON_INSTALL")

    def test_codex_plugin_manifest_and_mcp_contract(self):
        plugin = ROOT / "plugins" / "palgwae"
        manifest = json.loads(
            (plugin / ".codex-plugin" / "plugin.json").read_text()
        )
        servers = json.loads((plugin / ".mcp.json").read_text())["mcpServers"]

        self.assertEqual(manifest["name"], "palgwae")
        self.assertEqual(manifest["mcpServers"], "./.mcp.json")
        self.assertEqual(servers["palgwae"]["command"], "palgwae")
        self.assertEqual(servers["palgwae"]["args"], EXPECTED_ARGS)
        self.assertTrue(
            (plugin / "skills" / "trace-pipeline" / "SKILL.md").is_file()
        )

    def test_claude_plugin_uses_the_same_stdio_contract(self):
        plugin = ROOT / "plugins" / "claude" / "palgwae"
        manifest = json.loads(
            (plugin / ".claude-plugin" / "plugin.json").read_text()
        )
        servers = json.loads((plugin / ".mcp.json").read_text())["mcpServers"]

        self.assertEqual(manifest["name"], "palgwae")
        self.assertEqual(servers["palgwae"]["type"], "stdio")
        self.assertEqual(servers["palgwae"]["command"], "palgwae")
        self.assertEqual(servers["palgwae"]["args"], EXPECTED_ARGS)

    def test_opencode_uses_the_same_stdio_contract(self):
        config = json.loads(
            (ROOT / "clients" / "opencode" / "opencode.json").read_text()
        )
        command = config["mcp"]["palgwae"]["command"]

        self.assertEqual(command[0], "palgwae")
        self.assertEqual(command[1:], EXPECTED_ARGS)
        self.assertEqual(config["permission"]["palgwae_*"], "allow")

    def test_root_runtime_has_no_graphify_dependency(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        dependency_section = pyproject.split("dependencies = [", 1)[1].split(
            "]", 1
        )[0]
        self.assertNotIn("graphify", dependency_section.casefold())


if __name__ == "__main__":
    unittest.main()
