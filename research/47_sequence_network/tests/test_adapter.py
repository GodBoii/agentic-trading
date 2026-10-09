"""Causal shared candle features and downstream account adapter behavior."""

from importlib import import_module
import unittest

import numpy as np
import pandas as pd

d = import_module("research.45_market_dataset.dataset")
a = import_module("research.45_market_dataset.account")
r = import_module("research.47_sequence_network.run")


class AdapterTests(unittest.TestCase):
    def test_shared_future_candle_mutation_cannot_change_feature_prefix(self):
        price = 100 + np.arange(375) * .001
        day = pd.DataFrame({"open": price, "high": price + .05, "low": price - .05,
                            "close": price + .01, "volume": 1000 + np.arange(375)})
        mutated = day.copy()
        mutated.loc[101:, ["open", "high", "low", "close", "volume"]] *= 100
        first, first_sequence = d.causal_day_features(day)
        second, second_sequence = d.causal_day_features(mutated)
        np.testing.assert_array_equal(first.iloc[:101].to_numpy(), second.iloc[:101].to_numpy())
        np.testing.assert_array_equal(first_sequence[:101], second_sequence[:101])

    def test_adapter_uses_later_candle_execution_and_costs(self):
        rows = pd.DataFrame({"date": ["2025-01-02"], "security_id": [1], "decision_us": [1_000_000],
                "entry_us": [61_000_000], "exit_us_15": [961_000_000], "decision_reference": [100.],
                "entry_reference": [100.], "exit_reference_15": [100.2]})
        summary, trades, daily = a.account_replay(rows, np.array([30.]), horizon=15)
        self.assertEqual(summary["trades"], 1)
        self.assertTrue((trades.decision_us < trades.entry_us).all())
        self.assertTrue((trades.entry_us < trades.exit_us).all())
        self.assertGreater(summary["fees"], 0)
        self.assertAlmostEqual(summary["gross_pnl"] - summary["fees"], summary["net_pnl"])
        self.assertEqual(len(daily), 1)

    def test_direction_accuracy_excludes_target_ties_not_losing_costs(self):
        result = r.metrics(np.array([2., -2., 0.]), np.array([1., -1., 1.]), 1)
        self.assertEqual(result["nonzero_target_rows"], 2)
        self.assertEqual(result["sign_accuracy"], 1)
        self.assertEqual(result["training_majority_sign_accuracy"], .5)


if __name__ == "__main__":
    unittest.main()
