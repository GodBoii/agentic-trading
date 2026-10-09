"""Setup sequencing, mirrored sides, expiration and data-gap behavior."""

from dataclasses import replace
from datetime import datetime
from importlib import import_module
import unittest

from research.intraday_lab.domain import Side, Tick

strategy = import_module("research.10_vwap_pullback.strategy")
BASE = int(datetime.fromisoformat("2026-08-19T10:00:00+05:30").timestamp() * 1_000_000)


def tick(second: int, price: float, vwap: float | None) -> Tick:
    return Tick(BASE + second * 1_000_000, 1, "TEST", price - .005, price + .005,
                price, vwap, 10_000, 10_000, 0, True, True)


def minute(policy, index: int, price: float, vwap: float | None) -> None:
    for second in range(60):
        policy.on_tick(tick(index * 60 + second, price, vwap))


def prime(policy, sign: int = 1) -> None:
    for i in range(6):
        minute(policy, i, 100 + sign * (.15 + i * .03), 100 + sign * i * .005)


class VWAPTests(unittest.TestCase):
    def test_reclaim_requires_separate_arm_touch_and_confirmation_bars(self):
        policy = strategy.VWAPPullbackPolicy(strategy.configuration("vwap_reclaim"))
        prime(policy)
        minute(policy, 6, 100.035, 100.03)
        self.assertEqual(policy.setups[1].stage, strategy.Stage.ARMED)
        minute(policy, 7, 100.135, 100.035)
        self.assertEqual(policy.setups[1].stage, strategy.Stage.TOUCHED)
        signal, reason = policy.on_tick(tick(480, 100.14, 100.04))
        self.assertEqual(reason, "signal")
        self.assertEqual(signal.side, Side.LONG)
        self.assertNotIn(1, policy.setups)

    def test_bounded_pullback_stays_on_trend_side(self):
        policy = strategy.VWAPPullbackPolicy(strategy.configuration("vwap_bounded_pullback"))
        prime(policy)
        minute(policy, 6, 100.08, 100.03)
        minute(policy, 7, 100.235, 100.035)
        signal, reason = policy.on_tick(tick(480, 100.24, 100.04))
        self.assertEqual(reason, "signal")
        self.assertEqual(signal.side, Side.LONG)

    def test_short_sequence_is_mirrored(self):
        policy = strategy.VWAPPullbackPolicy(strategy.configuration("vwap_reclaim"))
        prime(policy, -1)
        minute(policy, 6, 99.965, 99.97)
        minute(policy, 7, 99.865, 99.965)
        signal, reason = policy.on_tick(tick(480, 99.86, 99.96))
        self.assertEqual(reason, "signal")
        self.assertEqual(signal.side, Side.SHORT)

    def test_missing_vwap_clears_setup(self):
        policy = strategy.VWAPPullbackPolicy(strategy.configuration("vwap_reclaim"))
        prime(policy)
        minute(policy, 6, 100.3, None)
        signal, reason = policy.on_tick(tick(420, 100.31, 100.035))
        self.assertIsNone(signal)
        self.assertEqual(reason, "vwap_unknown")
        self.assertNotIn(1, policy.setups)

    def test_gap_clears_armed_setup(self):
        policy = strategy.VWAPPullbackPolicy(strategy.configuration("vwap_reclaim"))
        prime(policy)
        policy.on_tick(tick(360, 100.3, 100.03))
        self.assertIn(1, policy.setups)
        signal, _ = policy.on_tick(tick(390, 100.3, 100.03))
        self.assertIsNone(signal)
        self.assertNotIn(1, policy.setups)

    def test_setup_expires_without_rearming_in_same_bar(self):
        policy = strategy.VWAPPullbackPolicy(strategy.configuration("vwap_reclaim"))
        prime(policy)
        for i in range(6, 12):
            minute(policy, i, 100.3 + .005 * i, 100 + .005 * i)
        signal, reason = policy.on_tick(tick(720, 100.36, 100.06))
        self.assertIsNone(signal)
        self.assertEqual(reason, "setup_expired")
        self.assertNotIn(1, policy.setups)


if __name__ == "__main__":
    unittest.main()
