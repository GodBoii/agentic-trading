import importlib
import unittest
from dataclasses import replace
from math import exp, log

from research.intraday_lab.domain import Tick

s = importlib.import_module("research.13_pairs_cointegration.strategy")


def tick(sec, sid, mid=100, **changes):
    return replace(Tick(1_000_000_000 + sec * 1_000_000, sid, str(sid), mid - .01,
                        mid + .01, mid, mid, 100000, 100000, 0, True, True), **changes)


class PairTests(unittest.TestCase):
    def test_synchronization_has_no_future_quote(self):
        tape = sorted([tick(i, sid) for i in range(180) for sid in s.PAIR], key=lambda t: t.at_us)
        prefix, _ = s.synchronize(tape[:200], receipt_proxy=False)
        full, _ = s.synchronize(tape, receipt_proxy=False)
        self.assertEqual(prefix, full[:len(prefix)])
        self.assertTrue(all(p.first.at_us <= p.at_us and p.second.at_us <= p.at_us for p in full))

    def test_missing_freshness_rejects_both_leg_point(self):
        tape = sorted([tick(i, sid, data_fresh=None) for i in range(120) for sid in s.PAIR],
                      key=lambda t: t.at_us)
        self.assertEqual(s.synchronize(tape, receipt_proxy=False)[0], [])
        self.assertGreater(len(s.synchronize(tape, receipt_proxy=True)[0]), 0)

    def test_ols_known_hedge_and_future_fit_does_not_mutate(self):
        points = []
        for i in range(200):
            x = 4 + .001 * i
            y = .5 + 1.2 * x + .0001 * (-1) ** i
            points.append(s.PairPoint(1_000_000_000 + i * s.GRID_US,
                                      tick(60 * i, s.PAIR[0], exp(y)), tick(60 * i, s.PAIR[1], exp(x))))
        model = s.fit_pair(points)
        self.assertAlmostEqual(model.beta, 1.2, places=4)
        self.assertAlmostEqual(model.intercept, .5, places=3)
        before = model.beta
        s.ar1_diagnostics(points[100:], model)
        self.assertEqual(model.beta, before)

    def test_gap_never_becomes_regular_ar1_lag(self):
        points = [s.PairPoint(1_000_000_000 + i * 10 * s.GRID_US,
                             tick(i * 600, s.PAIR[0], 101), tick(i * 600, s.PAIR[1])) for i in range(50)]
        result = s.ar1_diagnostics(points, s.FrozenPair(0, 1, .001, 100))
        self.assertEqual(result["regular_lag_pairs"], 0)
        self.assertNotIn("phi", result)

    def test_flat_two_leg_scenario_loses_exact_fee_and_spread(self):
        points = [s.PairPoint(1_000_000_000 + i * s.GRID_US,
                             tick(i * 60, s.PAIR[0], 101), tick(i * 60, s.PAIR[1])) for i in range(20)]
        model = s.FrozenPair(0, 1, .001, 100)
        outcomes, result = s.two_leg_outcomes(points, model)
        self.assertGreater(result["scenarios"], 0)
        self.assertLess(result["net"], 0)
        for row in outcomes:
            self.assertAlmostEqual(row["net"], row["gross"] - row["fees"])
            self.assertTrue(all(leg["entry_quote_us"] > row["decision_us"] for leg in row["legs"]))
        self.assertTrue(all(b["decision_us"] > a["exit_grid_us"] for a,b in zip(outcomes,outcomes[1:])))

    def test_training_refuses_short_sample(self):
        self.assertIsNone(s.fit_pair([]))


if __name__ == "__main__":
    unittest.main()
