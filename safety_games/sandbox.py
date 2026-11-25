"""Execute Python only in disposable, restricted Linux Docker containers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import uuid

from .config import SandboxConfig


class SandboxError(RuntimeError):
    """Infrastructure failed; this must not be treated as a solution score."""


class SandboxUnavailable(SandboxError):
    """A compatible Docker engine or trusted image is unavailable."""


class SandboxCleanupError(SandboxError):
    """Container removal could not be confirmed; stop the experiment."""


class ExecutionStatus(str, Enum):
    OK = "ok"
    RUNTIME_ERROR = "runtime_error"
    TIMEOUT = "timeout"
    OUTPUT_LIMIT = "output_limit"
    OOM_KILLED = "oom_killed"


@dataclass(frozen=True)
class ExecutionResult:
    status: ExecutionStatus
    stdout: str
    stderr: str
    exit_code: int | None
    duration_s: float
    image_id: str


@dataclass(frozen=True)
class _Captured:
    returncode: int
    stdout: bytes
    stderr: bytes
    stopped: ExecutionStatus | None = None


def _capture(command: list[str], payload: bytes, timeout_s: float, limit: int) -> _Captured:
    """Bound combined stdout/stderr in host memory, including output floods.

    In production only the trusted Docker CLI is launched here. Threads avoid
    blocking on full pipes on Windows as well as Unix.
    """
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        shell=False,
    )
    buffers = [bytearray(), bytearray()]
    lock = threading.Lock()
    exceeded = threading.Event()
    stream_errors: list[OSError] = []

    def read(stream, index: int) -> None:
        try:
            while chunk := stream.read1(4096):
                with lock:
                    remaining = max(0, limit - sum(map(len, buffers)))
                    buffers[index].extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        exceeded.set()
        except OSError as exc:
            stream_errors.append(exc)

    def write() -> None:
        try:
            process.stdin.write(payload)
            process.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                process.stdin.close()
            except OSError:
                pass

    threads = [
        threading.Thread(target=read, args=(process.stdout, 0), daemon=True),
        threading.Thread(target=read, args=(process.stderr, 1), daemon=True),
        threading.Thread(target=write, daemon=True),
    ]
    stopped = None
    deadline = time.monotonic() + timeout_s
    try:
        for thread in threads:
            thread.start()
        while process.poll() is None:
            if exceeded.is_set():
                stopped = ExecutionStatus.OUTPUT_LIMIT
                break
            if time.monotonic() >= deadline:
                stopped = ExecutionStatus.TIMEOUT
                break
            try:
                process.wait(timeout=min(0.02, max(0.001, deadline - time.monotonic())))
            except subprocess.TimeoutExpired:
                continue
    finally:
        if process.poll() is None:
            process.kill()  # Killing the CLI alone is insufficient; run() removes the container.
        process.wait(timeout=5)
        for thread in threads:
            if thread.ident is not None:
                thread.join(timeout=5)
        if any(thread.is_alive() for thread in threads):
            raise SandboxError("Docker stream workers did not terminate")
        process.stdout.close()
        process.stderr.close()
    if stream_errors:
        raise SandboxError("Failed to read Docker output") from stream_errors[0]
    if exceeded.is_set():
        stopped = ExecutionStatus.OUTPUT_LIMIT
    return _Captured(process.returncode, bytes(buffers[0]), bytes(buffers[1]), stopped)


class DockerSandbox:
    """No host-execution fallback, host mounts, runtime pulls or secret forwarding.

    The Docker daemon and image are trusted. A single instance pins its image
    on first prepare() and is intended for sequential use.
    """

    CONTROL_TIMEOUT_S = 10

    def __init__(self, config: SandboxConfig):
        self.config = config
        self._docker = shutil.which("docker")
        self.image_id: str | None = None

    def _control(self, arguments: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
        if self._docker is None:
            raise SandboxUnavailable("Docker CLI not found; host execution is disabled")
        try:
            result = subprocess.run(
                [self._docker, *arguments], stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=self.CONTROL_TIMEOUT_S, shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SandboxUnavailable("Docker command unavailable or timed out") from exc
        if check and result.returncode:
            detail = result.stderr.decode("utf-8", errors="replace").strip()[:2048]
            raise SandboxError(f"Docker {arguments[0]} failed: {detail}")
        return result

    def prepare(self) -> str:
        """Check Linux/seccomp and resolve an existing trusted image to its ID."""
        if self.image_id is not None:
            return self.image_id
        try:
            system = self._control(["info", "--format", "{{json .}}"])
            info = json.loads(system.stdout)
            if info.get("OSType") != "linux":
                raise SandboxUnavailable("Linux containers are required")
            if not any(option.startswith("name=seccomp") for option in info.get("SecurityOptions", [])):
                raise SandboxUnavailable("Docker seccomp support is required")
            result = self._control(["image", "inspect", "--format", "{{json .}}", self.config.image])
            image = json.loads(result.stdout)
            image_id = image["Id"]
            image_config = image.get("Config") or {}
            if image.get("Os") != "linux" or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
                raise SandboxUnavailable("Expected a content-addressed Linux image")
            if image_config.get("Volumes"):
                raise SandboxUnavailable("Sandbox images must not declare volumes")
            if (image_config.get("Labels") or {}).get("org.safety-games.runner") != "1":
                raise SandboxUnavailable("Build the trusted sandbox/Dockerfile first")
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise SandboxUnavailable("Invalid Docker metadata") from exc
        self.image_id = image_id
        return image_id

    def _create_arguments(self, name: str) -> list[str]:
        cfg = self.config
        profile = Path(__file__).with_name('seccomp.json').resolve()
        if not profile.is_file():
            raise SandboxUnavailable('Bundled seccomp profile is missing; refusing execution')
        args = [
            "create", "--name", name, "--interactive", "--pull=never",
            "--network=none", "--ipc=none", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges=true", "--user=65534:65534",
            f"--security-opt=seccomp={profile}",
            f"--memory={cfg.memory_mb}m", f"--memory-swap={cfg.memory_mb}m",
            f"--cpus={cfg.cpus}", f"--pids-limit={cfg.pids_limit}",
            "--ulimit=nofile=64:64", "--ulimit=fsize=8388608:8388608", "--ulimit=core=0:0",
            f"--tmpfs=/tmp:rw,noexec,nosuid,nodev,size={cfg.tmpfs_mb}m,mode=1777",
            "--workdir=/tmp", "--hostname=sandbox", "--restart=no", "--log-driver=none",
            "--label=org.safety-games.managed=true", "--entrypoint=/usr/local/bin/python",
        ]
        # Docker may inject proxy credentials from its client configuration.
        # Explicit empty values override that behavior before the runner starts.
        for variable in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "FTP_PROXY"):
            for spelling in (variable, variable.lower()):
                args.extend(["--env", f"{spelling}="])
        args.extend([self.image_id, "-I", "-B", "/opt/sandbox/execute.py"])
        return args

    def _remove(self, name: str, *, allow_missing: bool) -> None:
        try:
            result = self._control(["rm", "--force", name], check=False)
            if result.returncode:
                if allow_missing and b"no such container" in result.stderr.lower():
                    return
                raise SandboxCleanupError(f"Could not remove container {name}; stop execution")
        except SandboxUnavailable as exc:
            raise SandboxCleanupError(f"Could not confirm removal of {name}; stop execution") from exc

    def run(self, source: str, stdin: str = "", *, public_files: dict[str, str] | None = None) -> ExecutionResult:
        if not isinstance(source, str) or not isinstance(stdin, str):
            raise TypeError("source and stdin must be strings")
        for label, value, limit in (
            ("source", source, self.config.max_source_bytes),
            ("stdin", stdin, self.config.max_stdin_bytes),
        ):
            if len(value.encode("utf-8")) > limit:
                raise ValueError(f"{label} exceeds its byte limit")
        image_id = self.prepare()
        data = {"source": source, "stdin": stdin}
        if public_files:
            if set(public_files) - {'test_cases.json', 'problem.md'} or any(not isinstance(v, str) for v in public_files.values()):
                raise ValueError('Only original public problem/test data may accompany a solution')
            if sum(len(v.encode('utf-8')) for v in public_files.values()) > self.config.max_source_bytes:
                raise ValueError('Public files exceed byte limit')
            data['files'] = public_files
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        name = "safety-games-" + uuid.uuid4().hex
        created = False
        try:
            self._control(self._create_arguments(name))
            created = True
            started = time.monotonic()
            captured = _capture(
                [self._docker, "start", "--attach", "--interactive", name],
                payload, self.config.timeout_s, self.config.max_output_bytes,
            )
            elapsed = time.monotonic() - started
            exit_code = None
            if captured.stopped is not None:
                status = captured.stopped
            else:
                state = json.loads(self._control(["inspect", "--format", "{{json .State}}", name]).stdout)
                if state.get("Running") or state.get("Status") != "exited" or state.get("Error"):
                    raise SandboxError("Docker attachment ended without a clean container exit")
                exit_code = state["ExitCode"]
                if type(exit_code) is not int:
                    raise SandboxError("Docker returned an invalid exit code")
                if state.get("OOMKilled"):
                    status = ExecutionStatus.OOM_KILLED
                else:
                    status = ExecutionStatus.OK if exit_code == 0 else ExecutionStatus.RUNTIME_ERROR
                if captured.returncode != exit_code:
                    raise SandboxError("Docker CLI and container exit codes disagree")
            return ExecutionResult(
                status=status, stdout=captured.stdout.decode("utf-8", errors="replace"),
                stderr=captured.stderr.decode("utf-8", errors="replace"),
                exit_code=exit_code, duration_s=elapsed, image_id=image_id,
            )
        except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise SandboxError("Sandbox transport or state inspection failed") from exc
        finally:
            # Includes timeout, output flood, attach failure and user interruption.
            self._remove(name, allow_missing=not created)
