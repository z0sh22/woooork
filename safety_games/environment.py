"""One Docker container per episode, no host filesystem mounts."""
import base64
import json
from pathlib import PurePosixPath
import uuid

from .config import AgentConfig, SandboxConfig
from .sandbox import DockerSandbox, SandboxError, _capture


class ToolError(SandboxError):
    pass


def validate_workspace_path(path: str) -> str:
    if not isinstance(path, str) or not path or '\\' in path or ':' in path or '\x00' in path:
        raise ValueError('Expected a relative workspace path')
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or '..' in parsed.parts or not parsed.parts:
        raise ValueError('Path is outside the workspace')
    return parsed.as_posix()


def file_text(snapshot: dict, name: str) -> str | None:
    item = snapshot.get('files', {}).get(name)
    if item is None or item.get('kind') != 'file':
        return None
    return base64.b64decode(item['content'], validate=True).decode('utf-8', errors='replace')


class DockerEpisode:
    def __init__(self, sandbox: SandboxConfig, agent: AgentConfig, files: dict[str, str]):
        self.executor = DockerSandbox(sandbox)
        self.agent_config = agent
        self.initial_files = files
        self.name = 'safety-games-' + uuid.uuid4().hex
        self.created = False

    def __enter__(self):
        self.executor.prepare()
        args = self.executor._create_arguments(self.name)
        index = args.index(self.executor.image_id)
        args[index + 1:] = ['-I', '-B', '-c', 'import time; time.sleep(86400)']
        try:
            self.executor._control(args)
            self.created = True
            self.executor._control(['start', self.name])
            self.request('initialize', {'files': self.initial_files})
            return self
        except BaseException:
            self.executor._remove(self.name, allow_missing=not self.created)
            raise

    def request(self, action: str, arguments: dict | None = None) -> dict:
        arguments = arguments or {}
        if action in ('read_file', 'write_file'):
            validate_workspace_path(arguments.get('path'))
        payload = {'action': action, 'arguments': arguments,
                   'limits': {'max_bytes': self.agent_config.max_workspace_bytes, 'max_files': self.agent_config.max_workspace_files},
                   'timeout_s': self.agent_config.command_timeout_s,
                   'output_limit': self.executor.config.max_output_bytes}
        command = [self.executor._docker, 'exec', '--interactive', '--workdir=/tmp', self.name,
                   '/usr/local/bin/python', '-I', '-B', '/opt/sandbox/tool.py']
        # Snapshot envelopes are larger than command output, but remain bounded.
        captured = _capture(command, json.dumps(payload).encode('utf-8'),
                            self.agent_config.command_timeout_s + 5,
                            self.agent_config.max_workspace_bytes * 3 + 65536)
        if captured.stopped is not None or captured.returncode:
            raise ToolError('Container tool transport failed or exceeded its limits')
        try:
            result = json.loads(captured.stdout)
            if not isinstance(result, dict) or type(result.get('ok')) is not bool:
                raise ValueError('Invalid envelope')
            return result
        except (ValueError, UnicodeError) as exc:
            raise ToolError('Invalid container tool response') from exc

    def snapshot(self) -> dict:
        response = self.request('snapshot')
        if not response.get('ok') or not response['result'].get('complete'):
            raise ToolError('Workspace snapshot is incomplete; episode cannot be silently scored')
        return response['result']

    def __exit__(self, *exc):
        self.executor._remove(self.name, allow_missing=False)
