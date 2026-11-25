import csv
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from safety_games.config import ExperimentConfig, ExperimentMode
from safety_games.logging import LogSyncError, RoundLogger, _atomic_write
from safety_games.results import RoundResult, RoundStatus


class LoggingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = ExperimentConfig(output_dir=Path(self.directory.name), rounds=3)
        self.logger = RoundLogger(self.config, run_id="unit-test")

    def result(self, **changes):
        base = RoundResult("unit-test", 1, "fixture", ExperimentMode.BASELINE, "test-only", RoundStatus.COMPLETED)
        return replace(base, **changes)

    def read_json(self):
        return json.loads((self.logger.run_dir / "rounds.json").read_text(encoding="utf-8"))

    def read_csv(self):
        with (self.logger.run_dir / "rounds.csv").open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    def test_new_run_contains_no_fabricated_rounds(self):
        self.assertEqual(self.read_json(), [])
        self.assertEqual(self.read_csv(), [])
        manifest = json.loads((self.logger.run_dir / "manifest.json").read_text(encoding="utf-8"))
        digest = hashlib.sha256(json.dumps(self.config.to_dict(), sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()
        self.assertEqual(manifest["config_sha256"], digest)

    def test_json_csv_preserve_independent_scores_unicode_and_nulls(self):
        self.logger.write(self.result(task_id='проверка,"\nстрока', public_score=1.0, protected_score=0.25))
        observed = self.read_json()[0]
        self.assertEqual(observed["protected_score"], 0.25)
        self.assertEqual(observed["public_score"], 1)
        self.assertIsNone(observed["reward"])
        self.assertEqual(self.read_csv()[0]["task_id"], observed["task_id"])
        self.assertEqual(self.read_csv()[0]["reward"], "")

    def test_spreadsheet_formulas_are_escaped_only_in_csv(self):
        for index, identifier in enumerate(("=1+1", "  @SUM(1)", "\t-2+3"), start=1):
            self.logger.write(self.result(round_index=index, task_id=identifier))
        for source, exported in zip(self.read_json(), self.read_csv()):
            self.assertEqual(exported["task_id"], "'" + source["task_id"])

    def test_duplicate_out_of_order_or_mismatched_rounds_are_rejected(self):
        for changes in ({"round_index": 2}, {"run_id": "wrong"}, {"mode": ExperimentMode.REPUTATION}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.logger.write(self.result(**changes))
        self.logger.write(self.result())
        with self.assertRaises(ValueError):
            self.logger.write(self.result())

    def test_existing_run_and_path_traversal_are_rejected(self):
        with self.assertRaises(FileExistsError):
            RoundLogger(self.config, run_id="unit-test")
        for run_id in ("../outside", "", "a/b", "C:\\outside"):
            with self.subTest(run_id=run_id), self.assertRaises(ValueError):
                RoundLogger(self.config, run_id=run_id)

    def test_csv_failure_retains_committed_json_and_can_be_repaired(self):
        with patch.object(self.logger, "rebuild_csv", side_effect=OSError("fixture failure")):
            with self.assertRaises(LogSyncError):
                self.logger.write(self.result())
        self.assertEqual(len(self.read_json()), 1)
        self.assertEqual(self.read_csv(), [])
        self.logger.rebuild_csv()
        self.assertEqual(len(self.read_csv()), 1)
        self.logger.write(self.result(round_index=2))

    def test_json_failure_does_not_advance_round_or_corrupt_previous_file(self):
        with patch("safety_games.logging.os.replace", side_effect=OSError("fixture failure")):
            with self.assertRaises(OSError):
                self.logger.write(self.result())
        self.assertEqual(self.read_json(), [])
        self.logger.write(self.result())
        self.assertEqual(len(self.read_json()), 1)

    def test_atomic_write_cleans_its_temporary_file_on_failure(self):
        target = self.logger.run_dir / "extra.json"
        original_files = set(self.logger.run_dir.iterdir())
        with patch("safety_games.logging.os.replace", side_effect=OSError("fixture failure")):
            with self.assertRaises(OSError):
                _atomic_write(target, "fixture")
        self.assertEqual(set(self.logger.run_dir.iterdir()), original_files)

    def test_invalid_scores_and_naive_timestamp_are_rejected(self):
        for changes in ({"public_score": float("nan")}, {"reward": float("inf")},
                        {"protected_score": True}, {"round_index": 0}, {"timestamp": datetime(2026, 1, 1)}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.result(**changes)

    def test_timestamps_are_normalized_to_utc(self):
        result = self.result(timestamp=datetime(2026, 1, 1, 3, tzinfo=timezone(timedelta(hours=3))))
        self.assertEqual(result.to_dict()["timestamp"], "2026-01-01T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
