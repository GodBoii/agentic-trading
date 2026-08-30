from __future__ import annotations

import time
import unittest
from datetime import datetime

from pipeline.stages.activity_ranker import ActivityRanker
from pipeline.stages.live_state import LiveStockState


class IntraFinderPerformanceTests(unittest.TestCase):
    def test_four_thousand_stock_rank_stays_bounded(self) -> None:
        now = datetime.fromisoformat("2026-08-28T10:00:00+05:30")
        now_ts = now.timestamp()
        states = {}
        for index in range(4_000):
            state = LiveStockState(
                "NSE_EQ",
                index + 1,
                f"S{index}",
                f"INE{index}",
                adv_20_cr=20.0 + index % 50,
            )
            state.latest_price = 100.0 + index % 100
            state.last_packet_at = now.isoformat()
            state.last_trade_at = now.isoformat()
            state.depth = [{} for _ in range(5)]
            state.spread_percent = 0.03
            state.previous_cumulative_volume = 10_000
            state.cumulative_volume = 10_000 + index
            state.cumulative_value = 2_000_000 + index * 100
            state.price_samples.extend(
                [
                    (now_ts - 300, state.latest_price * 0.995),
                    (now_ts - 60, state.latest_price * 0.998),
                    (now_ts, state.latest_price),
                ]
            )
            state.value_samples.extend(
                [
                    (now_ts - 300, state.cumulative_value - 500_000),
                    (now_ts - 30, state.cumulative_value - 100_000),
                    (now_ts, state.cumulative_value),
                ]
            )
            states[state.key] = state

        started = time.perf_counter()
        result = ActivityRanker().rank(states, now)
        duration_ms = (time.perf_counter() - started) * 1000.0

        self.assertEqual(result.eligible_count, 4_000)
        self.assertEqual(len(result.hot), 60)
        # Wide enough for shared CI, strict enough to catch accidental quadratic work.
        self.assertLess(duration_ms, 500.0)


if __name__ == "__main__":
    unittest.main()
