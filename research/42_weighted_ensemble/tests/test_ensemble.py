"""Behavioral checks for chronology, normalization and constrained combination."""

from dataclasses import FrozenInstanceError, replace
from importlib import import_module
import unittest

import numpy as np

from research.common.data import DEVELOPMENT
from research.intraday_lab.domain import PolicyConfig, Tick

s = import_module("research.42_weighted_ensemble.strategy")
r = import_module("research.42_weighted_ensemble.run")


class EnsembleTests(unittest.TestCase):
    def setUp(self):
        random = np.random.default_rng(19)
        self.x = random.normal(size=(220, 5))
        self.y = np.column_stack([4 * self.x[:, 0] - 3, -4 * self.x[:, 0] - 3])
        self.stack_x = random.normal(size=(150, 5))
        self.stack_y = np.column_stack([4 * self.stack_x[:, 0] - 3, -4 * self.stack_x[:, 0] - 3])

    def test_weights_choose_independently_predictive_specialist(self):
        model = s.fit_ensemble(self.x, self.y, self.stack_x, self.stack_y, DEVELOPMENT, "receipt_proxy")
        self.assertGreater(model.weights[0], .95)
        self.assertAlmostEqual(sum(model.weights), 1)
        self.assertTrue(all(value >= 0 for value in model.weights))
        weighted = model.predict(self.stack_x, "convex_average")
        equal = model.predict(self.stack_x, "equal_average")
        self.assertLess(np.mean((weighted - self.stack_y) ** 2), np.mean((equal - self.stack_y) ** 2))

    def test_identical_forecasts_give_uniform_weights(self):
        predictions = np.ones((150, 4, 2))
        weights = s.convex_weights(predictions, np.zeros((150, 2)))
        np.testing.assert_allclose(weights, [.25] * 4, atol=1e-10)

    def test_stack_period_cannot_change_base_normalization_or_coefficients(self):
        first = s.fit_ensemble(self.x, self.y, self.stack_x, self.stack_y, DEVELOPMENT, "receipt_proxy")
        shifted = s.fit_ensemble(self.x, self.y, self.stack_x + 1_000, -self.stack_y, DEVELOPMENT, "receipt_proxy")
        self.assertEqual(first.specialists, shifted.specialists)
        self.assertEqual(first.joint, shifted.joint)
        self.assertEqual(first.constant_net, shifted.constant_net)
        np.testing.assert_allclose(first.specialists[0].mean, self.x[:, (0, 1)].mean(axis=0))
        self.assertNotEqual(first.weights, shifted.weights)

    def test_equal_forecast_is_actual_arithmetic_mean(self):
        model = s.fit_ensemble(self.x, self.y, self.stack_x, self.stack_y, DEVELOPMENT, "receipt_proxy")
        raw = np.stack([model.predict(self.stack_x, name) for name in s.SPECIALISTS])
        np.testing.assert_allclose(model.predict(self.stack_x, "equal_average"), raw.mean(axis=0))
        with self.assertRaises(FrozenInstanceError):
            model.weights = (1., 0., 0., 0.)

    def test_insufficient_data_or_nonfinite_values_never_fit(self):
        self.assertIsNone(s.fit_ensemble(self.x[:99], self.y[:99], self.stack_x, self.stack_y,
                                        DEVELOPMENT, "recent_trade"))
        self.assertIsNone(s.fit_ensemble(self.x, self.y, self.stack_x[:99], self.stack_y[:99],
                                        DEVELOPMENT, "receipt_proxy"))
        bad = self.x.copy()
        bad[0, 0] = np.nan
        with self.assertRaises(ValueError):
            s.fit_ensemble(bad, self.y, self.stack_x, self.stack_y, DEVELOPMENT, "receipt_proxy")

    def test_replay_rejects_training_date_and_mismatched_freshness(self):
        model = s.fit_ensemble(self.x, self.y, self.stack_x, self.stack_y, DEVELOPMENT, "receipt_proxy")
        config = replace(PolicyConfig(), name="equal_average", freshness_mode="receipt_proxy")
        policy = s.EnsemblePolicy(config, model, DEVELOPMENT)
        timestamp = int(np.datetime64("2026-08-21T06:00:00", "s").astype(int)) * 1_000_000
        tick = Tick(timestamp, 1, "A", 99.99, 100.01, 100., 100., 1000., 1000., 0., True, True)
        with self.assertRaisesRegex(ValueError, "follow every training date"):
            policy.on_tick(tick)
        with self.assertRaises(ValueError):
            s.EnsemblePolicy(replace(config, freshness_mode="recent_trade"), model, DEVELOPMENT)

    def test_future_suffix_cannot_change_prefix_predictions(self):
        model = s.fit_ensemble(self.x, self.y, self.stack_x, self.stack_y, DEVELOPMENT, "receipt_proxy")
        config = replace(PolicyConfig(), name="convex_average", freshness_mode="receipt_proxy")
        first, second = s.EnsemblePolicy(config, model, DEVELOPMENT), s.EnsemblePolicy(config, model, DEVELOPMENT)
        start = int(np.datetime64("2026-08-24T06:00:00", "s").astype(int)) * 1_000_000
        prefix = [Tick(start + i * 1_000_000, 1, "A", 100 + i * .001 - .01,
                       100 + i * .001 + .01, 100 + i * .001, 100., 1000., 1000., 0., True, True)
                  for i in range(150)]
        baseline = [first.on_tick(tick) for tick in prefix]
        extended = [second.on_tick(tick) for tick in prefix + [replace(prefix[-1], at_us=start + 150_000_000,
                                                                     bid=900, ask=900.1, last=900)]]
        self.assertEqual(baseline, extended[:len(prefix)])

    def test_directional_accuracy_is_separate_from_profit(self):
        predictions = np.array([[-3., -10.], [-4., -2.]])
        outcomes = np.array([[-2., -8.], [-9., -3.]])
        result = r.metrics(predictions, outcomes, np.array([-5., -5.]))
        self.assertEqual(result["preferred_side_accuracy"], 1)
        self.assertEqual(result["selected_label_profit_fraction"], 0)
        self.assertEqual(result["predicted_edge_ge_2bps_rows"], 0)
        self.assertIsNone(result["admitted_label_profit_fraction"])

    def test_constant_baseline_uses_same_admitted_rows(self):
        predictions = np.array([[3., -10.], [-9., -8.]])
        outcomes = np.array([[2., -12.], [-8., -10.]])
        constant = np.array([-5., -6.])
        result = r.metrics(predictions, outcomes, constant)
        expected = float(np.sqrt(np.mean((constant - outcomes[:1]) ** 2)))
        self.assertEqual(result["predicted_edge_ge_2bps_rows"], 1)
        self.assertAlmostEqual(result["admitted_training_mean_rmse_net_bps"], expected)


if __name__ == "__main__":
    unittest.main()
