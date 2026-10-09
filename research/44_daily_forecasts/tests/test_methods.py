import importlib
import unittest

import numpy as np
import pandas as pd

m = importlib.import_module("research.44_daily_forecasts.methods")


def bars() -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=60, freq="B", tz="Asia/Kolkata")
    close = 100 + np.arange(60) * 0.1
    return pd.DataFrame({"timestamp": dates.as_unit("s").astype("int64"),
        "datetime_ist": dates.astype(str), "open": close - 0.05, "high": close + 0.2,
        "low": close - 0.3, "close": close, "volume": 1000 + np.arange(60)})


class MethodsTests(unittest.TestCase):
    def test_future_mutation_does_not_change_features(self):
        source = bars()
        before = m.make_features(source)
        source.loc[45:, ["high", "close"]] *= 2
        after = m.make_features(source)
        pd.testing.assert_frame_equal(before.loc[:44, m.FEATURES], after.loc[:44, m.FEATURES])
        self.assertNotEqual(before.loc[44, "target_bps"], after.loc[44, "target_bps"])

    def test_labels_use_next_open_and_close(self):
        source = bars()
        result = m.make_features(source)
        self.assertAlmostEqual(result.loc[30, "target_bps"],
                               (source.loc[31, "close"] / source.loc[31, "open"] - 1) * 10000)
        self.assertLess(result.loc[30, "feature_date"], result.loc[30, "target_date"])
        self.assertTrue(pd.isna(result.iloc[-1].target_bps))

    def test_invalid_bar_breaks_history(self):
        source = bars()
        source.loc[30, "high"] = 1
        result = m.make_features(source)
        self.assertTrue(result.loc[31:50, "return20"].isna().all())
        self.assertEqual(result.invalid_source_rows.iloc[0], 1)

    def test_weight_fit_prefers_accurate_member_and_stays_convex(self):
        y = np.linspace(-10, 10, 150)
        forecasts = np.column_stack([y, -y, y + 5])
        weights = m.inverse_error_weights(forecasts, y)
        self.assertGreater(weights[0], 0.99)
        self.assertAlmostEqual(weights.sum(), 1)
        np.testing.assert_allclose(m.blend(forecasts, [1, 0, 0]), y)
        with self.assertRaises(ValueError):
            m.blend(forecasts, [1, -0.1, 0.1])

    def test_costs_hurt_both_sides_on_flat_prices(self):
        for side in [-1, 1]:
            cheap = m.bar_trade(100, 100, side, 100000, 2)
            dear = m.bar_trade(100, 100, side, 100000, 10)
            self.assertLess(cheap["net_pnl"], 0)
            self.assertLess(dear["net_pnl"], cheap["net_pnl"])
            self.assertAlmostEqual(cheap["gross_pnl"] - cheap["fees"], cheap["net_pnl"])

    def test_metric_cohorts_must_match(self):
        y = np.array([1.0, -1.0, 0.0])
        result = m.metrics(y, y, np.zeros(3))
        self.assertEqual(result["direction_accuracy"], 1)
        self.assertEqual(result["direction_rows"], 2)
        with self.assertRaises(ValueError):
            m.metrics(y, y[:2], y)


if __name__ == "__main__":
    unittest.main()
