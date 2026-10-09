"""Prior-session isolation and slot-coverage behavior."""

from dataclasses import replace
from datetime import datetime
from importlib import import_module
from types import MappingProxyType
import unittest

from research.intraday_lab.domain import PolicyConfig, Side, Tick

strategy = import_module("research.14_intraday_seasonality.strategy")
TRAIN = ("2026-08-19", "2026-08-20", "2026-08-21")


def tick(day: str, second: int, price: float = 100, **changes) -> Tick:
    base = int(datetime.fromisoformat(day + "T09:15:00+05:30").timestamp() * 1_000_000)
    return replace(Tick(base + second * 1_000_000, 1, "TEST", price - .005,
                        price + .005, price, None, 10000, 10000, 0, True, True), **changes)


def model(returns=(15.0, 20.0, 25.0)):
    return strategy.SlotModel(TRAIN, "recent_trade", MappingProxyType({(1, 1): strategy.SlotEstimate(returns)}))


def policy(name="same_slot_mean", estimate=None):
    return strategy.SeasonalityPolicy(replace(PolicyConfig(), name=name), model() if estimate is None else estimate)


class SeasonalityTests(unittest.TestCase):
    def test_training_requires_exact_dates_and_all_three_slot_returns(self):
        sessions = {day: [tick(day, 1800 + second, 100 + second * .0001) for second in range(1800)] for day in TRAIN}
        fitted, report = strategy.fit_model(sessions, "recent_trade")
        self.assertEqual(report["three_session_estimates"], 1)
        self.assertEqual(len(fitted.estimates[(1, 1)].returns_bps), 3)
        sessions[TRAIN[-1]] = sessions[TRAIN[-1]][30:]
        fitted, _ = strategy.fit_model(sessions, "recent_trade")
        self.assertEqual(len(fitted.estimates), 0)

    def test_gaps_and_unknown_metadata_prevent_strict_model_estimate(self):
        sessions = {day: [tick(day, 1800 + second) for second in range(1800)] for day in TRAIN}
        sessions[TRAIN[0]] = [t for i, t in enumerate(sessions[TRAIN[0]]) if not 100 <= i <= 120]
        fitted, _ = strategy.fit_model(sessions, "recent_trade")
        self.assertFalse(fitted.estimates)
        sessions = {day: [tick(day, 1800 + second, data_fresh=None) for second in range(1800)] for day in TRAIN}
        self.assertFalse(strategy.fit_model(sessions, "recent_trade")[0].estimates)
        self.assertTrue(strategy.fit_model(sessions, "receipt_proxy")[0].estimates)

    def test_training_or_same_day_evaluation_is_rejected(self):
        for day in TRAIN:
            with self.assertRaises(ValueError):
                policy().on_tick(tick(day, 1800))

    def test_evaluation_price_changes_do_not_change_frozen_signal_side(self):
        first = policy().on_tick(tick("2026-08-24", 1800, 100))[0]
        second = policy().on_tick(tick("2026-08-24", 1800, 200))[0]
        self.assertEqual(first.side, Side.LONG)
        self.assertEqual(first.side, second.side)
        self.assertEqual(first.move_bps, second.move_bps)

    def test_sign_consensus_rejects_mixed_history(self):
        mixed = model((30, 30, -15))
        self.assertIsNotNone(policy(estimate=mixed).on_tick(tick("2026-08-24", 1800))[0])
        self.assertEqual(policy("same_slot_unanimous_sign", mixed).on_tick(tick("2026-08-24", 1800))[1], "prior_sign_disagreement")

    def test_late_slot_start_does_not_get_second_chance(self):
        p = policy()
        self.assertEqual(p.on_tick(tick("2026-08-24", 1811))[1], "late_slot_start")
        self.assertEqual(p.on_tick(tick("2026-08-24", 1812))[1], "between_evaluations")

    def test_missing_estimate_does_not_default_to_zero_return(self):
        empty = strategy.SlotModel(TRAIN, "recent_trade", MappingProxyType({}))
        self.assertEqual(policy(estimate=empty).on_tick(tick("2026-08-24", 1800))[1], "insufficient_prior_sessions")


if __name__ == "__main__":
    unittest.main()
