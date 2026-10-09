from dataclasses import replace
from datetime import datetime, timezone
import importlib
import unittest

from research.intraday_lab.costs import round_trip_fees
from research.intraday_lab.domain import ExecutionConfig, PolicyConfig, Signal, Side, Tick
from research.intraday_lab.replay import ReplayEngine

s = importlib.import_module("research.12_execution_costs.strategy")

BASE = int(datetime(2026, 8, 19, 4, 10, tzinfo=timezone.utc).timestamp() * 1_000_000)


class OneSignal:
    def __init__(self, side):
        self.side = side
        self.sent = False

    def on_tick(self, tick):
        if self.sent:
            return None, "already_sent"
        self.sent = True
        return Signal(tick.at_us, 1, self.side, tick.midpoint, 20, 4), "signal"


def replay(side=Side.LONG, **settings):
    ticks = [Tick(BASE + sec * 1_000_000, 1, "A", 99.99, 100.01, 100,
                  100, 1000, 1000, 0, True, True) for sec in range(13)]
    config = replace(PolicyConfig(), horizon_seconds=2)
    engine = ReplayEngine(config, replace(ExecutionConfig(), **settings))
    engine.policy = OneSignal(side)
    summary = engine.run(ticks)
    return engine, summary


class ExecutionTests(unittest.TestCase):
    def test_later_fill_and_exact_accounting_for_both_sides(self):
        for side in (Side.LONG, Side.SHORT):
            engine, summary = replay(side)
            trade = engine.trades[0]
            self.assertGreater(trade.entry_us, trade.signal_us)
            expected = round_trip_fees(trade.entry_price, trade.exit_price,
                                       trade.quantity, long=side is Side.LONG)
            self.assertAlmostEqual(trade.fees, expected)
            self.assertAlmostEqual(trade.net_pnl, trade.gross_pnl - expected)
            self.assertAlmostEqual(summary["net_pnl"], trade.net_pnl, places=3)

    def test_delay_is_applied_to_entry_and_exit(self):
        engine, _ = replay(latency_ms=3000)
        trade = engine.trades[0]
        self.assertEqual(trade.entry_us - trade.signal_us, 3_000_000)
        self.assertEqual(trade.exit_us - trade.entry_us, 5_000_000)

    def test_restrictive_footprint_reduces_quantity(self):
        base, _ = replay()
        restricted, _ = replay(aggregate_depth_fraction=.01)
        self.assertLess(restricted.trades[0].quantity, base.trades[0].quantity)
        self.assertLessEqual(restricted.trades[0].quantity, 10)

    def test_slippage_worsens_fixed_size_flat_quote_return(self):
        base, _ = replay()
        stressed, _ = replay(extra_slippage_bps=3)
        self.assertLess(stressed.trades[0].net_pnl, base.trades[0].net_pnl)

    def test_no_trade_control_has_no_orders(self):
        ticks = [Tick(BASE, 1, "A", 99.99, 100.01, 100, 100, 1000, 1000, 0, True, True)]
        engine = ReplayEngine(PolicyConfig(), ExecutionConfig())
        engine.policy = s.NoTradePolicy()
        summary = engine.run(ticks)
        self.assertEqual(summary["net_pnl"], 0)
        self.assertEqual(summary["trades"], 0)
        self.assertEqual(summary["pending_entries"], 0)


if __name__ == "__main__":
    unittest.main()
