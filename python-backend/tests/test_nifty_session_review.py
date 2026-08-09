from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from pipeline.runtime.generate_nifty_session_review import (
    _load_large_order_activity,
    _minute_market,
)


class NiftySessionReviewTests(unittest.TestCase):
    def test_minute_market_uses_cumulative_volume_difference(self) -> None:
        timestamps = pd.to_datetime(
            ["2026-08-03T09:15:05+05:30", "2026-08-03T09:16:05+05:30"]
        )
        frame = pd.DataFrame(
            {
                "timestamp": timestamps,
                "price": [24600.0, 24605.0],
                "average_price": [24600.0, 24602.0],
                "volume": [1000.0, 1300.0],
                "open_interest": [5000.0, 5100.0],
                "best_bid": [24599.0, 24604.0],
                "best_ask": [24601.0, 24606.0],
                "spread_bps": [0.8, 0.8],
                "buy_quantity": [200.0, 300.0],
                "sell_quantity": [100.0, 200.0],
            }
        )
        minute = _minute_market(frame)
        self.assertEqual(float(minute["minute_volume"].iloc[1]), 300.0)
        self.assertEqual(float(minute["oi_change"].iloc[1]), 100.0)

    def test_large_order_lifetime_matching(self) -> None:
        appeared = {
            "side": "bid",
            "price": 24600,
            "type": "large_order_appeared",
            "captured_at_utc": "2026-08-03T03:45:00+00:00",
        }
        removed = {
            "side": "bid",
            "price": 24600,
            "type": "large_order_removed",
            "captured_at_utc": "2026-08-03T03:45:02+00:00",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.ndjson"
            path.write_text(
                json.dumps(appeared) + "\n" + json.dumps(removed) + "\n",
                encoding="utf-8",
            )
            activity, lifetimes, counts = _load_large_order_activity(path)
        self.assertEqual(len(activity), 2)
        self.assertEqual(lifetimes.tolist(), [2.0])
        self.assertEqual(counts["matched_lifetimes"], 1)


if __name__ == "__main__":
    unittest.main()
