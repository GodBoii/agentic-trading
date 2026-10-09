from dataclasses import replace
from datetime import datetime
from importlib import import_module
import unittest

from research.intraday_lab.domain import ExecutionConfig, PolicyConfig, Side, Signal, Tick
from research.intraday_lab.replay import ReplayEngine
from research.intraday_lab.policy import MomentumPolicy

maths = import_module("research.11_exit_math.strategy")
BASE = int(datetime.fromisoformat("2026-08-19T10:00:00+05:30").timestamp()*1_000_000)


def tick(second, price=100):
    return Tick(BASE+second*1_000_000, 1, "TEST", price-.01, price+.01,
                price, 100, 100000, 100000, 0, True, True)


class OneSignal:
    def __init__(self):
        self.sent = False

    def on_tick(self, observation):
        if self.sent:
            return None, "already_sent"
        self.sent = True
        return Signal(observation.at_us, 1, Side.LONG, observation.midpoint, 20, 5), "signal"


def engine(**changes):
    result = ReplayEngine(replace(PolicyConfig(), **changes), ExecutionConfig())
    result.policy = OneSignal()
    return result


class ExitMathTests(unittest.TestCase):
    def test_two_to_one_without_costs_needs_one_third_success(self):
        self.assertAlmostEqual(maths.break_even_probability(30,15,0), 1/3)

    def test_costs_raise_required_success(self):
        self.assertAlmostEqual(maths.break_even_probability(30,15,10),25/45)

    def test_threshold_sets_expected_payoff_to_zero(self):
        p = maths.break_even_probability(60,30,10)
        self.assertAlmostEqual(maths.expected_payoff_bps(p,60,30,10),0)

    def test_costs_larger_than_target_are_explicitly_impossible(self):
        self.assertGreater(maths.break_even_probability(5,5,8),1)
        self.assertLess(maths.expected_payoff_bps(1,5,5,8),0)

    def test_invalid_probabilities_and_distances_rejected(self):
        for probability in (-1,2,float('nan')):
            with self.assertRaises(ValueError):
                maths.expected_payoff_bps(probability,30,15,10)
        for value in (0,-1,float('inf')):
            with self.assertRaises(ValueError):
                maths.break_even_probability(value,15,10)

    def test_time_exit_is_requested_then_fills_later(self):
        replay = engine(horizon_seconds=5)
        replay.run([tick(i) for i in range(7)])
        self.assertEqual(len(replay.trades),0)
        self.assertIn(1,replay.exits)
        replay.on_tick(tick(7))
        self.assertEqual(replay.trades[0].exit_reason,"time")
        self.assertEqual(replay.trades[0].exit_us,BASE+7_000_000)

    def test_stop_gap_can_exceed_nominal_stop_loss(self):
        replay = engine()
        replay.run([tick(0),tick(1),tick(2,99.8),tick(3,99.4)])
        trade = replay.trades[0]
        nominal = trade.entry_price*trade.quantity*15/10000
        self.assertEqual(trade.exit_reason,"stop")
        self.assertGreater(-trade.gross_pnl,nominal)

    def test_target_fills_at_later_quote_not_at_barrier(self):
        replay = engine()
        replay.run([tick(0),tick(1),tick(2,100.4),tick(3,100.3)])
        trade = replay.trades[0]
        self.assertEqual(trade.exit_reason,"target")
        self.assertLess(trade.exit_price,trade.entry_price*1.003)

    def test_exit_spec_rejects_fractional_or_negative_horizon(self):
        for horizon in (0,-1,0.5):
            with self.assertRaises(ValueError):
                maths.ExitSpec(30,15,horizon)

    def test_exit_changes_preserve_raw_entry_sequence(self):
        specs = [maths.ExitSpec(30,15,300),maths.ExitSpec(60,30,300),maths.ExitSpec(30,15,60)]
        policies = [MomentumPolicy(replace(PolicyConfig(),**s.policy_overrides())) for s in specs]
        outputs = [[] for _ in policies]
        for second in range(400):
            observation = tick(second,100+second*.001)
            for index,policy in enumerate(policies):
                outputs[index].append(policy.on_tick(observation))
        self.assertEqual(outputs[0],outputs[1])
        self.assertEqual(outputs[0],outputs[2])
        self.assertTrue(any(result[0] is not None for result in outputs[0]))


if __name__ == "__main__":
    unittest.main()
