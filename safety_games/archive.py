"""Allowlisted research ZIP export with preflight and post-write secret checks."""
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import zipfile

from .artifacts import write_json
from .preservation import ensure_not_frozen

ROOT_FILES = frozenset(('README.md','requirements.txt','pyproject.toml','.env.example','.gitignore','.gitattributes'))
TREES = ('safety_games','sandbox','third_party','configs','data','prompts','tests','scripts','docs','.github',
         'results/baseline-v1-r2','results/baseline-v1.1-preparation','results/protocol_archives/r2',
         'results/baseline-v1-1-control-20261126','results/baseline-v1-1-control-plan-20261126')
EXCLUDED = frozenset(('.git','.venv','venv','__pycache__','.research_cache','.research_tools','node_modules',
                      '.aws','.codex','.agents','build','dist','exports'))
SECRET_PATTERN = re.compile(rb'gsk_[A-Za-z0-9_-]{16,}|sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}|AKIA[0-9A-Z]{16}|-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----')


class UnsafeArchive(ValueError):
    pass


def _excluded(relative):
    # Source/scanner filenames may discuss secrets without containing them.
    # Credential documents are excluded; source files still undergo content scans.
    credential_name = relative.suffix.lower() != '.py' and bool(re.search(r'(?:^|[._-])(?:credentials|secrets|passwords|api[-_]?keys)(?:[._-]|$)', relative.name, re.I))
    env_name = relative.name != '.env.example' and bool(re.search(r'(?:^|\.)env(?:\.|$)', relative.name, re.I))
    return credential_name or env_name or any(part.lower() in EXCLUDED or part.lower().startswith('.env') and part != '.env.example'
               for part in relative.parts) or relative.suffix.lower() in ('.pyc','.pyo','.zip','.pem','.key','.p12','.pfx')


def _local_secrets(root):
    # Read solely for local leak detection; never send or print these values.
    values = [os.environ.get('GROQ_API_KEY','')]
    path = root/'.env'
    if path.exists():
        from dotenv import dotenv_values
        values += [v for k,v in dotenv_values(path, interpolate=False).items()
                   if re.search(r'(key|token|secret|password)', k, re.I)]
    return tuple(v.encode('utf-8') for v in values if isinstance(v, str) and len(v) >= 8)


def contains_secret(raw, secrets=()):
    if SECRET_PATTERN.search(raw) or any(secret in raw for secret in secrets):
        return True
    # Snapshot content can be embedded deep inside JSONL/API events. Decode
    # only bounded valid base64 strings from a content field, never unpickle.
    for match in re.finditer(rb'"content"\s*:\s*"([A-Za-z0-9+/=]{4,})"', raw):
        try:
            decoded = base64.b64decode(match.group(1), validate=True)
        except ValueError:
            continue
        if SECRET_PATTERN.search(decoded) or any(secret in decoded for secret in secrets):
            return True
    return False


def inspect_archive(path, *, secrets=()):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise UnsafeArchive('Duplicate archive entries')
        for info in archive.infolist():
            relative = PurePosixPath(info.filename)
            if relative.is_absolute() or '..' in relative.parts or _excluded(relative) or '\\' in info.filename:
                raise UnsafeArchive('Unsafe or excluded archive member: ' + info.filename)
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise UnsafeArchive('Symlink archive member')
            if contains_secret(archive.read(info), secrets):
                raise UnsafeArchive('Potential credential in archive member: ' + info.filename)
        return {'checked_members':len(names), 'secret_found':False, 'excluded_paths_found':False}


def check_git_history(root):
    git_path = root/'.git'
    if not git_path.exists():
        return {'git_repository':False, 'env_tracked':False, 'history_checked':False,
                'note':'No local Git repository; no local history exists to inspect. External archives/history cannot be checked here.'}
    def run(*args):
        result = subprocess.run(['git','-C',str(root),*args], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise UnsafeArchive('Cannot verify local Git history')
        return result.stdout.splitlines()
    tracked = run('ls-files','--','.env','.env.*',':(exclude).env.example')
    history = run('log','--all','--format=','--name-only','--','.env','.env.*',':(exclude).env.example')
    return {'git_repository':True, 'env_tracked':bool(tracked), 'history_checked':True,
            'env_in_history':any(x.strip() for x in history)}


def create_research_archive(root: Path, output: Path):
    root, output = root.resolve(), output.resolve()
    ensure_not_frozen(output)
    if output.exists():
        raise FileExistsError('Refusing to overwrite an existing export')
    secrets = _local_secrets(root)
    files = set(root/name for name in ROOT_FILES if (root/name).is_file())
    for name in TREES:
        if (root/name).exists():
            files.update(p for p in (root/name).rglob('*') if p.is_file())
    selected = []
    for path in sorted(files):
        relative = path.relative_to(root)
        if _excluded(relative):
            continue
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != root) or root not in path.resolve().parents:
            raise UnsafeArchive('Symlinks/outside-root files are not exported')
        if path.stat().st_size > 32 * 1024 * 1024:
            raise UnsafeArchive('Unexpectedly large export member: ' + relative.as_posix())
        if contains_secret(path.read_bytes(), secrets):
            raise UnsafeArchive('Potential credential; export stopped: ' + relative.as_posix())
        selected.append(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + '.partial')
    if temporary.exists():
        raise FileExistsError('Previous partial export exists; inspect it before removal')
    try:
        with zipfile.ZipFile(temporary, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
            for path in selected:
                raw = path.read_bytes()
                if contains_secret(raw, secrets):
                    raise UnsafeArchive('File changed to contain a potential secret during export')
                archive.writestr(path.relative_to(root).as_posix(), raw)
        inspection = inspect_archive(temporary, secrets=secrets)
        # Verify the exact ZIP before giving it its final export name.
        sha = hashlib.sha256(temporary.read_bytes()).hexdigest()
        temporary.replace(output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    report = {'archive':str(output), 'sha256':sha, **inspection, 'git':check_git_history(root),
              'excluded':'Secrets, .env, Git objects, virtualenvs, caches and unallowlisted paths. User PDFs are not redistributed.'}
    write_json(output.with_suffix(output.suffix+'.inspection.json'), report)
    return report
