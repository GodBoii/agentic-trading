from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from pipeline.stages.indicator_event_engine import IndicatorEventEngine


class IndicatorEventEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = IndicatorEventEngine(event_cooldown_seconds=600)
        self.state = self.engine.state_fields()
        self.start = datetime.fromisoformat("2026-08-03T10:00:00+05:30")

    def tick(self, seconds: int, price: float, volume: float = 1000.0):
        return self.engine.on_tick(
            self.state,
            timestamp=self.start + timedelta(seconds=seconds),
            price=price,
            cumulative_volume=volume,
            vwap=100.0,
            opening_range_high=101.0,
            opening_range_low=99.0,
            opening_range_complete=True,
        )

    def test_pattern_is_emitted_only_after_the_minute_closes(self) -> None:
        self.assertEqual(self.tick(0, 100.0), [])
        self.assertEqual(self.tick(20, 100.10), [])
        self.assertEqual(self.tick(50, 100.01), [])
        events = self.tick(60, 100.02, 1100.0)
        self.assertIn("DOJI", {event["event_type"] for event in events})

    def test_same_pattern_is_cooled_down(self) -> None:
        self.tick(0, 100.0)
        self.tick(20, 100.10)
        self.tick(50, 100.01)
        first = self.tick(60, 100.0, 1100.0)
        self.tick(80, 100.10, 1150.0)
        self.tick(110, 100.01, 1190.0)
        second = self.tick(120, 100.0, 1200.0)
        self.assertIn("DOJI", {event["event_type"] for event in first})
        self.assertNotIn("DOJI", {event["event_type"] for event in second})

    def test_bullish_engulfing_is_directional(self) -> None:
        self.tick(0, 100.0)
        self.tick(50, 99.0, 1050.0)
        self.tick(60, 98.8, 1100.0)
        self.tick(110, 100.2, 1180.0)
        events = self.tick(120, 100.1, 1200.0)
        engulfing = next(
            event for event in events if event["event_type"] == "BULLISH_ENGULFING"
        )
        self.assertEqual(engulfing["direction"], "LONG")

    def test_ema_cross_is_a_transition_not_a_persistent_state(self) -> None:
        events = []
        prices = [110 - index * 0.4 for index in range(25)] + [100 + index * 1.0 for index in range(15)]
        for minute, price in enumerate(prices):
            events.extend(self.tick(minute * 60, price, 1000 + minute * 100))
        events.extend(self.tick(len(prices) * 60, prices[-1], 6000.0))
        bullish = [event for event in events if event["event_type"] == "EMA_BULLISH_CROSS"]
        self.assertEqual(len(bullish), 1)

    def test_late_closed_bar_updates_state_without_emitting_stale_event(self) -> None:
        engine = IndicatorEventEngine(event_cooldown_seconds=0, max_event_lag_seconds=60)
        state = engine.state_fields()
        first = datetime.fromisoformat("2026-08-03T10:00:00+05:30")
        engine.on_closed_bar(
            state,
            bar={
                "minute_start": first.isoformat(),
                "open": 100.0,
                "high": 100.1,
                "low": 99.9,
                "close": 100.0,
                "volume": 1000.0,
                "vwap": 100.0,
            },
            detected_at=first + timedelta(minutes=1),
            opening_range_high=None,
            opening_range_low=None,
            opening_range_complete=False,
        )
        events = engine.on_closed_bar(
            state,
            bar={
                "minute_start": (first + timedelta(minutes=1)).isoformat(),
                "open": 100.2,
                "high": 101.0,
                "low": 99.8,
                "close": 100.2,
                "volume": 1000.0,
                "vwap": 100.0,
            },
            detected_at=first + timedelta(minutes=5),
            opening_range_high=None,
            opening_range_low=None,
            opening_range_complete=False,
        )
        self.assertEqual(events, [])
        self.assertEqual(len(state["minute_bars"]), 2)

    def test_volume_surge_without_decisive_candle_is_neutral(self) -> None:
        engine = IndicatorEventEngine(event_cooldown_seconds=0, volume_surge_ratio=1.8)
        state = engine.state_fields()
        for index in range(10):
            minute = self.start + timedelta(minutes=index)
            engine.on_closed_bar(
                state,
                bar={
                    "minute_start": minute.isoformat(),
                    "open": 100.0,
                    "high": 100.1,
                    "low": 99.9,
                    "close": 100.02,
                    "volume": 100.0,
                    "vwap": 100.0,
                },
                detected_at=minute + timedelta(minutes=1),
                opening_range_high=None,
                opening_range_low=None,
                opening_range_complete=False,
            )
        minute = self.start + timedelta(minutes=10)
        events = engine.on_closed_bar(
            state,
            bar={
                "minute_start": minute.isoformat(),
                "open": 100.0,
                "high": 100.2,
                "low": 99.8,
                "close": 100.02,
                "volume": 500.0,
                "vwap": 100.0,
            },
            detected_at=minute + timedelta(minutes=1),
            opening_range_high=None,
            opening_range_low=None,
            opening_range_complete=False,
        )
        surge = next(item for item in events if item["event_type"] == "VOLUME_SURGE")
        self.assertEqual(surge["direction"], "NEUTRAL")
        self.assertLess(surge["details"]["body_to_range"], 0.35)


if __name__ == "__main__":
    unittest.main()
