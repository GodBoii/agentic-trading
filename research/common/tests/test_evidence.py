"""Corruption checks against real saved experiment fixtures, read-only originals."""

import csv
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from research.common.data import ROOT
from research.common.verify_program import verify_run


class EvidenceTests(unittest.TestCase):
    def copy_run(self, destination: Path) -> Path:
        original = ROOT / "research/02_opening_range/runs/initial-v1"
        if not original.exists():
            self.skipTest("recorded run fixture is unavailable on this checkout")
        copied = destination / "run"
        shutil.copytree(original, copied)
        return copied

    def test_saved_source_change_is_detected(self):
        with TemporaryDirectory() as directory:
            run = self.copy_run(Path(directory))
            path = next((run / "source").rglob("*.py"))
            path.write_text(path.read_text() + "\n# corrupted snapshot\n")
            with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
                verify_run(run)

    def test_trade_accounting_change_is_detected(self):
        with TemporaryDirectory() as directory:
            run = self.copy_run(Path(directory))
            path = run / "trades-2026-08-19-orb15-receipt_proxy.csv"
            with path.open(newline="", encoding="utf-8") as stream:
                reader = csv.DictReader(stream)
                names = reader.fieldnames
                rows = list(reader)
            self.assertTrue(rows)
            rows[0]["net_pnl"] = str(float(rows[0]["net_pnl"]) + 10)
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=names)
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(ValueError, "Accounting mismatch"):
                verify_run(run)

    def test_fake_complete_exposure_is_detected(self):
        with TemporaryDirectory() as directory:
            run = self.copy_run(Path(directory))
            path = run / "summary-2026-08-19-orb15-receipt_proxy.json"
            payload = json.loads(path.read_text())
            payload["pending_entries"] = 1
            path.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "Unresolved exposure flag mismatch"):
                verify_run(run)


if __name__ == "__main__":
    unittest.main()
