from __future__ import annotations

import unittest
import importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

spec = importlib.util.spec_from_file_location("volatility_study", Path(__file__).with_name("study.py"))
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)
black_price = study.black_price
implied_volatility = study.implied_volatility
same_expiry_pair = study.same_expiry_pair
variance_frame = study.variance_frame
qlike = study.qlike
from nifty_lab.replay import QuoteBook


class BlackTests(unittest.TestCase):
    def test_published_vollib_reference_value(self):
        self.assertAlmostEqual(black_price(100, 100, .5, .02, .2), 5.5811067246048118, places=10)

    def test_iv_round_trip_and_parity(self):
        for forward, strike, years in ((100, 90, .01), (100, 100, .4), (25000, 24950, .0001)):
            c = black_price(forward, strike, years, .05, .25, "CE")
            p = black_price(forward, strike, years, .05, .25, "PE")
            self.assertAlmostEqual(c-p, np.exp(-.05*years)*(forward-strike), places=8)
            for kind, value in (("CE", c), ("PE", p)):
                self.assertAlmostEqual(implied_volatility(value, forward, strike, years, .05, kind), .25, places=7)

    def test_rejects_impossible_prices(self):
        for price in (-1, 101):
            with self.assertRaises(ValueError):
                implied_volatility(price, 100, 100, 1)
        with self.assertRaises(ValueError):
            implied_volatility(9, 110, 100, 1)
        with self.assertRaises(ValueError):
            implied_volatility(5, 100, 100, 0)

    def test_quote_lookup_does_not_see_future(self):
        at = pd.Timestamp("2026-08-20T05:00:00Z")
        data = pd.DataFrame([{"security_id": "1", "timestamp": at+pd.Timedelta(seconds=1), "bid": 5, "ask": 6}])
        book = QuoteBook(data, 2)
        self.assertEqual(book.snapshot(at), {})
        self.assertEqual(book.snapshot(at+pd.Timedelta(seconds=4)), {})

    def test_parity_forward_and_synchronisation(self):
        at = pd.Timestamp("2026-08-20T05:00:00Z")
        expiry = pd.Timestamp("2026-08-25 15:30", tz="Asia/Kolkata").tz_convert("UTC")
        years = (expiry-at).total_seconds()/(365*86400)
        quotes = {}
        for strike in (24950, 25000, 25050):
            for kind in ("CE", "PE"):
                value = black_price(25020, strike, years, 0, .15, kind)
                key = str(strike)+kind
                quotes[key] = {"security_id": key, "expiry": "2026-08-25", "strike": strike,
                               "option_type": kind, "bid": value-.1, "ask": value+.1,
                               "timestamp": at-pd.Timedelta(seconds=1)}
        pair = same_expiry_pair(quotes, at)
        self.assertAlmostEqual(pair["forward"], 25020, places=8)
        self.assertTrue(pair["parity_intersection"])
        for item in quotes.values():
            if item["option_type"] == "PE":
                item["timestamp"] = at-pd.Timedelta(seconds=10)
        self.assertIsNone(same_expiry_pair(quotes, at))


class VarianceTests(unittest.TestCase):
    @staticmethod
    def frame(n=100):
        times = pd.date_range("2026-08-20T04:00Z", periods=n, freq="min")
        return pd.DataFrame({"date": "2026-08-20", "security_id": "f", "segment": 0,
                             "decision_at": times, "close": 25000*np.exp(np.arange(n)*.0001), "complete_minute": True})

    def test_forecast_label_uses_future_returns_only(self):
        data = self.frame()
        data.loc[70, "close"] *= 1.01
        result = variance_frame(data)
        expected = np.sum((np.diff(np.log(data.loc[65:70, "close"])) * 10000)**2)
        self.assertAlmostEqual(result.loc[65, "target_5"], expected, places=7)
        self.assertAlmostEqual(result.loc[65, "rv_60"], 1, places=8)
        self.assertTrue(pd.isna(result.iloc[-1]["target_5"]))

    def test_gap_and_incomplete_minute_reset(self):
        data = self.frame(180)
        data.loc[80, "complete_minute"] = False
        data = data.drop(index=150)
        result = variance_frame(data)
        before = result[result["decision_at"] == data.loc[78, "decision_at"]].iloc[0]
        after = result[result["decision_at"] == data.loc[90, "decision_at"]].iloc[0]
        after_gap = result[result["decision_at"] == data.loc[160, "decision_at"]].iloc[0]
        self.assertTrue(pd.isna(before["target_5"]))
        self.assertTrue(pd.isna(after["rv_60"]))
        self.assertTrue(pd.isna(after_gap["rv_60"]))

    def test_qlike_exact_and_bad_forecast(self):
        values = np.array([1, 10, 100])
        np.testing.assert_array_equal(qlike(values, values), 0)
        self.assertTrue((qlike(values, values*2)>0).all())


if __name__ == "__main__":
    unittest.main()
