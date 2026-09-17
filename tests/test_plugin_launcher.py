"""Owner-root selection must not depend on a stale shell directory."""

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "palgwae"
spec = importlib.util.spec_from_file_location("palgwae_launcher", PLUGIN / "bin/palgwae-mcp.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class PluginLauncherTest(unittest.TestCase):
    def test_windows_launcher_waits_for_the_runtime_exit(self):
        with (
            patch.object(launcher.sys, "platform", "win32"),
            patch.object(launcher, "owner_root", return_value=ROOT),
            patch.object(launcher.shutil, "which", return_value="uv"),
            patch.object(launcher.subprocess, "run") as run,
            patch.object(launcher.os, "execvpe") as replace,
            patch.object(launcher.os, "chdir") as chdir,
        ):
            run.return_value.returncode = 7
            self.assertEqual(launcher.main(), 7)
            run.assert_called_once()
            self.assertEqual(run.call_args.kwargs["cwd"], ROOT)
            replace.assert_not_called()
            chdir.assert_not_called()

    def test_explicit_owner_overrides_host_cwd(self):
        with tempfile.TemporaryDirectory() as owner:
            with patch.dict(os.environ, {"PALGWAE_PROJECT_ROOT": owner}):
                self.assertEqual(launcher.owner_root(PLUGIN), Path(owner).resolve())

    def test_invalid_explicit_owner_fails_closed(self):
        with tempfile.TemporaryDirectory() as owner:
            with patch.dict(os.environ, {"PALGWAE_PROJECT_ROOT": str(Path(owner) / "missing")}):
                with self.assertRaisesRegex(ValueError, "not a directory"):
                    launcher.owner_root(PLUGIN)

    def test_current_owner_precedes_stale_oldpwd(self):
        with tempfile.TemporaryDirectory() as old:
            with patch.dict(os.environ, {"OLDPWD": old}, clear=True):
                with patch.object(launcher.Path, "cwd", return_value=ROOT):
                    self.assertEqual(launcher.owner_root(PLUGIN), ROOT)

    def test_plugin_cwd_uses_inherited_owner(self):
        with tempfile.TemporaryDirectory() as owner:
            with patch.dict(os.environ, {"OLDPWD": owner}, clear=True):
                with patch.object(launcher.Path, "cwd", return_value=PLUGIN):
                    self.assertEqual(launcher.owner_root(PLUGIN), Path(owner).resolve())
