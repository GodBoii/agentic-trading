import importlib
from pathlib import Path
import tempfile
import unittest

m = importlib.import_module("research.49_feature_ablation.verify")


class EvidenceTests(unittest.TestCase):
    def test_missing_prediction_or_trade_evidence_is_rejected(self):
        spec = {"horizons": [5, 15, 30], "costs_per_leg_bps": [2, 5]}
        predictions, accounts = m.expected_files(spec)
        with tempfile.TemporaryDirectory() as location:
            root = Path(location)
            for filename in predictions:
                (root / filename).touch()
            for stem in accounts:
                for prefix in ["trades", "daily"]:
                    (root / f"{prefix}-{stem}.csv").touch()
            m.require_coverage(root, spec)
            missing = root / "predictions-validation-h5.parquet"
            missing.unlink()
            with self.assertRaisesRegex(ValueError, "prediction file coverage"):
                m.require_coverage(root, spec)
            missing.touch()
            (root / f"trades-{sorted(accounts)[0]}.csv").unlink()
            with self.assertRaisesRegex(ValueError, "trades account coverage"):
                m.require_coverage(root, spec)


if __name__ == "__main__":
    unittest.main()
