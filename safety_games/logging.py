"""Single-writer round logger: canonical JSON and a rebuildable CSV view."""

import csv
from dataclasses import fields
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import tempfile
import uuid

from . import __version__
from .config import ExperimentConfig
from .results import RoundResult


class LogSyncError(OSError):
    """JSON was committed, but CSV needs rebuild_csv()."""


def _atomic_write(path: Path, text: str) -> None:
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False) as stream:
            temporary = stream.name
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def _json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2) + "\n"


def _csv_cell(value: object) -> object:
    # Spreadsheet formula protection. Canonical JSON preserves original strings.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


class RoundLogger:
    """A new run per instance. Never resumes or overwrites an existing run."""

    def __init__(self, config: ExperimentConfig, run_id: str | None = None):
        self.config = config
        self.run_id = run_id if run_id is not None else uuid.uuid4().hex
        if not isinstance(self.run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", self.run_id):
            raise ValueError("run_id must be a safe directory identifier (1..128 characters)")
        self.run_dir = config.output_dir / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self._records: list[dict] = []
        snapshot = config.to_dict()
        digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()
        _atomic_write(self.run_dir / "manifest.json", _json({
            "schema_version": 1,
            "run_id": self.run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "package_version": __version__,
            "python_version": platform.python_version(),
            "config_sha256": digest,
            "config": snapshot,
        }))
        _atomic_write(self.run_dir / "rounds.json", _json([]))
        self.rebuild_csv()

    def write(self, result: RoundResult) -> None:
        if result.run_id != self.run_id or result.mode != self.config.mode:
            raise ValueError("round run_id and mode must match the logger configuration")
        if result.round_index != len(self._records) + 1 or result.round_index > self.config.rounds:
            raise ValueError("rounds must be written once, sequentially, within the configured limit")
        records = [*self._records, result.to_dict()]
        _atomic_write(self.run_dir / "rounds.json", _json(records))
        self._records = records  # JSON is now the authoritative committed state.
        try:
            self.rebuild_csv()
        except OSError as exc:
            raise LogSyncError("JSON committed; call rebuild_csv() to repair CSV") from exc

    def rebuild_csv(self) -> None:
        records = json.loads((self.run_dir / "rounds.json").read_text(encoding="utf-8"))
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=["schema_version", *(f.name for f in fields(RoundResult))])
        writer.writeheader()
        writer.writerows({key: _csv_cell(value) for key, value in row.items()} for row in records)
        _atomic_write(self.run_dir / "rounds.csv", output.getvalue())
