import contextlib
import io
import json
from pathlib import Path
import types
import unittest
from unittest.mock import Mock, patch

from palgwae.cli import main


class WorkspaceCliTest(unittest.TestCase):
    def setUp(self):
        self.workspace = types.ModuleType("palgwae.workspace")
        self.workspace.initialize_workspace = Mock(return_value=Path(".palgwae/workspace.yaml"))
        self.workspace.build_workspace = Mock(return_value={
            "status": "PASS", "counts": {"repositories": 2},
            "mcp_config": {"mcpServers": {"palgwae": {"command": "palgwae"}}},
        })
        self.module_patch = patch.dict("sys.modules", {"palgwae.workspace": self.workspace})
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)

    def invoke(self, arguments, *, interactive=False, responses=()):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), \
                patch("palgwae.cli.sys.stdin.isatty", return_value=interactive), \
                patch("builtins.input", side_effect=responses) as prompt:
            code = main(arguments)
        return code, stdout.getvalue(), stderr.getvalue(), prompt.call_count

    def test_repeated_repository_flags_build_one_workspace(self):
        code, output, errors, prompts = self.invoke([
            "init", "--repo", "pipeline=.", "--repo", "airflow",
            "--namespace", "urn:example:platform", "--environment", "prd",
        ])
        self.assertEqual(code, 0, errors)
        self.assertEqual(prompts, 0)
        self.workspace.initialize_workspace.assert_called_once_with(
            Path.cwd(), ["pipeline=.", "airflow"], "urn:example:platform", "prd"
        )
        self.workspace.build_workspace.assert_called_once_with(Path(".palgwae/workspace.yaml"), None)
        self.assertIn("mcp_config", json.loads(output))

    def test_interactive_names_and_namespace(self):
        code, output, errors, prompts = self.invoke(
            ["init"], interactive=True,
            responses=[" airflow=../airflow, backend , ./etl ", "urn:example:team"],
        )
        self.assertEqual(code, 0, errors)
        self.assertEqual(prompts, 2)
        self.assertIn("Related project names", errors)
        self.assertIn("Graph namespace", errors)
        self.assertEqual(json.loads(output)["status"], "PASS")
        self.workspace.initialize_workspace.assert_called_once_with(
            Path.cwd(), ["airflow=../airflow", "backend", "./etl"], "urn:example:team", None
        )

    def test_interactive_default_is_current_project(self):
        code, _, errors, prompts = self.invoke(
            ["init", "--namespace", "urn:example:team"], interactive=True, responses=[""]
        )
        self.assertEqual(code, 0, errors)
        self.assertEqual(prompts, 1)
        self.assertEqual(self.workspace.initialize_workspace.call_args.args[1], ["."])

    def test_explicit_repositories_do_not_prompt_again(self):
        code, _, errors, prompts = self.invoke(
            ["init", "--repo", "backend", "--namespace", "urn:example:team"], interactive=True
        )
        self.assertEqual(code, 0, errors)
        self.assertEqual(prompts, 0)

    def test_bare_noninteractive_init_has_actionable_error(self):
        code, output, errors, prompts = self.invoke(["init"])
        self.assertEqual(code, 2)
        self.assertEqual(output, "")
        self.assertEqual(prompts, 0)
        self.assertIn("--namespace", errors)
        self.assertIn("--repo", errors)
        self.workspace.initialize_workspace.assert_not_called()

    def test_noninteractive_namespace_alone_selects_current_project(self):
        code, _, errors, _ = self.invoke(["init", "--namespace", "urn:example:team"])
        self.assertEqual(code, 0, errors)
        self.assertEqual(self.workspace.initialize_workspace.call_args.args[1], ["."])

    def test_existing_workspace_builds_without_initializing_or_prompting(self):
        code, _, errors, prompts = self.invoke(
            ["init", "--workspace", "projects.yaml", "--output", "graph"], interactive=True
        )
        self.assertEqual(code, 0, errors)
        self.assertEqual(prompts, 0)
        self.workspace.initialize_workspace.assert_not_called()
        self.workspace.build_workspace.assert_called_once_with(Path("projects.yaml"), Path("graph"))

    def test_workspace_rejects_conflicting_initialization_flags(self):
        for extra in (["--repo", "backend"], ["--namespace", "urn:example:team"], ["--environment", "prd"]):
            with self.subTest(extra=extra):
                code, _, errors, _ = self.invoke(["init", "--workspace", "projects.yaml", *extra])
                self.assertEqual(code, 2)
                self.assertIn("cannot be combined", errors)
        self.workspace.build_workspace.assert_not_called()
        self.workspace.initialize_workspace.assert_not_called()

    def test_legacy_source_rejects_workspace_flags(self):
        for extra in (["--repo", "backend"], ["--workspace", "projects.yaml"], ["--environment", "prd"]):
            with self.subTest(extra=extra):
                code, _, errors, _ = self.invoke([
                    "init", "--source", "dags", "--namespace", "urn:example:team", *extra
                ])
                self.assertEqual(code, 2)
                self.assertIn("cannot be combined", errors)
        self.workspace.initialize_workspace.assert_not_called()

    def test_legacy_airflow_init_keeps_output_and_mcp_config(self):
        with patch("palgwae.airflow.build_airflow", return_value={"status": "PASS"}) as build:
            code, output, errors, prompts = self.invoke([
                "init", "--source", "dags", "--namespace", "urn:example:team", "--output", "graph"
            ])
        self.assertEqual(code, 0, errors)
        self.assertEqual(prompts, 0)
        build.assert_called_once_with(Path("dags"), Path("graph"), "urn:example:team")
        report = json.loads(output)
        self.assertEqual(report["mcp_config"]["mcpServers"]["palgwae"]["args"], [
            "mcp", "--bundle", str(Path("graph").resolve()), "--transport", "stdio"
        ])
        self.workspace.initialize_workspace.assert_not_called()

    def test_legacy_airflow_init_retains_default_output(self):
        with patch("palgwae.airflow.build_airflow", return_value={"status": "PASS"}) as build:
            code, _, errors, _ = self.invoke(["init", "--source", "dags", "--namespace", "urn:example:team"])
        self.assertEqual(code, 0, errors)
        build.assert_called_once_with(Path("dags"), Path(".palgwae/bundle"), "urn:example:team")

    def test_legacy_source_still_requires_namespace(self):
        code, _, errors, prompts = self.invoke(["init", "--source", "dags"], interactive=True)
        self.assertEqual(code, 2)
        self.assertEqual(prompts, 0)
        self.assertIn("--namespace", errors)

    def test_rebuild_defaults_and_explicit_paths(self):
        code, _, errors, prompts = self.invoke(["rebuild"])
        self.assertEqual(code, 0, errors)
        self.assertEqual(prompts, 0)
        self.workspace.build_workspace.assert_called_once_with(Path(".palgwae/workspace.yaml"), None)
        self.workspace.build_workspace.reset_mock()
        code, _, errors, _ = self.invoke(["rebuild", "--workspace", "team.yaml", "--output", "graph"])
        self.assertEqual(code, 0, errors)
        self.workspace.build_workspace.assert_called_once_with(Path("team.yaml"), Path("graph"))
        self.workspace.initialize_workspace.assert_not_called()

    def test_build_failure_does_not_repeat_initialization(self):
        self.workspace.build_workspace.side_effect = ValueError("unsupported repository")
        code, _, errors, _ = self.invoke(["init", "--namespace", "urn:example:team"])
        self.assertEqual(code, 2)
        self.assertIn("unsupported repository", errors)
        self.workspace.initialize_workspace.assert_called_once()

    def test_empty_namespace_is_rejected(self):
        code, _, errors, _ = self.invoke(["init"], interactive=True, responses=["backend", "  "])
        self.assertEqual(code, 2)
        self.assertIn("namespace URI is required", errors)
        self.workspace.initialize_workspace.assert_not_called()

    def test_interrupted_prompt_has_actionable_error(self):
        code, _, errors, _ = self.invoke(["init"], interactive=True, responses=EOFError())
        self.assertEqual(code, 2)
        self.assertIn("rerun init with --repo", errors)
        self.workspace.initialize_workspace.assert_not_called()


if __name__ == "__main__":
    unittest.main()
