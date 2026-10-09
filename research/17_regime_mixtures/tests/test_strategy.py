"""Finite fitting, posterior normalization and causal feature/policy behavior."""

from dataclasses import replace
from datetime import datetime
from importlib import import_module
import unittest

import numpy as np

from research.intraday_lab.domain import PolicyConfig, Tick

strategy = import_module("research.17_regime_mixtures.strategy")
DATES = ("2026-08-19", "2026-08-20", "2026-08-21")
BASE = int(datetime.fromisoformat("2026-08-24T10:00:00+05:30").timestamp() * 1_000_000)


def tick(second, price=100.0, **changes):
    return replace(Tick(BASE + second * 1_000_000, 1, "TEST", price-.005, price+.005,
                        price, None, 10000, 10000, 0, True, True), **changes)


def training():
    rng = np.random.default_rng(31)
    first = rng.normal([0, 3, .15], [2, .3, .02], size=(150, 3))
    second = rng.normal([15, 2, .8], [3, .2, .02], size=(150, 3))
    return np.concatenate([first, second])


class MixtureTests(unittest.TestCase):
    def test_fit_is_finite_and_seed_repeatable(self):
        first, report = strategy.fit_features(training(), DATES, "recent_trade")
        second, _ = strategy.fit_features(training(), DATES, "recent_trade")
        self.assertEqual(first, second)
        self.assertEqual(report["status"], "fitted")
        self.assertTrue(np.isfinite(report["training_loglikelihoods"]).all())
        self.assertTrue(np.all(np.asarray(first.variances) >= .01))

    def test_probabilities_normalize_and_do_not_depend_on_future_calls(self):
        model, _ = strategy.fit_features(training(), DATES, "recent_trade")
        prefix = model.posterior(np.array([15., 2., .8]))
        model.posterior(np.array([-500., 100., .1]))
        self.assertTrue(np.allclose(prefix, model.posterior(np.array([15., 2., .8]))))
        self.assertAlmostEqual(float(prefix.sum()), 1)
        self.assertTrue(np.all(prefix >= 0))

    def test_invalid_model_variance_and_nonfinite_posterior_are_rejected(self):
        model, _ = strategy.fit_features(training(), DATES, "recent_trade")
        with self.assertRaises(ValueError):
            replace(model, variances=((0, 1, 1), (1, 1, 1)))
        with self.assertRaises(ValueError):
            model.posterior(np.array([np.nan, 1, 1]))

    def test_inadequate_or_degenerate_training_refuses_fit(self):
        self.assertIsNone(strategy.fit_features(np.zeros((199, 3)), DATES, "recent_trade")[0])
        self.assertIsNone(strategy.fit_features(np.ones((300, 3)), DATES, "recent_trade")[0])
        with self.assertRaises(ValueError):
            strategy.fit_features(np.full((300, 3), np.nan), DATES, "recent_trade")

    def test_features_release_only_after_six_completed_bars(self):
        collector = strategy.CausalFeatures(PolicyConfig())
        for second in range(360):
            self.assertIsNone(collector.on_tick(tick(second, 100 + second // 60 * .03))[0])
        feature, _, reason = collector.on_tick(tick(360, 110))
        self.assertEqual(reason, "feature")
        self.assertAlmostEqual(feature[0], np.log(100.15 / 100) * 10000)
        self.assertAlmostEqual(feature[2], 1)

    def test_gap_clears_feature_history(self):
        collector = strategy.CausalFeatures(PolicyConfig())
        for second in range(360):
            collector.on_tick(tick(second))
        self.assertIsNone(collector.on_tick(tick(390))[0])
        self.assertEqual(len(collector.bars.history[1]), 0)

    def test_strict_unknown_metadata_produces_no_training_rows(self):
        sessions = {}
        for day in DATES:
            base = int(datetime.fromisoformat(day + "T10:00:00+05:30").timestamp() * 1_000_000)
            sessions[day] = [replace(tick(second, data_fresh=None), at_us=base+second*1_000_000) for second in range(420)]
        model, report = strategy.fit_model(sessions, "recent_trade")
        self.assertIsNone(model)
        self.assertEqual(report["rows"], 0)

    def test_policy_rejects_training_date_and_no_fit_never_trades(self):
        config = replace(PolicyConfig(), name="mixture_trend_continuation")
        policy = strategy.RegimePolicy(config, None, DATES)
        self.assertEqual(policy.on_tick(tick(0))[1], "insufficient_training")
        old = int(datetime.fromisoformat(DATES[-1] + "T10:00:00+05:30").timestamp() * 1_000_000)
        with self.assertRaises(ValueError):
            policy.on_tick(replace(tick(0), at_us=old))


if __name__ == "__main__":
    unittest.main()
