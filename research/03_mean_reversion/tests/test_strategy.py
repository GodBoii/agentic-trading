"""Behavior checks for causal bars, missing data, and reversal decisions."""

from dataclasses import replace
from datetime import datetime
from importlib import import_module
from math import sin
import unittest

from research.intraday_lab.domain import Side, Tick

bars_module = import_module("research.03_mean_reversion.bars")
strategy = import_module("research.03_mean_reversion.strategy")
BASE = int(datetime.fromisoformat("2026-08-19T10:00:00+05:30").timestamp() * 1_000_000)


def tick(second: int, price: float = 100.0, **changes) -> Tick:
    return replace(Tick(BASE + second * 1_000_000, 1, "TEST", price - .005,
                        price + .005, price, 100.0, 10_000, 10_000, 0, True, True), **changes)


def tape(prices: list[float]) -> list[Tick]:
    return [tick(i * 60 + second, price) for i, price in enumerate(prices) for second in range(60)]


class BarTests(unittest.TestCase):
    def test_current_minute_is_never_released_early(self):
        bars = bars_module.CompletedBars(strategy.configuration("rolling_zscore_fade"))
        for second in range(60):
            result, _ = bars.update(tick(second, 100 + second / 100))
            self.assertIsNone(result)
        closed, _ = bars.update(tick(60, 110))
        self.assertEqual(closed.close, 100.59)
        self.assertEqual(closed.high, 100.59)
        self.assertEqual(closed.observations, 60)

    def test_gap_clears_all_history_and_partial_bar(self):
        bars = bars_module.CompletedBars(strategy.configuration("rolling_zscore_fade"))
        for item in tape([100, 101]):
            bars.update(item)
        self.assertEqual(len(bars.history[1]), 1)
        self.assertIsNone(bars.update(tick(150))[0])
        self.assertEqual(len(bars.history[1]), 0)

    def test_unknown_freshness_refuses_strict_but_proxy_is_explicit(self):
        strict = bars_module.CompletedBars(strategy.configuration("rolling_zscore_fade"))
        proxy = bars_module.CompletedBars(strategy.configuration("rolling_zscore_fade", "receipt_proxy"))
        item = tick(0, data_fresh=None, connection_warm=None, trade_age_seconds=None)
        self.assertEqual(strict.update(item)[1], "unusable_observation")
        self.assertEqual(proxy.update(item)[1], "warming_bar")

    def test_duplicate_or_backward_instrument_time_is_rejected(self):
        bars = bars_module.CompletedBars(strategy.configuration("rolling_zscore_fade"))
        bars.update(tick(10))
        with self.assertRaises(ValueError):
            bars.update(tick(10))

    def test_late_first_quote_does_not_make_full_minute(self):
        bars = bars_module.CompletedBars(strategy.configuration("rolling_zscore_fade"))
        for second in range(30, 60):
            bars.update(tick(second))
        self.assertEqual(bars.update(tick(60))[1], "incomplete_bar")


class ReversionTests(unittest.TestCase):
    def test_fade_requires_turn_and_uses_only_closed_prices(self):
        prices = [100 + .02 * sin(i) for i in range(19)] + [99.5, 99.6]
        policy = strategy.ReversionPolicy(strategy.configuration("rolling_zscore_fade"))
        for item in tape(prices):
            policy.on_tick(item)
        signal, reason = policy.on_tick(tick(21 * 60, 99.61))
        self.assertEqual(reason, "signal")
        self.assertEqual(signal.side, Side.LONG)
        self.assertEqual(signal.reference_midpoint, 99.61)
        self.assertEqual(signal.at_us, BASE + 21 * 60 * 1_000_000)

    def test_missing_vwap_does_not_become_zero_or_price(self):
        policy = strategy.ReversionPolicy(strategy.configuration("vwap_deviation_turn"))
        for item in tape([100 + .02 * sin(i) for i in range(21)]):
            policy.on_tick(replace(item, vwap=None))
        self.assertEqual(policy.on_tick(tick(1260, vwap=None))[1], "vwap_unknown")

    def test_ar1_stationary_fit_and_unit_root_rejection(self):
        values = [101.0]
        for _ in range(19):
            values.append(100 + .8 * (values[-1] - 100))
        phi, center, half_life = strategy.ar1_fit(values)
        self.assertAlmostEqual(phi, .8)
        self.assertAlmostEqual(center, 100)
        self.assertGreater(half_life, 3)
        self.assertIsNone(strategy.ar1_fit([100.0] * 20))
        self.assertIsNone(strategy.ar1_fit([100 + i for i in range(20)]))

    def test_prefix_results_do_not_depend_on_future_suffix(self):
        prefix = tape([100 + .02 * sin(i) for i in range(19)] + [99.5, 99.6])
        first = strategy.ReversionPolicy(strategy.configuration("rolling_zscore_fade"))
        second = strategy.ReversionPolicy(strategy.configuration("rolling_zscore_fade"))
        observed_first = [first.on_tick(item) for item in prefix]
        observed_second = [second.on_tick(item) for item in prefix]
        for item in tape([120]):
            second.on_tick(replace(item, at_us=item.at_us + len(prefix) * 1_000_000))
        self.assertEqual(observed_first, observed_second)


if __name__ == "__main__":
    unittest.main()
