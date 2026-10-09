"""Supplemental row identity alignment and frozen-value restoration checks."""

from dataclasses import asdict, replace
from importlib import import_module
import unittest

import numpy as np

from research.common.data import DEVELOPMENT
from research.intraday_lab.domain import PolicyConfig, Tick

s = import_module("research.42_weighted_ensemble.strategy")
a = import_module("research.42_weighted_ensemble.supplemental_audit")


class SupplementalTests(unittest.TestCase):
    def test_recovered_rows_match_original_labels_and_later_fill_times(self):
        ticks = [Tick(1_000_000_000 + i * 1_000_000, 1, "A", 99.99, 100.01,
                      100., 100., 1000., 1000., 0., True, True) for i in range(240)]
        x, y, _ = s.executable_labels(ticks, PolicyConfig())
        recovered, identities = a.interval_identities(ticks, PolicyConfig())
        np.testing.assert_array_equal(x, recovered)
        self.assertEqual(len(y), len(identities))
        self.assertGreater(len(identities), 0)
        self.assertTrue(all(row["decision_us"] < row["label_entry_us"] < row["label_exit_us"] for row in identities))
        ticks[100] = replace(ticks[100], data_fresh=None)
        x, _, _ = s.executable_labels(ticks, PolicyConfig())
        recovered, _ = a.interval_identities(ticks, PolicyConfig())
        np.testing.assert_array_equal(x, recovered)

    def test_restore_preserves_fitted_parameters_and_predictions(self):
        generator = np.random.default_rng(12)
        x, stack = generator.normal(size=(150, 5)), generator.normal(size=(150, 5))
        y, stack_y = generator.normal(size=(150, 2)), generator.normal(size=(150, 2))
        model = s.fit_ensemble(x, y, stack, stack_y, DEVELOPMENT, "receipt_proxy")
        restored = a.restore_model(asdict(model))
        self.assertEqual(model, restored)
        for variant in s.VARIANTS:
            np.testing.assert_array_equal(model.predict(stack, variant), restored.predict(stack, variant))
        self.assertIsNone(a.restore_model(None))

    def test_feature_hash_changes_when_a_value_changes(self):
        left, right = np.zeros(5), np.zeros(5)
        right[3] = .1
        self.assertEqual(a.feature_hash(left), a.feature_hash(left.copy()))
        self.assertNotEqual(a.feature_hash(left), a.feature_hash(right))


if __name__ == "__main__":
    unittest.main()
