import importlib
import unittest

import numpy as np
import pandas as pd

d = importlib.import_module("research.45_market_dataset.dataset")
a = importlib.import_module("research.45_market_dataset.account")


def candles() -> pd.DataFrame:
    time = pd.date_range("2022-02-14T09:15:00+05:30", periods=375, freq="min")
    prices = 100 + np.arange(375) * 0.01
    return pd.DataFrame({"timestamp": time.as_unit("s").astype("int64"),
        "open": prices, "close": prices + 0.005, "high": prices + 0.01,
        "low": prices - 0.01, "volume": 1000 + np.arange(375)})


def decisions(count: int = 4) -> pd.DataFrame:
    base = 1_800_000_000_000_000
    return pd.DataFrame({"date": ["2026-01-01"] * count, "security_id": np.arange(1, count + 1),
        "decision_us": [base] * count, "entry_us": [base + 60_000_000] * count,
        "exit_us_5": [base + 360_000_000] * count, "decision_reference": [100.0] * count,
        "entry_reference": [100.0] * count, "exit_reference_5": [101.0] * count})


class SharedTests(unittest.TestCase):
    def test_future_candles_do_not_change_features_or_sequences(self):
        before = d.normalized_bars(candles())
        changed = before.copy()
        changed.loc[150:, ["open", "close", "high", "low"]] *= 2
        changed.loc[150:, "volume"] *= 10
        x, seq = d.causal_day_features(before)
        x2, seq2 = d.causal_day_features(changed)
        pd.testing.assert_frame_equal(x.iloc[:150], x2.iloc[:150])
        np.testing.assert_allclose(seq[:150], seq2[:150], equal_nan=True)

    def test_complete_session_and_bad_candle_admission(self):
        source = d.normalized_bars(candles())
        self.assertEqual(len(list(d.eligible_sessions(source))), 1)
        self.assertEqual(len(list(d.eligible_sessions(source.iloc[:-1]))), 0)
        altered = candles()
        altered.loc[100, "high"] = 1
        self.assertEqual(len(list(d.eligible_sessions(d.normalized_bars(altered)))), 0)

    def test_timestamp_seconds_are_floored_and_duplicates_refused(self):
        original = candles()
        original.timestamp += 1
        frame = d.normalized_bars(original)
        self.assertTrue((frame.bucket_us % 60_000_000 == 0).all())
        doubled = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
        self.assertEqual(len(list(d.eligible_sessions(doubled))), 0)

    def test_full_sequential_execution_and_slot_reservations(self):
        rows = decisions()
        summary, trades, daily = a.account_replay(rows, np.full(4, 100.0), 5)
        self.assertEqual(summary["trades"], 3)
        self.assertEqual(summary["rejections"]["capacity"], 1)
        self.assertEqual(daily.maximum_slots.max(), 3)
        self.assertTrue((trades.decision_us < trades.entry_us).all())
        self.assertAlmostEqual(summary["net_pnl"], summary["gross_pnl"] - summary["fees"])
        self.assertAlmostEqual(daily.ending_equity.iloc[0] - 500000, trades.net_pnl.sum())

    def test_no_trade_control_and_invalid_chronology(self):
        rows = decisions()
        summary, trades, daily = a.account_replay(rows, np.zeros(4), 5)
        self.assertEqual(summary["net_pnl"], 0)
        self.assertTrue(trades.empty)
        self.assertEqual(daily.ending_equity.iloc[0], 500000)
        rows.entry_us = rows.decision_us
        with self.assertRaises(ValueError):
            a.account_replay(rows, np.ones(4) * 100, 5)

    def test_same_stock_cannot_overlap_and_new_capacity_after_exit(self):
        rows = decisions(3)
        rows.security_id = 1
        rows.loc[1, ["decision_us", "entry_us", "exit_us_5"]] += 60_000_000
        rows.loc[2, ["decision_us", "entry_us", "exit_us_5"]] += 600_000_000
        summary, _, _ = a.account_replay(rows, np.full(3, 100.0), 5)
        self.assertEqual(summary["trades"], 2)
        self.assertEqual(summary["rejections"]["capacity"], 1)

    def test_realized_daily_loss_halts_later_entries(self):
        rows = decisions(2)
        rows.loc[0, "exit_reference_5"] = 95.0
        rows.loc[1, ["decision_us", "entry_us", "exit_us_5"]] += 600_000_000
        summary, _, _ = a.account_replay(rows, np.full(2, 100.0), 5)
        self.assertEqual(summary["trades"], 1)
        self.assertEqual(summary["rejections"]["daily_loss"], 1)

    def test_gate_ignores_future_exit_and_cost_stress_hurts_both_sides(self):
        rows = decisions(1)
        rows.exit_reference_5 = 100.0
        for sign in [-1, 1]:
            cheap, _, _ = a.account_replay(rows, np.array([100.0 * sign]), 5, cost_per_leg_bps=2)
            dear, _, _ = a.account_replay(rows, np.array([100.0 * sign]), 5, cost_per_leg_bps=5)
            self.assertLess(dear["net_pnl"], cheap["net_pnl"])
            self.assertEqual(cheap["trades"], 1)
        changed = rows.copy()
        changed.exit_reference_5 = 1000.0
        weak, _, _ = a.account_replay(changed, np.array([1.0]), 5)
        self.assertEqual(weak["trades"], 0)


if __name__ == "__main__":
    unittest.main()
