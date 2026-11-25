from dataclasses import replace
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from safety_games.config import SandboxConfig
from safety_games.sandbox import (
    DockerSandbox, ExecutionStatus, SandboxCleanupError, SandboxError,
    SandboxUnavailable, _Captured, _capture,
)


IMAGE_ID = "sha256:" + "a" * 64


class SandboxTests(unittest.TestCase):
    def setUp(self):
        self.sandbox = DockerSandbox(SandboxConfig())
        self.sandbox._docker = "docker-fixture"
        self.commands = []
        self.info = {"OSType": "linux", "SecurityOptions": ["name=seccomp,profile=builtin"]}
        self.image = {"Id": IMAGE_ID, "Os": "linux", "Config": {"Labels": {"org.safety-games.runner": "1"}}}
        self.state = {"Status": "exited", "Running": False, "ExitCode": 0, "OOMKilled": False, "Error": ""}
        self.control_patch = patch.object(self.sandbox, "_control", side_effect=self.control)
        self.control_patch.start()
        self.addCleanup(self.control_patch.stop)

    def control(self, arguments, **kwargs):
        self.commands.append(arguments)
        data = self.info if arguments[0] == "info" else self.image if arguments[0] == "image" else self.state if arguments[0] == "inspect" else {}
        return subprocess.CompletedProcess(arguments, 0, json.dumps(data).encode(), b"")

    def run_fixture(self, captured=None):
        if captured is None:
            captured = _Captured(0, b"fixture-output\n", b"")
        with patch("safety_games.sandbox._capture", return_value=captured) as capture:
            result = self.sandbox.run("fixture-source", "fixture-stdin")
        return result, capture

    def test_run_uses_hardened_container_and_pins_image(self):
        result, capture = self.run_fixture()
        create = next(c for c in self.commands if c[0] == "create")
        for flag in ("--network=none", "--read-only", "--cap-drop=ALL", "--user=65534:65534",
                     "--security-opt=no-new-privileges=true", "--pull=never", "--ipc=none",
                     "--memory=128m", "--memory-swap=128m", "--pids-limit=32", "--log-driver=none"):
            self.assertIn(flag, create)
        self.assertIn(IMAGE_ID, create)
        self.assertNotIn(self.sandbox.config.image, create)
        self.assertFalse(any(arg.startswith(("--volume", "--mount", "--privileged", "--env-file")) for arg in create))
        self.assertIn("HTTP_PROXY=", create)
        self.assertEqual(result.status, ExecutionStatus.OK)
        self.assertEqual(result.image_id, IMAGE_ID)
        self.assertEqual(json.loads(capture.call_args.args[1]), {"source": "fixture-source", "stdin": "fixture-stdin"})
        self.assertEqual(self.commands[-1][0:2], ["rm", "--force"])
        self.assertEqual(self.commands[-1][-1], create[2])

    def test_prepare_is_cached_for_one_experiment_instance(self):
        self.sandbox.prepare()
        self.sandbox.prepare()
        self.assertEqual(sum(c[0] == "image" for c in self.commands), 1)

    def test_rejects_windows_engine_missing_seccomp_and_untrusted_image(self):
        for kind in ("windows", "seccomp", "volumes", "label", "image_id"):
            with self.subTest(kind=kind):
                old_info = json.loads(json.dumps(self.info))
                old_image = json.loads(json.dumps(self.image))
                if kind == "windows":
                    self.info["OSType"] = "windows"
                elif kind == "seccomp":
                    self.info["SecurityOptions"] = []
                elif kind == "volumes":
                    self.image["Config"]["Volumes"] = {"/data": {}}
                elif kind == "label":
                    self.image["Config"]["Labels"] = {}
                else:
                    self.image["Id"] = "mutable-tag"
                with self.assertRaises(SandboxUnavailable):
                    self.sandbox.prepare()
                self.info, self.image = old_info, old_image
        self.assertFalse(any(c[0] == "create" for c in self.commands))

    def test_timeout_and_output_limit_always_remove_container(self):
        for status in (ExecutionStatus.TIMEOUT, ExecutionStatus.OUTPUT_LIMIT):
            with self.subTest(status=status):
                result, _ = self.run_fixture(_Captured(-9, b"partial", b"", status))
                self.assertEqual(result.status, status)
                self.assertIsNone(result.exit_code)
                self.assertEqual(self.commands[-1][0:2], ["rm", "--force"])

    def test_runtime_error_and_oom_are_distinct_from_infrastructure_failures(self):
        self.state["ExitCode"] = 137
        result, _ = self.run_fixture(_Captured(137, b"", b""))
        self.assertEqual(result.status, ExecutionStatus.RUNTIME_ERROR)
        self.state["OOMKilled"] = True
        result, _ = self.run_fixture(_Captured(137, b"", b""))
        self.assertEqual(result.status, ExecutionStatus.OOM_KILLED)

    def test_failed_attachment_and_interrupt_still_remove_container(self):
        for error in (OSError("fixture"), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                with patch("safety_games.sandbox._capture", side_effect=error):
                    with self.assertRaises(SandboxError if isinstance(error, OSError) else KeyboardInterrupt):
                        self.sandbox.run("fixture")
                self.assertEqual(self.commands[-1][0:2], ["rm", "--force"])

    def test_running_container_or_disagreeing_exit_codes_are_not_success(self):
        self.state["Running"] = True
        with self.assertRaises(SandboxError):
            self.run_fixture()
        self.state["Running"] = False
        with self.assertRaises(SandboxError):
            self.run_fixture(_Captured(1, b"", b""))

    def test_failed_cleanup_is_not_silently_ignored(self):
        with patch.object(self.sandbox, "_remove", side_effect=SandboxCleanupError("fixture")):
            with self.assertRaises(SandboxCleanupError):
                self.run_fixture()

    def test_missing_container_is_accepted_only_after_failed_creation(self):
        missing = subprocess.CompletedProcess([], 1, b"", b"Error: No such container: fixture")
        with patch.object(self.sandbox, "_control", return_value=missing):
            self.sandbox._remove("fixture", allow_missing=True)
            with self.assertRaises(SandboxCleanupError):
                self.sandbox._remove("fixture", allow_missing=False)

    def test_failed_creation_still_attempts_cleanup(self):
        original_control = self.control

        def failing_control(arguments, **kwargs):
            if arguments[0] == "create":
                raise SandboxError("fixture: creation failed")
            return original_control(arguments, **kwargs)

        with patch.object(self.sandbox, "_control", side_effect=failing_control):
            with self.assertRaises(SandboxError):
                self.sandbox.run("fixture")
        self.assertEqual(self.commands[-1][0:2], ["rm", "--force"])

    def test_malformed_container_state_is_an_infrastructure_error(self):
        self.state = None
        with self.assertRaises(SandboxError):
            self.run_fixture()
        self.assertEqual(self.commands[-1][0:2], ["rm", "--force"])

    def test_input_limits_are_checked_before_docker_is_called(self):
        self.sandbox.config = replace(self.sandbox.config, max_source_bytes=1, max_stdin_bytes=1)
        for source, stdin in (("я", ""), ("", "я")):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.sandbox.run(source, stdin)
        self.assertEqual(self.commands, [])

    def test_missing_docker_never_launches_host_python(self):
        with patch("safety_games.sandbox.shutil.which", return_value=None):
            sandbox = DockerSandbox(SandboxConfig())
        with patch("safety_games.sandbox.subprocess.Popen") as popen:
            with self.assertRaises(SandboxUnavailable):
                sandbox.run("fixture")
        popen.assert_not_called()


class CaptureTests(unittest.TestCase):
    """Static, trusted pipe fixtures only; never execute model-supplied code."""

    def command(self, fixture):
        return [sys.executable, "-I", "-c", fixture]

    def test_stdin_and_separate_streams(self):
        command = self.command("import sys; sys.stdout.buffer.write(sys.stdin.buffer.read()); sys.stderr.buffer.write(b'err')")
        result = _capture(command, "тест".encode("utf-8"), 3, 1024)
        self.assertEqual(result.stdout, "тест".encode("utf-8"))
        self.assertEqual(result.stderr, b"err")
        self.assertEqual(result.returncode, 0)
        self.assertIsNone(result.stopped)

    def test_output_flood_is_bounded_in_host_memory(self):
        command = self.command("import os\nwhile True: os.write(1, b'x' * 4096)")
        result = _capture(command, b"", 3, 1024)
        self.assertEqual(result.stopped, ExecutionStatus.OUTPUT_LIMIT)
        self.assertEqual(len(result.stdout) + len(result.stderr), 1024)

    def test_output_limit_is_combined_across_both_streams(self):
        command = self.command("import os; os.write(1, b'a' * 100); os.write(2, b'b' * 100)")
        result = _capture(command, b"", 3, 120)
        self.assertEqual(result.stopped, ExecutionStatus.OUTPUT_LIMIT)
        self.assertEqual(len(result.stdout) + len(result.stderr), 120)

    def test_timeout_terminates_transport(self):
        result = _capture(self.command("import time; time.sleep(3)"), b"", 0.1, 1024)
        self.assertEqual(result.stopped, ExecutionStatus.TIMEOUT)

    def test_timeout_does_not_block_on_unread_large_stdin(self):
        result = _capture(self.command("import time; time.sleep(3)"), b"x" * 1048576, 0.1, 1024)
        self.assertEqual(result.stopped, ExecutionStatus.TIMEOUT)


if __name__ == "__main__":
    unittest.main()
