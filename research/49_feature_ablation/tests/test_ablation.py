import importlib
import unittest

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

m = importlib.import_module("research.49_feature_ablation.run")


class AblationTests(unittest.TestCase):
    def test_groups_add_information_without_replacing_baseline(self):
        groups = m.feature_groups({"price": ["p"], "volume_extra": ["v"],
                                  "peer_extra": ["r"], "full_extra": ["t"]})
        self.assertEqual(groups["price_vwap"], ["p"])
        self.assertEqual(groups["full_context"], ["p", "v", "r", "t"])

    def test_saved_ridge_reproduces_predictions(self):
        x = np.arange(90, dtype=float).reshape(30, 3)
        y = x[:, 0] * .1 + x[:, 2] * .2
        model = make_pipeline(StandardScaler(), Ridge(alpha=100)).fit(x, y)
        frozen = m.freeze_ridge(model, ["a", "b", "c"])
        rebuilt = ((x - frozen["mean"]) / frozen["scale"]) @ np.asarray(frozen["coefficients"]) + frozen["intercept"]
        np.testing.assert_allclose(model.predict(x), rebuilt)

    def test_test_outliers_do_not_enter_scaler(self):
        x = np.arange(60, dtype=float).reshape(30, 2)
        model = make_pipeline(StandardScaler(), Ridge(alpha=100)).fit(x, x[:, 0])
        original = model.steps[0][1].mean_.copy()
        model.predict(np.full((3, 2), 1e9))
        np.testing.assert_array_equal(model.steps[0][1].mean_, original)


if __name__ == "__main__":
    unittest.main()
