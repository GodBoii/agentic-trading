from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from pipeline.stages.trade_readiness import evaluate_trade_readiness


class TradeReadinessTests(unittest.TestCase):
    start = datetime.fromisoformat("2026-08-10T10:00:00+05:30")

    def trend_bars(self, direction: str = "LONG"):
        bars = []
        sign = 1.0 if direction == "LONG" else -1.0
        origin = 100.0 if direction == "LONG" else 110.0
        for index in range(60):
            open_price = origin + sign * index * 0.08
            close = open_price + sign * 0.06
            bars.append(
                {
                    "minute_start": (self.start + timedelta(minutes=index)).isoformat(),
                    "open": open_price,
                    "high": max(open_price, close) + 0.04,
                    "low": min(open_price, close) - 0.03,
                    "close": close,
                    "volume": 3000.0 if index >= 55 else 1000.0,
                    "vwap": 102.0 if direction == "LONG" else 108.0,
                }
            )
        return bars

    @staticmethod
    def features(price: float, direction: str = "LONG"):
        return {
            "last_price": price,
            "vwap": 102.0 if direction == "LONG" else 108.0,
            "opening_range_high": 102.0 if direction == "LONG" else 111.0,
            "opening_range_low": 99.0 if direction == "LONG" else 108.0,
            "relative_volume": 1.5,
            "volume_acceleration": 1.7,
            "last_trade_age_seconds": 3.0,
            "spread_percent": 0.03,
            "estimated_slippage_percent": 0.02,
            "depth_imbalance_median_30s": 0.30 if direction == "LONG" else -0.30,
            "depth_sample_count_30s": 20,
        }

    def test_aligned_structure_confirmation_and_participation_become_ready(self) -> None:
        bars = self.trend_bars("LONG")
        result = evaluate_trade_readiness(
            bars=bars,
            events=[
                {"event_type": "EMA_BULLISH_CROSS", "direction": "LONG"},
                {"event_type": "VOLUME_SURGE", "direction": "LONG"},
            ],
            features=self.features(bars[-1]["close"], "LONG"),
        )
        self.assertTrue(result["ready"])
        self.assertEqual(result["direction"], "LONG")
        self.assertGreaterEqual(result["score"], 75.0)
        self.assertGreater(result["direction_margin"], 10.0)

    def test_bearish_stock_arriving_at_support_is_watched_not_dispatched(self) -> None:
        bars = self.trend_bars("SHORT")
        price = bars[-1]["close"]
        result = evaluate_trade_readiness(
            bars=bars,
            events=[
                {"event_type": "EMA_BEARISH_CROSS", "direction": "SHORT"},
                {"event_type": "VOLUME_SURGE", "direction": "SHORT"},
            ],
            features=self.features(price, "SHORT"),
            stock={"historical": {"previous_close": price - 0.10}},
        )
        self.assertFalse(result["ready"])
        self.assertEqual(result["leading_direction"], "SHORT")
        self.assertIn("INSUFFICIENT_TARGET_ROOM", result["failures"])

    def test_doji_and_volume_alone_are_not_a_trade_setup(self) -> None:
        bars = self.trend_bars("LONG")
        result = evaluate_trade_readiness(
            bars=bars,
            events=[
                {"event_type": "DOJI", "direction": "NEUTRAL"},
                {"event_type": "VOLUME_SURGE", "direction": "NEUTRAL"},
            ],
            features=self.features(bars[-1]["close"], "LONG"),
        )
        self.assertFalse(result["ready"])
        self.assertIn("NO_DIRECTIONAL_CATALYST", result["failures"])

    def test_stale_last_trade_blocks_otherwise_strong_setup(self) -> None:
        bars = self.trend_bars("LONG")
        features = self.features(bars[-1]["close"], "LONG")
        features["last_trade_age_seconds"] = 180.0
        result = evaluate_trade_readiness(
            bars=bars,
            events=[{"event_type": "EMA_BULLISH_CROSS", "direction": "LONG"}],
            features=features,
            max_last_trade_age_seconds=90,
        )
        self.assertFalse(result["ready"])
        self.assertIn("LAST_TRADE_STALE", result["failures"])

    def test_candle_pattern_alone_cannot_be_the_primary_setup(self) -> None:
        bars = self.trend_bars("LONG")
        result = evaluate_trade_readiness(
            bars=bars,
            events=[{"event_type": "BULLISH_ENGULFING", "direction": "LONG"}],
            features=self.features(bars[-1]["close"], "LONG"),
        )
        self.assertFalse(result["ready"])
        self.assertIn("NO_PRIMARY_SETUP_CATALYST", result["failures"])

    def test_completed_bar_warmup_is_mandatory(self) -> None:
        bars = self.trend_bars("LONG")[:20]
        result = evaluate_trade_readiness(
            bars=bars,
            events=[{"event_type": "EMA_BULLISH_CROSS", "direction": "LONG"}],
            features=self.features(bars[-1]["close"], "LONG"),
        )
        self.assertFalse(result["ready"])
        self.assertEqual(result["failures"], ["INSUFFICIENT_COMPLETED_BARS"])


if __name__ == "__main__":
    unittest.main()
