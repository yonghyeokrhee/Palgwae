from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from palgwae_graphify.runner import _environment, run_graphify


class GraphifyRunnerTest(unittest.TestCase):
    def test_subprocess_environment_is_allowlist_not_secret_denylist(self):
        supplied = {
            "PATH": "/usr/bin",
            "LANG": "C.UTF-8",
            "API_BEARER_TOKEN": "do-not-forward",
            "AWS_BEARER_TOKEN_BEDROCK": "do-not-forward",
            "SSH_AUTH_SOCK": "/private/socket",
            "UNRECOGNIZED_FUTURE_SECRET": "do-not-forward",
        }
        with patch.dict(os.environ, supplied, clear=True):
            environment = _environment()

        self.assertEqual(environment["PATH"], "/usr/bin")
        self.assertEqual(environment["LANG"], "C.UTF-8")
        for forbidden in (
            "API_BEARER_TOKEN",
            "AWS_BEARER_TOKEN_BEDROCK",
            "SSH_AUTH_SOCK",
            "UNRECOGNIZED_FUTURE_SECRET",
        ):
            self.assertNotIn(forbidden, environment)

    def test_output_inside_source_repository_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "outside the source"):
                run_graphify(
                    repo_root=root,
                    repository="fixture",
                    revision="1" * 40,
                    output_dir=root / "graphify-output",
                )


if __name__ == "__main__":
    unittest.main()
