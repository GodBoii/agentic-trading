"""Closed-pattern causality and Wilder update behavior."""

from dataclasses import replace
from datetime import datetime
from importlib import import_module
import unittest

from research.intraday_lab.domain import Side, Tick

strategy = import_module("research.07_indicator_patterns.strategy")
BASE = int(datetime.fromisoformat("2026-08-19T10:00:00+05:30").timestamp() * 1_000_000)


def tick(second: int, price: float = 100.0, **changes) -> Tick:
    return replace(Tick(BASE + second * 1_000_000, 1, "TEST", price - .005,
                        price + .005, price, 100.0, 10_000, 10_000, 0, True, True), **changes)


class IndicatorTests(unittest.TestCase):
    def test_wilder_uses_seed_average_then_recursive_update(self):
        indicator = strategy.WilderRSI(3)
        outputs = [indicator.update(x) for x in [100, 101, 102, 101, 103]]
        self.assertEqual(outputs[:3], [None, None, None])
        self.assertAlmostEqual(outputs[3], 200 / 3)
        self.assertAlmostEqual(outputs[4], 250 / 3)

    def test_flat_price_is_neutral(self):
        indicator = strategy.WilderRSI()
        for _ in range(15):
            result = indicator.update(100)
        self.assertEqual(result, 50)

    def test_wick_is_evaluated_after_minute_closes(self):
        policy = strategy.IndicatorPolicy(strategy.configuration("wick_rejection"))
        for second in range(20 * 60):
            policy.on_tick(tick(second))
        for offset in range(60):
            price = 99.8 if offset == 20 else 100.01 if offset == 59 else 100.0
            signal, _ = policy.on_tick(tick(1200 + offset, price))
            self.assertIsNone(signal)
        signal, reason = policy.on_tick(tick(1260, 100.02))
        self.assertEqual(reason, "signal")
        self.assertEqual(signal.side, Side.LONG)
        self.assertEqual(signal.reference_midpoint, 100.02)

    def test_gap_resets_rsi_instead_of_bridging_missing_minutes(self):
        policy = strategy.IndicatorPolicy(strategy.configuration("rsi_recross"))
        for second in range(16 * 60):
            policy.on_tick(tick(second, 100 + second / 10000))
        self.assertIn(1, policy.rsi)
        policy.on_tick(tick(1000))
        self.assertNotIn(1, policy.rsi)
        self.assertNotIn(1, policy.previous_rsi)

    def test_unusable_quote_resets_rsi_and_history(self):
        policy = strategy.IndicatorPolicy(strategy.configuration("rsi_recross"))
        for second in range(16 * 60):
            policy.on_tick(tick(second))
        signal, reason = policy.on_tick(tick(960, data_fresh=False))
        self.assertIsNone(signal)
        self.assertEqual(reason, "unusable_observation")
        self.assertEqual(len(policy.bars.history[1]), 0)
        self.assertNotIn(1, policy.rsi)

    def test_bollinger_breakout_uses_prior_window(self):
        policy = strategy.IndicatorPolicy(strategy.configuration("bollinger_breakout"))
        for second in range(20 * 60):
            price = 100 + (.03 if second // 60 % 2 else -.03)
            policy.on_tick(tick(second, price))
        for offset in range(60):
            policy.on_tick(tick(1200 + offset, 100.2))
        signal, reason = policy.on_tick(tick(1260, 100.21))
        self.assertEqual(reason, "signal")
        self.assertEqual(signal.side, Side.LONG)


if __name__ == "__main__":
    unittest.main()
