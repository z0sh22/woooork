"""Append-only external trajectories; snapshots and diffs never enter the sandbox."""
import base64
from datetime import datetime, timezone
import difflib
import json
import os
from pathlib import Path
import re

from .artifacts import SecretRedactor, write_json
from .environment import file_text, validate_workspace_path
from .logging import _atomic_write


def markdown_record(record):
    serialized=json.dumps(record,ensure_ascii=False,allow_nan=False)
    longest=max((len(s) for s in re.findall(r'`+',serialized)),default=0)
    fence='`'*max(4,longest+1)
    return f"\n### Event {record['event_id']}, step {record['step']}: {record['type']}\n\n{fence}json\n{serialized}\n{fence}\n"


def changes_between(before: dict, after: dict) -> list[dict]:
    changes = []
    old, new = before.get('files', {}), after.get('files', {})
    for name in sorted(set(old) | set(new)):
        if old.get(name) == new.get(name):
            continue
        prior, current = file_text(before, name), file_text(after, name)
        changes.append({'path': name, 'before_sha256': old.get(name, {}).get('sha256'),
                        'after_sha256': new.get(name, {}).get('sha256'),
                        'change': 'created' if name not in old else 'deleted' if name not in new else 'modified',
                        'diff': ''.join(difflib.unified_diff((prior or '').splitlines(True), (current or '').splitlines(True),
                                                         fromfile='before/'+name, tofile='after/'+name)) if prior is not None or current is not None else None})
    return changes


class TrajectoryLogger:
    def __init__(self, directory: Path, *, experiment_id, run_id, episode_id, task_id, redactor=None):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.context = dict(experiment_id=experiment_id, run_id=run_id, episode_id=episode_id, task_id=task_id)
        self.redactor = redactor or SecretRedactor()
        path = directory / 'trajectory.jsonl'
        records=read_events(directory) if path.exists() else []
        self.sequence=max((record['event_id'] for record in records),default=0)
        self.step = 0
        if path.exists():
            raw=path.read_text(encoding='utf-8')
            lines=[line for line in raw.splitlines() if line.strip()]
            damaged=len(lines)!=len(records)
            if damaged:
                write_json(directory/f'rejected_tail_{self.sequence+1}.json',{'tail':self.redactor.clean(lines[-1]),'reason':'incomplete final JSONL record'})
            if damaged or not raw.endswith('\n'):
                _atomic_write(path,''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records))
            _atomic_write(directory/'trajectory.md',''.join(markdown_record(r) for r in records))
            if damaged:
                self.emit({'type':'trajectory_tail_recovered','status':'incomplete_tail_preserved_separately'})

    def emit(self, event: dict):
        self.sequence += 1
        record = {**self.context, 'event_id': self.sequence, 'step': self.step,
                  'timestamp': datetime.now(timezone.utc).isoformat(), 'type': 'event', 'tool_name': None,
                  'arguments': None, 'result': None, 'status': None, 'stdout': None, 'stderr': None,
                  'exit_code': None, 'duration_s': None, 'file_changes': [], 'usage': None, **event}
        record = self.redactor.clean(record)
        serialized = json.dumps(record, ensure_ascii=False, allow_nan=False)
        with (self.directory / 'trajectory.jsonl').open('a', encoding='utf-8', newline='\n') as stream:
            stream.write(serialized + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        # JSONL is canonical. Markdown can be rebuilt after an interruption.
        with (self.directory / 'trajectory.md').open('a', encoding='utf-8', newline='\n') as stream:
            stream.write(markdown_record(record))
            stream.flush()
        return record

    def save_snapshot(self, label: str, snapshot: dict):
        # No untrusted symlink is ever materialized on the host.
        cleaned = self.redactor.clean(snapshot)
        write_json(self.directory / (label + '_snapshot.json'), cleaned)
        for name, item in snapshot.get('files', {}).items():
            validate_workspace_path(name)
            if item.get('kind') != 'file':
                continue
            data = base64.b64decode(item['content'], validate=True)
            try:
                text = data.decode('utf-8')
            except UnicodeDecodeError:
                continue  # The exact bounded binary data remains in the snapshot.
            path = self.directory / label / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.redactor.clean(text), encoding='utf-8')


def read_events(directory: Path):
    path = directory / 'trajectory.jsonl'
    lines=[line for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    records=[]
    for index,line in enumerate(lines):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            if index!=len(lines)-1:
                raise ValueError('Trajectory corruption before final record; refusing silent recovery')
    return records
