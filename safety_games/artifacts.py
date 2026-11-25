"""Controller-owned durable artifacts and secret redaction."""
from contextlib import contextmanager
import base64
import hashlib
import json
import os
from pathlib import Path
import re

from .logging import _atomic_write


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


class SecretRedactor:
    def __init__(self, secrets=()):
        self._secrets = tuple(s for s in secrets if isinstance(s, str) and s)

    def clean(self, value):
        if isinstance(value, str):
            for secret in self._secrets:
                value = value.replace(secret, "[REDACTED]")
            return re.sub(r"gsk_[A-Za-z0-9_-]{16,}", "[REDACTED]", value)
        if isinstance(value, dict):
            cleaned = {self.clean(k): self.clean(v) for k, v in value.items()}
            if value.get('kind') == 'file' and value.get('encoding') == 'base64' and isinstance(value.get('content'), str):
                try:
                    raw = base64.b64decode(value['content'], validate=True)
                except ValueError:
                    return cleaned
                redacted = raw
                for secret in self._secrets:
                    redacted = redacted.replace(secret.encode('utf-8'), b'[REDACTED]')
                redacted = re.sub(rb'gsk_[A-Za-z0-9_-]{16,}', b'[REDACTED]', redacted)
                if redacted != raw:
                    cleaned.update(content=base64.b64encode(redacted).decode('ascii'),content_redacted=True,
                                   redacted_content_sha256=hashlib.sha256(redacted).hexdigest())
            return cleaned
        if isinstance(value, (tuple, list)):
            return [self.clean(v) for v in value]
        return value


@contextmanager
def exclusive_run(path: Path):
    """Single controller per run. A stale lock requires explicit operator removal."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, str(os.getpid()).encode())
        os.close(descriptor)
        descriptor = None
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        path.unlink(missing_ok=True)
