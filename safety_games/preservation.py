"""Keep the published v1.0 run and frozen protocol archive read-only to tools."""
import hashlib
import json
from pathlib import Path


def ensure_not_frozen(path):
    path = Path(path).resolve()
    parts = path.parts
    if 'baseline-v1-r2' in parts or any(parts[i:i+2] == ('protocol_archives', 'r2') for i in range(len(parts)-1)):
        raise ValueError('Frozen v1.0 artifacts are read-only. Choose a separate output directory.')


def verify_preservation(manifest):
    expected = json.loads(Path(manifest).read_text(encoding='utf-8'))['files']
    changed = [name for name, sha in expected.items()
               if not Path(name).is_file() or hashlib.sha256(Path(name).read_bytes()).hexdigest() != sha]
    roots = ('results/baseline-v1-r2', 'results/protocol_archives/r2', 'data')
    added = [p.as_posix() for root in roots for p in Path(root).rglob('*')
             if p.is_file() and '__pycache__' not in p.parts and p.as_posix() not in expected]
    return {'success': not changed and not added, 'checked_files': len(expected),
            'changed_or_missing': changed, 'added_to_frozen_trees': added}
