"""Trusted episode transport. This file runs only INSIDE the Docker sandbox."""
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import selectors
import signal
import stat
import subprocess
import sys
import time

ROOT = Path('/tmp/workspace')


def parent_fd(name, create=False):
    if not isinstance(name, str) or not name or '\\' in name or '\x00' in name:
        raise ValueError('invalid workspace path')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or not path.parts or ':' in name:
        raise ValueError('path must remain inside the workspace')
    fd = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[:-1]:
            if create:
                try:
                    os.mkdir(part, dir_fd=fd)
                except FileExistsError:
                    pass
            new_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new_fd
        return fd, path.name
    except BaseException:
        os.close(fd)
        raise


def read_bytes(name, limit):
    parent, leaf = parent_fd(name)
    try:
        fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                raise ValueError('not a regular file or file exceeds byte limit')
            data = stream.read(limit + 1)
            if len(data) > limit:
                raise ValueError('file exceeds byte limit')
            return data
    finally:
        os.close(parent)


def write_text(name, content, limit):
    data = content.encode('utf-8')
    if len(data) > limit:
        raise ValueError('file exceeds byte limit')
    parent, leaf = parent_fd(name, create=True)
    try:
        fd = os.open(leaf, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=parent)
        with os.fdopen(fd, 'wb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError('not a regular file')
            stream.truncate(0)
            stream.write(data)
        return {'bytes_written': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    finally:
        os.close(parent)


def snapshot(max_bytes, max_files):
    files, errors, total = {}, [], 0
    for directory, dirs, names in os.walk(ROOT, followlinks=False):
        dirs.sort()
        for name in sorted([*names, *(d for d in dirs if (Path(directory) / d).is_symlink())]):
            path = Path(directory) / name
            relative = path.relative_to(ROOT).as_posix()
            if len(files) >= max_files:
                errors.append('workspace file limit exceeded')
                return {'files': files, 'complete': False, 'errors': errors}
            try:
                mode = path.lstat().st_mode
                if stat.S_ISLNK(mode):
                    files[relative] = {'kind': 'symlink', 'target': os.readlink(path)}
                elif stat.S_ISREG(mode):
                    data = read_bytes(relative, max_bytes - total)
                    total += len(data)
                    files[relative] = {'kind': 'file', 'encoding': 'base64', 'content': base64.b64encode(data).decode('ascii'),
                                       'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                else:
                    files[relative] = {'kind': 'special'}
                    errors.append('special file: ' + relative)
            except (OSError, ValueError) as exc:
                errors.append(relative + ': ' + type(exc).__name__)
    return {'files': files, 'complete': not errors, 'errors': errors}


def command_run(command, timeout, output_limit):
    environment = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': str(ROOT), 'LANG': 'C.UTF-8'}
    started = time.monotonic()
    process = subprocess.Popen(command, shell=True, executable='/bin/sh', cwd=ROOT, env=environment,
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ, 0)
    selector.register(process.stderr, selectors.EVENT_READ, 1)
    buffers, status = [bytearray(), bytearray()], 'ok'
    try:
        while selector.get_map():
            if time.monotonic() - started >= timeout:
                status = 'timeout'
                break
            for key, _ in selector.select(timeout=0.05):
                chunk = os.read(key.fd, 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                remaining = max(0, output_limit - sum(map(len, buffers)))
                buffers[key.data].extend(chunk[:remaining])
                if len(chunk) > remaining:
                    status = 'output_limit'
                    break
            if status != 'ok':
                break
        if status == 'ok':
            process.wait(timeout=max(0.01, timeout - (time.monotonic() - started)))
    except subprocess.TimeoutExpired:
        status = 'timeout'
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=2)
        selector.close()
        process.stdout.close()
        process.stderr.close()
    if status == 'ok' and process.returncode:
        status = 'runtime_error'
    return {'status': status, 'stdout': buffers[0].decode('utf-8', errors='replace'),
            'stderr': buffers[1].decode('utf-8', errors='replace'), 'exit_code': process.returncode,
            'duration_s': time.monotonic() - started}


def dispatch(request):
    action, args = request['action'], request.get('arguments', {})
    limits = request.get('limits', {})
    size = limits.get('max_bytes', 1048576)
    count = limits.get('max_files', 64)
    if action == 'initialize':
        ROOT.mkdir(mode=0o700)
        for name, text in args['files'].items():
            write_text(name, text, size)
        return {'initialized': True}
    if action == 'snapshot':
        return snapshot(size, count)
    if action == 'list_files':
        snap = snapshot(size, count)
        return {'files': {name: {k: v for k, v in item.items() if k != 'content'} for name, item in snap['files'].items()},
                'complete': snap['complete'], 'errors': snap['errors']}
    if action == 'read_file':
        data = read_bytes(args['path'], min(size, args.get('max_bytes', size)))
        return {'content': data.decode('utf-8', errors='replace'), 'bytes_read': len(data)}
    if action == 'write_file':
        return write_text(args['path'], args['content'], size)
    if action == 'run_command':
        return command_run(args['command'], request['timeout_s'], request['output_limit'])
    raise ValueError('unknown workspace action')


if __name__ == '__main__':
    try:
        request = json.load(sys.stdin)
        # Neither environment nor credentials from the controller are accepted.
        result = {'ok': True, 'result': dispatch(request)}
    except (ValueError, KeyError, TypeError, OSError) as exc:
        result = {'ok': False, 'error_type': type(exc).__name__, 'message': str(exc)[:300]}
    print(json.dumps(result, ensure_ascii=True))
