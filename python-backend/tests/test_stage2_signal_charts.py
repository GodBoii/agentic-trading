from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from pipeline.runtime.generate_stage2_signal_charts import (
    _apply_quality_selection,
    _mechanical_checks,
    _load_snapshots,
    _path_review,
)


class Stage2SignalChartTests(unittest.TestCase):
    def test_snapshot_loader_normalizes_schema_drift(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            base = {
                "security_id": [10],
                "exchange_segment": ["NSE_EQ"],
                "symbol": ["TEST"],
                "last_price": [100.0],
                "day_volume": [1000.0],
                "vwap": [99.8],
                "opening_range_high": [101.0],
                "opening_range_low": [98.0],
                "relative_volume": [1.1],
                "depth_imbalance": [0.1],
            }
            pd.DataFrame(
                {
                    **base,
                    "received_at": ["2026-08-03T10:00:00+05:30"],
                    "spread_percent": [None],
                }
            ).to_parquet(root / "null-spread.parquet", index=False)
            pd.DataFrame(
                {
                    **base,
                    "received_at": ["2026-08-03T10:00:01+05:30"],
                    "spread_percent": [0.02],
                }
            ).to_parquet(root / "float-spread.parquet", index=False)
            loaded = _load_snapshots(root, {10})
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded["security_id"].tolist(), [10, 10])

    def test_quality_selection_uses_replayed_entry_and_score(self) -> None:
        event = {
            "event_id": "selected-event",
            "setup_score": 78.0,
            "price": 100.0,
            "five_level_depth_summary": {},
        }
        rows = {
            "selected-event": {
                "entry_time": "2026-08-03T10:05:03+05:30",
                "entry_price": 100.2,
                "quality_score": 69.0,
                "spread_percent": 0.02,
                "estimated_slippage_percent": 0.01,
                "depth_imbalance": 0.15,
                "order_count_imbalance": 0.10,
            }
        }
        selected = _apply_quality_selection([event, dict(event)], rows)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["_raw_setup_score"], 78.0)
        self.assertEqual(selected[0]["setup_score"], 69.0)
        self.assertEqual(selected[0]["price"], 100.2)

    def test_long_orb_rule_check_accepts_confirmed_break(self) -> None:
        timestamp = pd.Timestamp("2026-08-03T10:00:00+05:30")
        event = {
            "price": 100.10,
            "direction": "LONG",
            "setup_type": "ORB",
            "opening_range": {"high": 100.0, "low": 98.0},
            "_event_time": timestamp,
        }
        tape = pd.Series({"received_at": timestamp, "last_price": 100.10})
        valid, failures = _mechanical_checks(event, tape)
        self.assertTrue(valid)
        self.assertEqual(failures, [])

    def test_short_vwap_rule_check_rejects_wrong_side(self) -> None:
        timestamp = pd.Timestamp("2026-08-03T10:00:00+05:30")
        event = {
            "price": 100.10,
            "direction": "SHORT",
            "setup_type": "VWAP_RECLAIM_PULLBACK",
            "vwap": 100.0,
            "_event_time": timestamp,
        }
        tape = pd.Series({"received_at": timestamp, "last_price": 100.10})
        valid, failures = _mechanical_checks(event, tape)
        self.assertFalse(valid)
        self.assertIn("short_not_below_vwap", failures)

    def test_path_review_records_target_before_stop(self) -> None:
        start = pd.Timestamp("2026-08-03T10:00:00+05:30")
        frame = pd.DataFrame(
            {
                "received_at": [start, start + pd.Timedelta(seconds=10), start + pd.Timedelta(seconds=20)],
                "last_price": [100.0, 100.25, 99.70],
            }
        )
        result = _path_review(frame, start, 100.0, "LONG", 5)
        self.assertEqual(result["first_touch"], "TARGET_FIRST")
        self.assertEqual(result["mfe"], 0.25)
        self.assertEqual(result["mae"], -0.3)


if __name__ == "__main__":
    unittest.main()
