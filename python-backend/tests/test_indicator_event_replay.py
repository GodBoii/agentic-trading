from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from pipeline.research.indicator_event_replay import replay_indicator_events


class IndicatorEventReplayTests(unittest.TestCase):
    def test_replay_is_causal_and_aggregates_events(self) -> None:
        start = datetime(2026, 8, 3, 9, 30, tzinfo=ZoneInfo("Asia/Kolkata"))
        rows = []
        cumulative_volume = 10_000.0
        for index in range(25):
            open_price = 100.0
            close_price = 100.0
            high = 100.05
            low = 99.95
            if index == 23:
                open_price, close_price, high, low = 99.8, 100.3, 100.35, 99.75
            cumulative_volume += 1_000
            rows.append(
                {
                    "security_id": 1,
                    "minute": pd.Timestamp(start + timedelta(minutes=index)),
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close_price,
                    "cumulative_volume": cumulative_volume,
                    "volume": 1_000.0,
                    "exchange_segment": "NSE_EQ",
                    "symbol": "TEST",
                    "vwap": 100.0,
                    "opening_range_high": 100.2,
                    "opening_range_low": 99.8,
                    "spread_percent": 0.02,
                    "estimated_slippage_percent": 0.02,
                    "connection_warm": True,
                    "best_bid": 99.99,
                    "best_ask": 100.01,
                    "bid_quantity_5": 1000.0,
                    "ask_quantity_5": 1000.0,
                }
            )
        report = replay_indicator_events(pd.DataFrame(rows))
        self.assertGreater(report["indicator_events_detected"], 0)
        self.assertGreater(report["aggregates_formed"], 0)
        self.assertLessEqual(report["aggregates_formed"], report["indicator_events_detected"])
        self.assertGreater(report["aggregates_passing_approximate_safety_gates"], 0)


if __name__ == "__main__":
    unittest.main()
