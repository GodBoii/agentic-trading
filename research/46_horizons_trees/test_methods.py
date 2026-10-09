"""Selection control, fixed-grid scope, date-group purge and forecast metrics."""

from importlib import import_module
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import pandas as pd

m = import_module("research.46_horizons_trees.methods")
SPEC = json.loads((Path(__file__).parent / "specification.json").read_text())


def epoch_us(date: str) -> int:
    return int(pd.Timestamp(date, tz="Asia/Kolkata").timestamp() * 1_000_000)


class MethodTests(unittest.TestCase):
    def test_exact_bounded_trial_count(self):
        trials = [candidate for h in SPEC["horizons_minutes"] for candidate in m.candidates(h, SPEC)]
        self.assertEqual(len(trials), 36)
        self.assertEqual(len({c.candidate_id for c in trials}), 36)
        self.assertEqual(sum(c.family == "momentum" for c in trials), 18)

    def test_no_trade_beats_negative_validation_winner(self):
        result = m.select_validation([{"candidate_id": "loss", "net_pnl": -1, "trades": 200}], 100)
        self.assertTrue(result["abstain"])

    def test_sparse_positive_result_is_not_selectable(self):
        result = m.select_validation([{"candidate_id": "sparse", "net_pnl": 10000, "trades": 99}], 100)
        self.assertTrue(result["abstain"])

    def test_positive_selection_and_deterministic_tie(self):
        rows = [{"candidate_id": "z", "net_pnl": 20, "trades": 100},
                {"candidate_id": "a", "net_pnl": 20, "trades": 200}]
        self.assertEqual(m.select_validation(rows, 100)["candidate_id"], "a")
        self.assertEqual(m.select_validation(list(reversed(rows)), 100)["candidate_id"], "a")

    def test_zero_active_result_cannot_force_entry(self):
        result = m.select_validation([{"candidate_id": "a", "net_pnl": 0, "trades": 200}], 100)
        self.assertTrue(result["abstain"])

    def test_all_stocks_in_date_group_stay_together(self):
        dates = ["2023-12-29", "2024-01-01", "2025-01-01"]
        rows = []
        for date in dates:
            start = epoch_us(date + "T09:45:00")
            for sid in [1, 2]:
                rows.append({"date": date, "security_id": sid, "decision_us": start,
                             "entry_us": start + 60_000_000, "exit_us_30": start + 31 * 60_000_000})
        parts = m.chronological_parts(pd.DataFrame(rows), SPEC, 30)
        self.assertEqual([len(parts[p]) for p in ["training", "validation", "test"]], [2, 2, 2])

    def test_label_crossing_year_boundary_is_purged(self):
        start = epoch_us("2023-12-31T23:40:00")
        frame = pd.DataFrame([{"date": "2023-12-31", "decision_us": start,
                               "entry_us": start + 60_000_000, "exit_us_30": start + 31 * 60_000_000}])
        self.assertTrue(m.chronological_parts(frame, SPEC, 30)["training"].empty)

    def test_invalid_temporal_order_rejected(self):
        start = epoch_us("2023-12-29T09:45:00")
        frame = pd.DataFrame([{"date": "2023-12-29", "decision_us": start,
                               "entry_us": start, "exit_us_30": start + 31 * 60_000_000}])
        with self.assertRaises(ValueError):
            m.chronological_parts(frame, SPEC, 30)

    def test_metrics_same_cohort_and_zero_forecast_is_abstention(self):
        result = m.forecast_metrics(np.asarray([1, -1, 0]), np.asarray([1, -1, 0]), 0)
        self.assertEqual(result["direction_accuracy"], 1)
        result = m.forecast_metrics(np.asarray([1, -1]), np.asarray([0, 0]), 0)
        self.assertEqual(result["direction_accuracy"], 0)
        with self.assertRaises(ValueError):
            m.forecast_metrics(np.asarray([1, 2]), np.asarray([1]), 0)

    def test_nonfinite_validation_value_rejected(self):
        with self.assertRaises(ValueError):
            m.select_validation([{"candidate_id": "bad", "net_pnl": float("nan"), "trades": 200}], 100)

    def test_actual_shared_account_nonoverlap_slots_and_adverse_costs(self):
        account = import_module("research.45_market_dataset.account")
        start = epoch_us("2024-01-02T09:45:00")
        rows = []
        for offset in [0, 15 * 60_000_000, 45 * 60_000_000]:
            for sid in range(1, 5):
                rows.append({"date": "2024-01-02", "security_id": sid,
                    "decision_us": start + offset, "entry_us": start + offset + 60_000_000,
                    "exit_us_30": start + offset + 31 * 60_000_000,
                    "decision_reference": 100, "entry_reference": 100, "exit_reference_30": 100.5})
        frame = pd.DataFrame(rows)
        forecasts = np.full(len(frame), 50.0)
        summary, trades, daily = account.account_replay(frame, forecasts, 30,
            threshold_net_bps=10, cost_per_leg_bps=2)
        self.assertEqual(summary["trades"], 6)
        self.assertEqual(daily.maximum_slots.max(), 3)
        self.assertTrue((trades.decision_us < trades.entry_us).all())
        self.assertAlmostEqual(trades.net_pnl.sum(), summary["net_pnl"])
        dear, _, _ = account.account_replay(frame, forecasts, 30,
            threshold_net_bps=10, cost_per_leg_bps=5)
        self.assertLess(dear["net_pnl"], summary["net_pnl"])
        no_trade, ledger, _ = account.account_replay(frame, np.zeros(len(frame)), 30,
            threshold_net_bps=10, cost_per_leg_bps=2)
        self.assertEqual(no_trade["net_pnl"], 0)
        self.assertTrue(ledger.empty)

    def test_frozen_numeric_boosting_state_reproduces_nonlinear_prediction(self):
        from sklearn.ensemble import HistGradientBoostingRegressor
        from threadpoolctl import threadpool_limits
        runner = import_module("research.46_horizons_trees.run")
        verifier = import_module("research.46_horizons_trees.verify")
        rng = np.random.default_rng(46)
        x = rng.normal(size=(1000, 2))
        y = np.where(x[:, 0] * x[:, 1] > 0, 20.0, -20.0)
        model = HistGradientBoostingRegressor(**SPEC["boosting"])
        with threadpool_limits(limits=2):
            model.fit(x, y)
            expected = model.predict(x[:100])
        with TemporaryDirectory() as directory:
            state = runner.freeze_model(Path(directory), 5, "boosting", model, ["a", "b"])
            actual = verifier.predict_nodes(x[:100], Path(directory) / state["file"])
        np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)
        self.assertLess(np.mean((expected-y[:100])**2), np.mean(y[:100]**2))


if __name__ == "__main__":
    unittest.main()
