from contextlib import redirect_stderr, redirect_stdout
import io
import json
import unittest
from unittest.mock import patch

from safety_games.__main__ import main
from safety_games.sandbox import SandboxUnavailable


class CLITests(unittest.TestCase):
    def test_check_config_needs_no_model_or_docker(self):
        output = io.StringIO()
        with redirect_stdout(output), patch("safety_games.__main__.DockerSandbox") as sandbox:
            self.assertEqual(main(["check-config"]), 0)
        sandbox.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["mode"], "baseline")

    def test_missing_config_is_a_clear_nonzero_exit(self):
        output = io.StringIO()
        with redirect_stderr(output):
            self.assertEqual(main(["check-config", "--config", "missing-config-fixture.toml"]), 1)
        self.assertTrue(output.getvalue().startswith("error:"))

    def test_sandbox_failure_does_not_claim_success(self):
        output = io.StringIO()
        with redirect_stderr(output), patch("safety_games.__main__.DockerSandbox") as sandbox:
            sandbox.return_value.run.side_effect = SandboxUnavailable("fixture: Docker unavailable")
            self.assertEqual(main(["sandbox-check"]), 1)
        self.assertIn("Docker unavailable", output.getvalue())


if __name__ == "__main__":
    unittest.main()
