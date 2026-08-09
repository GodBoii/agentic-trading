from __future__ import annotations

import unittest

import pandas as pd

from pipeline.research.stage2_quality_replay import (
    QualityPolicy,
    _nearest_index,
    _path_outcome,
    _score_features,
    _usable_atr,
    apply_policy,
    build_minute_bars,
)


class Stage2QualityReplayTests(unittest.TestCase):
    def test_zero_atr_uses_positive_price_based_floor(self) -> None:
        self.assertAlmostEqual(_usable_atr(0.0, 250.0), 0.25)

    def test_quality_score_prefers_fresh_pullback_over_extended_chase(self) -> None:
        features = {
            "confirmation_holds": True,
            "break_extension_atr": 0.08,
            "room_atr": 1.0,
            "trend_move_atr": -0.6,
            "strong_close": True,
            "directional_candle": True,
            "directional_engulfing": False,
            "directional_rejection": True,
            "doji": False,
            "relative_volume": 1.1,
            "volume_acceleration": 2.0,
            "depth_mean_60s": 0.15,
            "depth_direction_persistence_60s": 0.65,
            "spread_percent": 0.015,
            "estimated_slippage_percent": 0.01,
        }
        fresh, _, _ = _score_features(features, 1)
        chased, _, _ = _score_features(
            {
                **features,
                "break_extension_atr": 1.2,
                "trend_move_atr": 1.8,
                "relative_volume": 3.5,
                "depth_mean_60s": 0.8,
                "spread_percent": 0.08,
                "estimated_slippage_percent": 0.08,
            },
            1,
        )
        self.assertGreater(fresh, chased)

    def test_timestamp_search_preserves_microsecond_resolution(self) -> None:
        times = pd.date_range(
            "2026-07-31T10:13:45+05:30", periods=120, freq="s"
        ).as_unit("us")
        target = pd.Timestamp("2026-07-31T10:15:00+05:30")
        self.assertEqual(_nearest_index(times, target), 75)

    def test_minute_features_use_only_present_and_previous_bars(self) -> None:
        timestamps = pd.date_range("2026-08-03T09:15:00+05:30", periods=30, freq="min")
        tape = pd.DataFrame(
            {
                "received_at": timestamps,
                "last_price": [100 + index * 0.1 for index in range(30)],
                "day_volume": [1000 + index * 100 for index in range(30)],
                "vwap": [100 + index * 0.04 for index in range(30)],
                "opening_range_high": [101.5] * 30,
                "opening_range_low": [99.5] * 30,
            }
        )
        first = build_minute_bars(tape.iloc[:20]).iloc[-1]
        extended = build_minute_bars(tape).loc[timestamps[19]]
        self.assertAlmostEqual(float(first["ema9"]), float(extended["ema9"]), places=10)
        self.assertAlmostEqual(float(first["rsi14"]), float(extended["rsi14"]), places=10)

    def test_path_outcome_honors_first_touch_sequence(self) -> None:
        start = pd.Timestamp("2026-08-03T10:00:00+05:30")
        tape = pd.DataFrame(
            {
                "received_at": [start, start + pd.Timedelta(seconds=10), start + pd.Timedelta(seconds=20)],
                "last_price": [100.0, 100.25, 99.70],
            }
        )
        result = _path_outcome(tape, 0, 1, QualityPolicy())
        self.assertEqual(result["outcome"], "TARGET_FIRST")

    def test_policy_cooldown_prevents_repeated_event(self) -> None:
        base = {
            "market_date": "2026-08-03",
            "security_id": 1,
            "setup_type": "ORB",
            "direction": "LONG",
            "confirmation_holds": True,
            "confirmation_gap_seconds": 1.0,
            "spread_percent": 0.03,
            "estimated_slippage_percent": 0.01,
            "room_atr": 1.2,
            "break_extension_atr": 0.1,
            "vwap_extension_atr": 0.5,
            "directional_evidence": 4,
            "quality_score": 80.0,
        }
        frame = pd.DataFrame(
            [
                {**base, "event_id": "a", "entry_time": "2026-08-03T10:00:00+05:30"},
                {**base, "event_id": "b", "entry_time": "2026-08-03T10:05:00+05:30"},
            ]
        )
        evaluated = apply_policy(frame, QualityPolicy())
        self.assertEqual(evaluated["selected"].tolist(), [True, False])
        self.assertIn("COOLDOWN", evaluated.iloc[1]["gate_failures"])


if __name__ == "__main__":
    unittest.main()
