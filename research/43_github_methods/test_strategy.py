"""Causal timing, resets, uncertainty arithmetic and agreement behavior."""

from dataclasses import replace
from datetime import datetime
from importlib import import_module
from math import exp
import unittest

import numpy as np

from research.intraday_lab.domain import PolicyConfig, Tick

module = import_module("research.43_github_methods.strategy")
BASE = int(datetime.fromisoformat("2026-08-19T09:15:00+05:30").timestamp() * 1_000_000)


def tick(second: int, price: float = 100.0, **changes) -> Tick:
    return replace(Tick(BASE + second * 1_000_000, 1, "TEST", price - .005,
                        price + .005, price, None, 10000, 10000, 0, True, True), **changes)


def policy(name: str = "kalman_trend", mode: str = "recent_trade"):
    return module.GithubMethodsPolicy(PolicyConfig(name=name, freshness_mode=mode))


class ModelTests(unittest.TestCase):
    def test_kalman_first_step_matches_independent_matrix_equations(self):
        model = module.LocalLinearKalman()
        slope, _ = model.update(10)
        prior = np.asarray([[29.25, 4], [4, 4.04]])
        gain = np.asarray([29.25, 4]) / 38.25
        expected_covariance = prior - np.outer(gain, prior[0])
        np.testing.assert_allclose(model.mean, gain * 10)
        np.testing.assert_allclose(model.covariance, expected_covariance)
        self.assertAlmostEqual(slope, 40 / 38.25)

    def test_kalman_covariance_stays_positive_and_symmetric(self):
        model = module.LocalLinearKalman()
        for value in range(300):
            model.update(value * 2 + value % 3)
            np.testing.assert_allclose(model.covariance, model.covariance.T, atol=1e-12)
            self.assertGreater(float(np.linalg.eigvalsh(model.covariance).min()), 0)
        self.assertAlmostEqual(float(model.mean[1]), 2, delta=.3)

    def test_nonfinite_observation_rejected_before_mutation(self):
        model = module.LocalLinearKalman()
        with self.assertRaises(ValueError):
            model.update(float("nan"))
        np.testing.assert_array_equal(model.mean, [0, 0])

    def test_cusum_strict_crossing_and_triggered_side_reset(self):
        model = module.SymmetricCusum()
        self.assertEqual(model.update(15), 0)
        self.assertEqual(model.update(1), 1)
        self.assertEqual(model.positive, 0)
        self.assertEqual(model.update(-15), 0)
        self.assertEqual(model.update(-1), -1)
        self.assertEqual(model.negative, 0)

    def test_cusum_reversals_do_not_add_absolute_path(self):
        model = module.SymmetricCusum()
        self.assertEqual([model.update(x) for x in [8, -8, 8, -8]], [0, 0, 0, 0])

    def test_agreement_requires_both_and_same_direction(self):
        rule = module.decision
        self.assertEqual(rule("kalman_trend", 4, 1, 20, 0), 1)
        self.assertEqual(rule("cusum_continuation", 0, 1, 0, -1), -1)
        self.assertEqual(rule("kalman_cusum_agreement", 4, 1, 20, 1), 1)
        self.assertEqual(rule("kalman_cusum_agreement", 4, 1, 20, -1), 0)
        self.assertEqual(rule("kalman_cusum_agreement", 4, 1, 20, 0), 0)
        self.assertEqual(rule("kalman_cusum_agreement", -4, 1, -20, -1), -1)

    def test_uncertainty_and_overextended_moves_block_kalman(self):
        self.assertEqual(module.decision("kalman_trend", 4, 3, 20, 1), 0)
        self.assertEqual(module.decision("kalman_trend", 4, 1, 101, 1), 0)

    def test_no_model_update_until_bar_released(self):
        instance = policy()
        for second in range(0, 60, 5):
            self.assertIsNone(instance.on_tick(tick(second))[0])
        self.assertEqual(instance.states, {})
        instance.on_tick(tick(60))
        self.assertEqual(instance.states[1].count, 1)

    def test_gap_and_incomplete_bar_reset_filter(self):
        instance = policy()
        for second in range(0, 125, 5):
            instance.on_tick(tick(second))
        self.assertEqual(instance.states[1].count, 2)
        for second in range(150, 245, 5):
            instance.on_tick(tick(second))
        self.assertEqual(instance.states[1].count, 1)

    def test_unusable_quote_clears_state_and_unknown_metadata_is_gated(self):
        strict, proxy = policy(), policy(mode="receipt_proxy")
        for second in range(0, 65, 5):
            strict.on_tick(tick(second))
            proxy.on_tick(tick(second, data_fresh=None, connection_warm=None, trade_age_seconds=None))
        self.assertEqual(proxy.states[1].count, 1)
        self.assertEqual(strict.on_tick(tick(65, data_fresh=None))[1], "unusable_observation")
        self.assertEqual(strict.states, {})

    def test_prefix_outputs_cannot_change_when_future_is_appended(self):
        prefix = [tick(s, 100 * exp((s // 60) * 4 / 10000)) for s in range(0, 1805, 5)]
        later = [tick(s, 80) for s in range(1805, 2100, 5)]
        first, second = policy(), policy()
        expected = [first.on_tick(item) for item in prefix]
        actual = [second.on_tick(item) for item in prefix + later]
        self.assertEqual(expected, actual[:len(prefix)])
        self.assertTrue(any(signal is not None for signal, _ in expected))

    def test_instruments_do_not_share_filter_state(self):
        instance = policy()
        for second in range(0, 125, 5):
            instance.on_tick(tick(second))
            instance.on_tick(tick(second, price=200, security_id=2))
        self.assertEqual(instance.states[1].anchor, 100)
        self.assertEqual(instance.states[2].anchor, 200)
        self.assertIsNot(instance.states[1].kalman, instance.states[2].kalman)


if __name__ == "__main__":
    unittest.main()
