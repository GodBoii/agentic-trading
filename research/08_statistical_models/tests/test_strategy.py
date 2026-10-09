import importlib
import unittest
from dataclasses import replace

import numpy as np

from research.intraday_lab.domain import Tick, PolicyConfig

s = importlib.import_module("research.08_statistical_models.strategy")


def tick(second, **changes):
    mid = 100 + .001 * second
    value = Tick(1_000_000_000 + second * 1_000_000, 1, "A", mid - .01,
                 mid + .01, mid, 100, 900, 100, 0, True, True)
    return replace(value, **changes)


class NumericalTests(unittest.TestCase):
    def test_prefix_features_do_not_use_future_prices(self):
        f1, f2 = s.CausalFeatures(PolicyConfig()), s.CausalFeatures(PolicyConfig())
        prefix = [tick(i) for i in range(121)]
        a = [f1.update(t)[0] for t in prefix]
        b = [f2.update(t)[0] for t in prefix + [tick(121, bid=900, ask=901, last=900)]]
        for left, right in zip(a, b):
            if left is None:
                self.assertIsNone(right)
            else:
                np.testing.assert_array_equal(left, right)

    def test_future_labels_include_costs_and_later_entry(self):
        ticks = [tick(i, bid=99.99, ask=100.01, last=100) for i in range(240)]
        # A favorable signal-only price must not become a same-observation fill.
        ticks[60] = replace(ticks[60], bid=89.99, ask=90.01, last=90)
        x, y, diagnostics = s.executable_labels(ticks, PolicyConfig())
        self.assertGreater(diagnostics["samples"], 0)
        self.assertTrue(np.all(y < -10))
        self.assertEqual(x.shape[1], 5)

    def test_invalid_future_quote_rejects_interval(self):
        ticks = [tick(i) for i in range(180)]
        ticks[100] = replace(ticks[100], data_fresh=None)
        x, _, diagnostics = s.executable_labels(ticks, PolicyConfig())
        self.assertEqual(len(x), 0)
        self.assertGreater(diagnostics["rejected_future_intervals"], 0)

    def test_fit_is_deterministic_and_coefficients_frozen(self):
        random = np.random.default_rng(3)
        x = random.normal(size=(200, 5))
        y = np.column_stack([3 * x[:, 0] - 2, -3 * x[:, 0] - 2])
        a, b = s.fit_model(x, y), s.fit_model(x, y)
        self.assertEqual(a.payload(), b.payload())
        self.assertLess(abs(a.predictions(np.array([1., 0, 0, 0, 0]))[0][0] - 1), .1)
        with self.assertRaises(ValueError):
            a.ridge[0, 0] = 100

    def test_missing_training_and_invalid_shape(self):
        self.assertIsNone(s.fit_model(np.zeros((3, 5)), np.zeros((3, 2))))
        with self.assertRaises(ValueError):
            s.fit_model(np.zeros((3, 4)), np.zeros((3, 2)))

    def test_no_model_cannot_emit_signal(self):
        policy = s.StatisticalPolicy(PolicyConfig(), None)
        reasons = []
        for i in range(121):
            signal, reason = policy.on_tick(tick(i))
            self.assertIsNone(signal)
            reasons.append(reason)
        self.assertIn("insufficient_training_data", reasons)


if __name__ == "__main__":
    unittest.main()
