from dataclasses import replace
from datetime import datetime
from importlib import import_module
import unittest

from research.intraday_lab.domain import PolicyConfig, Side, Tick

CompressionPolicy = import_module("research.06_volatility_compression.strategy").CompressionPolicy
BASE = int(datetime.fromisoformat("2026-08-19T09:15:00+05:30").timestamp() * 1_000_000)


def tick(seconds, price=100, **changes):
    return replace(Tick(BASE + seconds * 1_000_000, 1, "TEST", price-.01, price+.01,
                        price, 100, 10000, 10000, 0, True, True), **changes)


def feed_minutes(policy, prices, start=0):
    outputs = []
    for minute, price in enumerate(prices, start):
        for second in range(0, 60, 10):
            result = policy.on_tick(tick(minute*60+second, price))
            if result[0] is not None:
                outputs.append(result[0])
    return outputs


class CompressionTests(unittest.TestCase):
    def test_bar_close_not_available_until_next_minute(self):
        policy = CompressionPolicy(PolicyConfig(), method="range", confirmation_bars=1)
        feed_minutes(policy, [100]*5)
        for second in range(300, 360, 10):
            self.assertIsNone(policy.on_tick(tick(second, 100.2))[0])
        self.assertEqual(policy.on_tick(tick(360, 100.2))[0].side, Side.LONG)

    def test_bollinger_needs_two_completed_breakout_closes(self):
        policy = CompressionPolicy(PolicyConfig(), method="bollinger_absolute")
        self.assertFalse(feed_minutes(policy, [100 + .002*(i%2) for i in range(20)] + [100.2]))
        self.assertFalse(feed_minutes(policy, [100.3], start=21))
        self.assertEqual(policy.on_tick(tick(22*60, 100.3))[0].side, Side.LONG)

    def test_short_compressed_range(self):
        policy = CompressionPolicy(PolicyConfig(), method="range", confirmation_bars=1)
        feed_minutes(policy, [100]*5+[99.8])
        self.assertEqual(policy.on_tick(tick(360, 99.8))[0].side, Side.SHORT)

    def test_gap_discards_previous_history(self):
        policy = CompressionPolicy(PolicyConfig(), method="range", confirmation_bars=1)
        feed_minutes(policy, [100]*6)
        self.assertEqual(policy.on_tick(tick(400, 101))[1], "warming_history")
        self.assertEqual(len(policy.states[1].closes), 0)

    def test_unknown_freshness_clears_history(self):
        policy = CompressionPolicy(PolicyConfig())
        feed_minutes(policy, [100]*20)
        self.assertEqual(policy.on_tick(tick(1200, data_fresh=None))[1], "unusable_observation")
        self.assertNotIn(1, policy.states)

    def test_reversal_during_decision_blocks_old_breakout(self):
        policy = CompressionPolicy(PolicyConfig(), method="range", confirmation_bars=1)
        feed_minutes(policy, [100]*5+[100.2])
        self.assertEqual(policy.on_tick(tick(360, 99.9))[1], "breakout_reversed_before_decision")

    def test_flat_bands_do_not_signal(self):
        policy = CompressionPolicy(PolicyConfig(), method="bollinger_absolute")
        self.assertFalse(feed_minutes(policy, [100]*30))

    def test_relative_squeeze_needs_full_prior_width_history(self):
        policy = CompressionPolicy(PolicyConfig())
        self.assertFalse(feed_minutes(policy, [100]*20+[100.2, 100.3, 100.3]))
        self.assertEqual(policy.states[1].armed, 0)

    def test_out_of_order_rejected(self):
        policy = CompressionPolicy(PolicyConfig())
        policy.on_tick(tick(10))
        with self.assertRaises(ValueError):
            policy.on_tick(tick(5))

    def test_full_relative_squeeze_then_breakout(self):
        policy = CompressionPolicy(PolicyConfig())
        self.assertFalse(feed_minutes(policy, [100]*145 + [100.2, 100.3]))
        self.assertEqual(policy.on_tick(tick(147*60, 100.3))[0].side, Side.LONG)

    def test_security_histories_are_independent(self):
        policy = CompressionPolicy(PolicyConfig(), method="range", confirmation_bars=1)
        feed_minutes(policy, [100]*6)
        signal, reason = policy.on_tick(tick(360, 100.2, security_id=2))
        self.assertIsNone(signal)
        self.assertEqual(reason, "warming_history")

    def test_proxy_does_not_override_explicit_bad_flag(self):
        policy = CompressionPolicy(PolicyConfig(freshness_mode="receipt_proxy"))
        self.assertEqual(policy.on_tick(tick(0, data_fresh=False))[1], "unusable_observation")


if __name__ == "__main__":
    unittest.main()
