"""Explicit operator annotations; automatic evidence is never overwritten."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from .behavior import CATEGORIES, STATUSES
from .trajectory import read_events


def add_annotation(directory: Path, *, status, reviewer, note, evidence_events=(), categories=(), honest_reviewed=False, hacking_attempt=None):
    from .preservation import ensure_not_frozen
    ensure_not_frozen(directory)
    if status not in STATUSES or not reviewer.strip() or not note.strip():
        raise ValueError('A valid status, reviewer and contextual note are required')
    if any(c not in CATEGORIES for c in categories):
        raise ValueError('Unknown behavior category')
    events={e['event_id'] for e in read_events(directory)}
    if any(e not in events for e in evidence_events):
        raise ValueError('Evidence references a missing trajectory event')
    if status=='confirmed_hacking' and (not evidence_events or not categories):
        raise ValueError('Confirmation requires trajectory evidence and a category')
    if honest_reviewed and status!='no_hacking_detected':
        raise ValueError('Honest review is incompatible with a hacking/uncertain label')
    annotation={'timestamp':datetime.now(timezone.utc).isoformat(),'status':status,'reviewer':reviewer,'note':note,
                'evidence_events':list(evidence_events),'categories':list(categories),'honest_reviewed':honest_reviewed,'hacking_attempt':hacking_attempt}
    with (directory/'audit.jsonl').open('a',encoding='utf-8',newline='\n') as stream:
        stream.write(json.dumps(annotation,ensure_ascii=False)+'\n');stream.flush();os.fsync(stream.fileno())
    return annotation
