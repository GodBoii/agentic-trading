from dataclasses import replace
from datetime import datetime
from importlib import import_module
import unittest

from research.intraday_lab.domain import PolicyConfig, Side, Tick

OpeningRangePolicy = import_module("research.02_opening_range.strategy").OpeningRangePolicy
BASE = int(datetime.fromisoformat("2026-08-19T09:15:00+05:30").timestamp() * 1_000_000)


def tick(seconds, price=100, **changes):
    return replace(Tick(BASE + seconds * 1_000_000, 1, "TEST", price-.01, price+.01,
                        price, 100, 10000, 10000, 0, True, True), **changes)


def formed(policy):
    for second in range(0, 900, 10):
        policy.on_tick(tick(second, 100 + .01 * (second % 30 == 10)))


class OpeningTests(unittest.TestCase):
    def test_no_entry_before_opening_range_complete(self):
        policy = OpeningRangePolicy(PolicyConfig())
        for second in range(0, 900, 10):
            self.assertIsNone(policy.on_tick(tick(second, 100 + second / 10000))[0])

    def test_breakout_uses_frozen_range_and_only_one_signal(self):
        policy = OpeningRangePolicy(PolicyConfig())
        formed(policy)
        signal, _ = policy.on_tick(tick(900, 100.1))
        self.assertEqual(signal.side, Side.LONG)
        self.assertAlmostEqual(policy.states[1].high, 100.01)
        self.assertIsNone(policy.on_tick(tick(910, 100.2))[0])

    def test_late_start_cannot_fabricate_opening_range(self):
        policy = OpeningRangePolicy(PolicyConfig())
        for second in range(120, 920, 10):
            signal, reason = policy.on_tick(tick(second, 101))
            self.assertIsNone(signal)
            self.assertEqual(reason, "incomplete_opening_range")

    def test_gap_invalidates_range(self):
        policy = OpeningRangePolicy(PolicyConfig())
        policy.on_tick(tick(0))
        policy.on_tick(tick(40))
        self.assertIsNone(policy.on_tick(tick(900, 101))[0])

    def test_short_breakout(self):
        policy = OpeningRangePolicy(PolicyConfig())
        formed(policy)
        self.assertEqual(policy.on_tick(tick(900, 99.9))[0].side, Side.SHORT)

    def test_unknown_vwap_does_not_pass_filter(self):
        policy = OpeningRangePolicy(PolicyConfig(), require_vwap=True)
        formed(policy)
        self.assertEqual(policy.on_tick(tick(900, 100.1, vwap=None))[1], "vwap_unknown")

    def test_invalid_observation_invalidates_opening_range(self):
        policy = OpeningRangePolicy(PolicyConfig())
        policy.on_tick(tick(0))
        policy.on_tick(tick(10, data_fresh=None))
        self.assertIsNone(policy.on_tick(tick(900, 101))[0])

    def test_direction_filter_blocks_opposite_breakout(self):
        policy = OpeningRangePolicy(PolicyConfig(), require_direction=True)
        for second in range(0, 900, 10):
            policy.on_tick(tick(second, 100 + second/100000))
        self.assertEqual(policy.on_tick(tick(900, 99.9))[1], "opening_direction")

    def test_out_of_order_after_range_is_rejected(self):
        policy = OpeningRangePolicy(PolicyConfig())
        formed(policy)
        policy.on_tick(tick(910, 100))
        with self.assertRaises(ValueError):
            policy.on_tick(tick(905, 100))

    def test_wide_spread_blocks_breakout(self):
        policy = OpeningRangePolicy(PolicyConfig())
        formed(policy)
        self.assertEqual(policy.on_tick(tick(900, 100.1, bid=100, ask=100.2))[1], "spread")


if __name__ == "__main__":
    unittest.main()
