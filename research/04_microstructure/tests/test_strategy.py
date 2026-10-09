import importlib
import unittest
from dataclasses import replace

from research.intraday_lab.domain import PolicyConfig, Tick, Side

s = importlib.import_module("research.04_microstructure.strategy")


def tick(second=0, **changes):
    base = Tick(1_000_000_000 + second * 1_000_000, 1, "A", 99.99, 100.01,
                100, 100, 900, 100, 0, True, True)
    return replace(base, **changes)


class SnapshotTests(unittest.TestCase):
    def test_aggregate_math_and_symmetric_price(self):
        self.assertAlmostEqual(s.aggregate_imbalance(tick()), .8)
        self.assertAlmostEqual(s.aggregate_weighted_quote(tick()), 100.008)
        self.assertEqual(s.aggregate_weighted_quote(tick(bid_quantity_5=100)), 100)
        self.assertAlmostEqual(s.normalized_depth_change(tick(), tick(bid_quantity_5=1000)), .1)

    def test_persistence_rejects_momentary_spike(self):
        p = s.MicrostructurePolicy(PolicyConfig(), s.MicrostructureConfig())
        for second in range(31):
            signal, reason = p.on_tick(tick(second, bid_quantity_5=100 if second == 15 else 900))
        self.assertIsNone(signal)
        self.assertEqual(reason, "imbalance_not_persistent")

    def test_causal_persistent_signal(self):
        p = s.MicrostructurePolicy(PolicyConfig(), s.MicrostructureConfig())
        outputs = [p.on_tick(tick(second)) for second in range(31)]
        self.assertTrue(all(item[0] is None for item in outputs[:-1]))
        self.assertEqual(outputs[-1][0].side, Side.LONG)

    def test_missing_freshness_and_gap_reset(self):
        p = s.MicrostructurePolicy(PolicyConfig(), s.MicrostructureConfig())
        p.on_tick(tick())
        self.assertEqual(p.on_tick(tick(1, data_fresh=None))[1], "unusable_observation")
        self.assertEqual(p.on_tick(tick(100))[1], "warming_history")

    def test_instruments_do_not_share_history(self):
        p = s.MicrostructurePolicy(PolicyConfig(), s.MicrostructureConfig())
        for second in range(31):
            p.on_tick(tick(second))
        self.assertEqual(p.on_tick(tick(31, security_id=2))[1], "warming_history")


if __name__ == "__main__":
    unittest.main()
