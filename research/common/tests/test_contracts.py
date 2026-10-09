from dataclasses import replace
import importlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research.intraday_lab.domain import PolicyConfig, Side, Signal
from research.intraday_lab.tests.test_lab import tick
from research.common.runner import CheckedPolicy

PeerResidualPolicy = importlib.import_module("research.05_relative_value.strategy").PeerResidualPolicy
VarianceRatioPolicy = importlib.import_module("research.09_variance_ratio.strategy").VarianceRatioPolicy
variance_ratio = importlib.import_module("research.09_variance_ratio.strategy").variance_ratio


class ContractTests(unittest.TestCase):
    def test_future_signal_timestamp_is_rejected(self):
        class Bad:
            def on_tick(self, t):
                return Signal(t.at_us + 1, t.security_id, Side.LONG, t.midpoint, 1, 1), "signal"
        with self.assertRaises(ValueError):
            CheckedPolicy(Bad()).on_tick(tick(0))

    def test_wrong_instrument_signal_is_rejected(self):
        class Bad:
            def on_tick(self, t):
                return Signal(t.at_us, 99, Side.LONG, t.midpoint, 1, 1), "signal"
        with self.assertRaises(ValueError):
            CheckedPolicy(Bad()).on_tick(tick(0))

    def test_peers_are_required_before_residual_trade(self):
        p = PeerResidualPolicy(PolicyConfig(), minimum_peers=2)
        outputs = [p.on_tick(tick(i, 100 + .01 * i)) for i in range(301)]
        self.assertFalse(any(signal for signal, _ in outputs))
        self.assertIn("insufficient_fresh_peers", [reason for _, reason in outputs])

    def test_future_peer_cannot_change_previous_decision(self):
        p = PeerResidualPolicy(PolicyConfig(), minimum_peers=1)
        q = PeerResidualPolicy(PolicyConfig(), minimum_peers=1)
        prior_p = [p.on_tick(tick(i, 100 + .01 * i)) for i in range(301)]
        prior_q = [q.on_tick(tick(i, 100 + .01 * i)) for i in range(301)]
        p.on_tick(tick(301, 150, sid=2))
        q.on_tick(tick(301, 50, sid=2))
        self.assertEqual(prior_p, prior_q)

    def test_residual_directions_are_opposite(self):
        cfg = replace(PolicyConfig(), maximum_move_bps=1000)
        a = PeerResidualPolicy(cfg, minimum_peers=1)
        b = PeerResidualPolicy(cfg, minimum_peers=1, direction="reversal")
        final = []
        for i in range(301):
            for sid, slope in ((2, .001), (1, .01)):
                ta = a.on_tick(tick(i, 100 + slope * i, sid=sid))
                tb = b.on_tick(tick(i, 100 + slope * i, sid=sid))
                if ta[0] is not None and tb[0] is not None:
                    final.append((ta[0].side, tb[0].side))
        self.assertTrue(final)
        self.assertTrue(all(x is not y for x, y in final))

    def test_vr_alternating_returns_have_small_two_step_variance(self):
        self.assertAlmostEqual(variance_ratio([.01, -.01] * 15, 2), 0)

    def test_vr_zero_variance_stays_unknown(self):
        self.assertIsNone(variance_ratio([0.0] * 30, 2))

    def test_vr_invalid_small_window_rejected(self):
        with self.assertRaises(ValueError):
            variance_ratio([.1, -.1], 5)

    def test_variance_policy_does_not_fill_missing_minutes(self):
        p = VarianceRatioPolicy(PolicyConfig())
        p.on_tick(tick(0))
        signal, reason = p.on_tick(tick(180, 110))
        self.assertIsNone(signal)
        self.assertEqual(reason, "collecting_minute")


if __name__ == "__main__":
    unittest.main()
