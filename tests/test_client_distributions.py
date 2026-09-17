from __future__ import annotations

import importlib.util
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
CODEX_ARGS = [
    "run",
    "--no-project",
    "--script",
    "./bin/palgwae-mcp.py",
    "mcp",
    "--bundle",
    ".palgwae/bundle",
    "--bootstrap",
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
        self.assertEqual(
            servers["palgwae"]["command"], "uv"
        )
        self.assertEqual(servers["palgwae"]["args"], CODEX_ARGS)
        self.assertEqual(servers["palgwae"]["cwd"], ".")
        self.assertEqual(servers["palgwae"]["startup_timeout_sec"], 120)
        self.assertTrue((plugin / "bin" / "palgwae-mcp.py").is_file())
        self.assertTrue((plugin / "bin" / "resolve-owner-root.py").is_file())
        self.assertTrue((plugin / "runtime" / "pyproject.toml").is_file())
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

    def test_bundled_codex_runtime_matches_the_canonical_python_source(self):
        canonical = ROOT / "src" / "palgwae"
        bundled = ROOT / "plugins" / "palgwae" / "runtime" / "src" / "palgwae"
        canonical_files = sorted(path.relative_to(canonical) for path in canonical.rglob("*.py"))
        bundled_files = sorted(path.relative_to(bundled) for path in bundled.rglob("*.py"))

        self.assertEqual(bundled_files, canonical_files)
        for name in canonical_files:
            self.assertEqual(
                (bundled / name).read_bytes(),
                (canonical / name).read_bytes(),
                f"bundled runtime is stale: {name}",
            )

    def test_owner_resolver_accepts_codex_cd_forms_only_for_directories(self):
        resolver_path = (
            ROOT / "plugins" / "palgwae" / "bin" / "resolve-owner-root.py"
        )
        module_spec = importlib.util.spec_from_file_location(
            "palgwae_owner_resolver", resolver_path
        )
        self.assertIsNotNone(module_spec)
        self.assertIsNotNone(module_spec.loader)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)

        self.assertEqual(
            module._directory_argument(["codex", "-C", str(ROOT)]), ROOT
        )
        self.assertEqual(
            module._directory_argument(["codex", f"--cd={ROOT}"]), ROOT
        )
        self.assertIsNone(
            module._directory_argument(["codex", "--cd", str(ROOT / "missing")])
        )


if __name__ == "__main__":
    unittest.main()
