from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location("regime_study", Path(__file__).with_name("study.py"))
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)


class RegimeTests(unittest.TestCase):
    @staticmethod
    def frame(days=5, size=100):
        rng = np.random.default_rng(17)
        rows = []
        for day in pd.date_range("2026-08-01", periods=days):
            times = pd.date_range(day.strftime("%Y-%m-%d")+"T04:00Z", periods=size, freq="min")
            rows.append(pd.DataFrame({"date": day.strftime("%Y-%m-%d"), "decision_at": times,
                                      "close": 25000*np.exp(np.cumsum(rng.normal(0,.0001,size))),
                                      "security_id": "future", "segment": 0, "complete_minute": True}))
        return pd.concat(rows, ignore_index=True)

    def test_feature_history_unchanged_by_future_prices(self):
        raw = self.frame()
        altered = raw.copy()
        cutoff = raw.loc[450, "decision_at"]
        altered.loc[altered["decision_at"] > cutoff, "close"] *= 1.1
        before, after = study.causal_features(raw), study.causal_features(altered)
        columns = ["lag_0", "lag_4", "vr5_60", "past_var60", "ou_phi"]
        pd.testing.assert_frame_equal(before.loc[before["decision_at"]<=cutoff, columns], after.loc[after["decision_at"]<=cutoff, columns])

    def test_missing_minute_blocks_labels(self):
        raw = self.frame(days=1, size=150).drop(index=80)
        result = study.causal_features(raw)
        before = result[result["decision_at"]==raw.loc[78,"decision_at"]].iloc[0]
        after = result[result["decision_at"]==raw.loc[90,"decision_at"]].iloc[0]
        self.assertTrue(pd.isna(before["target_5"]))
        self.assertTrue(pd.isna(after["vr5_60"]))

    def test_regime_fit_ignores_test_labels(self):
        frame = study.causal_features(self.frame()).dropna(subset=["target_5", "log_var5", "past_ret5"])
        train = frame[frame["date"] < "2026-08-05"]
        test = frame[frame["date"] == "2026-08-05"].copy()
        first, fitted = study.mixture_prediction(train, test, "target_5", 2)
        test["target_5"] = 999999
        second, refitted = study.mixture_prediction(train, test, "target_5", 2)
        np.testing.assert_array_equal(first, second)
        self.assertEqual(fitted, refitted)
        np.testing.assert_allclose(fitted["training_scaler_mean"], train[["log_var5","past_ret5"]].mean().to_numpy())

    def test_all_past_predictions_invariant_to_future_labels(self):
        frame = study.causal_features(self.frame(size=140))
        first, _ = study.walk_forward(frame)
        altered = frame.copy()
        for horizon in study.HORIZONS:
            column = f"target_{horizon}"
            selected = (altered["date"]=="2026-08-05") & altered[column].notna()
            altered.loc[selected, column] = 999999
        second, _ = study.walk_forward(altered)
        columns = ["date", "decision_at", "horizon"] + [name for name in first if name.startswith("pred_")]
        pd.testing.assert_frame_equal(first[columns], second[columns])

    def test_vr_independent_returns_near_one(self):
        rng = np.random.default_rng(22)
        prices = np.cumsum(rng.normal(size=20000))
        self.assertLess(abs(study.variance_ratio(prices)-1), .05)

    def test_missing_labels_retain_every_scored_row_in_day_metrics(self):
        frame = study.causal_features(self.frame(days=6, size=140))
        # Missing outcomes in the middle and at each session end leave gaps in
        # the prediction index. Date grouping must retain the actual row identity.
        missing = (frame["date"] >= "2026-08-04") & (frame.index % 7 == 0)
        for horizon in study.HORIZONS:
            frame.loc[missing, f"target_{horizon}"] = np.nan
        predictions, report = study.walk_forward(frame)
        for horizon in study.HORIZONS:
            emitted = predictions[predictions["horizon"] == horizon]
            scored = emitted.dropna(subset=["actual_bps"])
            self.assertLess(len(scored), len(emitted))
            retained_rows = sum(len(day) for _, day in scored.groupby("date"))
            self.assertEqual(retained_rows, report[str(horizon)]["scored_rows"])
            for name, metrics in report[str(horizon)]["metrics"].items():
                day_improvements = []
                for _, day in scored.groupby("date"):
                    actual = day["actual_bps"].to_numpy()
                    forecast = day[name].to_numpy()
                    day_improvements.append(np.mean(actual**2 - (actual-forecast)**2))
                self.assertEqual(len(day_improvements), metrics["days"])
                self.assertEqual(retained_rows, metrics["rows"])
                self.assertAlmostEqual(np.mean(day_improvements),
                                       metrics["equal_day_mse_improvement_vs_zero_bps2"], places=10)

    def test_ou_estimate_on_known_stationary_simulation(self):
        rng = np.random.default_rng(25)
        levels = [0.0]
        for _ in range(20000):
            levels.append(.8*levels[-1]+rng.normal())
        phi, intercept, half_life = study.ou_like_fit(np.array(levels))
        self.assertLess(abs(phi-.8), .02)
        self.assertLess(abs(intercept), .03)
        self.assertLess(abs(half_life-(-np.log(2)/np.log(.8))), .3)


if __name__ == "__main__":
    unittest.main()
