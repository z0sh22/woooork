"""Real isolation checks, opt-in and mandatory (no skips) when enabled."""

from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from safety_games.config import SandboxConfig
from safety_games.sandbox import DockerSandbox, ExecutionStatus


@unittest.skipUnless(os.environ.get("SAFETY_GAMES_DOCKER_TESTS") == "1", "set SAFETY_GAMES_DOCKER_TESTS=1 to test real Docker isolation")
class DockerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = SandboxConfig(image=os.environ.get("SAFETY_GAMES_SANDBOX_IMAGE", "safety-games-sandbox:local"))
        # An explicitly requested integration run must fail if Docker is absent.
        DockerSandbox(cls.config).prepare()

    def sandbox(self, **changes):
        return DockerSandbox(replace(self.config, **changes))

    def assert_ok(self, source, stdin=""):
        result = self.sandbox().run(source, stdin)
        self.assertEqual(result.status, ExecutionStatus.OK, result.stderr)
        return result

    def test_stdin_stdout_and_unicode(self):
        result = self.assert_ok("import sys; print(sys.stdin.read().upper())", "тест")
        self.assertEqual(result.stdout, "ТЕСТ\n")

    def test_no_external_network_or_extra_network_interfaces(self):
        self.assert_ok('''from pathlib import Path
import socket
assert sorted(p.name for p in Path('/sys/class/net').iterdir()) == ['lo']
try:
    connection = socket.create_connection(('1.1.1.1', 443), timeout=0.2)
except OSError:
    pass
else:
    connection.close()
    raise AssertionError('external network accessible')
''')

    def test_host_files_credentials_and_docker_socket_are_not_exposed(self):
        with tempfile.TemporaryDirectory() as directory:
            sentinel = Path(directory) / "host-only-secret.txt"
            sentinel.write_text(uuid.uuid4().hex, encoding="utf-8")
            source = f'''import os
from pathlib import Path
assert not Path({str(sentinel)!r}).exists()
assert not Path('/var/run/docker.sock').exists()
assert not Path('/run/docker.sock').exists()
assert 'SAFETY_GAMES_TEST_SECRET' not in os.environ
assert 'OPENAI_API_KEY' not in os.environ
assert 'HTTP_PROXY' not in os.environ
assert os.getuid() == 65534
'''
            with patch.dict(os.environ, {"SAFETY_GAMES_TEST_SECRET": "test-only", "OPENAI_API_KEY": "test-only", "HTTP_PROXY": "http://test-only:credential@127.0.0.1:9"}):
                self.assert_ok(source)

    def test_root_is_read_only_and_workspace_is_fresh_per_execution(self):
        self.assert_ok('''from pathlib import Path
Path('/tmp/round-marker').write_text('fixture')
try:
    Path('/opt/sandbox/execute.py').write_text('mutation')
except OSError:
    pass
else:
    raise AssertionError('trusted image is writable')
''')
        self.assert_ok("from pathlib import Path; assert not Path('/tmp/round-marker').exists()")

    def test_resource_limits_are_active(self):
        self.assert_ok('''import resource
assert resource.getrlimit(resource.RLIMIT_NOFILE) == (64, 64)
assert resource.getrlimit(resource.RLIMIT_CORE) == (0, 0)
assert resource.getrlimit(resource.RLIMIT_FSIZE) == (8388608, 8388608)
''')

    def test_timeout_removes_container_and_all_descendants(self):
        sandbox = self.sandbox(timeout_s=1.5)
        with patch.object(sandbox, "_remove", wraps=sandbox._remove) as remove:
            result = sandbox.run('''import subprocess, sys, time
subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
time.sleep(60)
''')
        self.assertEqual(result.status, ExecutionStatus.TIMEOUT)
        name = remove.call_args.args[0]
        self.assertNotEqual(sandbox._control(["inspect", name], check=False).returncode, 0)

    def test_output_flood_has_a_host_memory_bound(self):
        result = self.sandbox(max_output_bytes=1024).run("import os\nwhile True: os.write(1, b'x' * 4096)")
        self.assertEqual(result.status, ExecutionStatus.OUTPUT_LIMIT)
        self.assertEqual(len(result.stdout.encode("utf-8")), 1024)

    def test_memory_limit_is_enforced_by_the_engine(self):
        result = self.sandbox().run("allocation = bytearray(512 * 1024 * 1024)")
        self.assertEqual(result.status, ExecutionStatus.OOM_KILLED, result.stderr)


if __name__ == "__main__":
    unittest.main()
