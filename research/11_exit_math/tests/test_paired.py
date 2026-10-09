from datetime import datetime
from importlib import import_module
import unittest

from research.intraday_lab.domain import ExecutionConfig, PolicyConfig, Side, Tick
from research.intraday_lab.domain import Signal
from research.intraday_lab.replay import ReplayEngine

paired = import_module("research.11_exit_math.paired")
ExitSpec = import_module("research.11_exit_math.strategy").ExitSpec
BASE = int(datetime.fromisoformat("2026-08-19T10:00:00+05:30").timestamp()*1_000_000)


def tick(second,price=100):
    return Tick(BASE+second*1_000_000,1,"TEST",price-.01,price+.01,price,
                100,10000,10000,0,True,True)


class PairedExitTests(unittest.TestCase):
    def test_time_exit_preserves_fixed_quantity_and_waits_for_later_quote(self):
        entry = paired.FrozenEntry(1,Side.LONG,BASE,100.01,7)
        result = paired.replay_exit(entry,[tick(i) for i in range(8)],ExitSpec(30,15,5),
                                    PolicyConfig(),ExecutionConfig())
        self.assertTrue(result["complete"])
        self.assertEqual(result["quantity"],7)
        self.assertEqual(result["exit_us"],BASE+6_000_000)

    def test_missing_next_quote_leaves_counterfactual_unresolved(self):
        entry = paired.FrozenEntry(1,Side.LONG,BASE,100.01,100)
        result = paired.replay_exit(entry,[tick(0),tick(5)],ExitSpec(30,15,5),
                                    PolicyConfig(),ExecutionConfig())
        self.assertFalse(result["complete"])
        self.assertIsNone(result["net_pnl"])

    def test_same_entry_short_uses_ask_to_exit(self):
        entry = paired.FrozenEntry(1,Side.SHORT,BASE,99.99,100)
        result = paired.replay_exit(entry,[tick(0),tick(1,99.6),tick(2,99.7)],ExitSpec(30,15,5),
                                    PolicyConfig(),ExecutionConfig())
        self.assertEqual(result["exit_reason"],"target")
        self.assertGreater(result["exit_price"],99.71)
        self.assertGreater(result["gross_pnl"],0)

    def test_pre_entry_price_does_not_trigger_exit(self):
        entry = paired.FrozenEntry(1,Side.LONG,BASE+1_000_000,100.01,100)
        result = paired.replay_exit(entry,[tick(0,110),tick(1),tick(2)],ExitSpec(30,15,5),
                                    PolicyConfig(),ExecutionConfig())
        self.assertFalse(result["complete"])
        self.assertIsNone(result["exit_reason"])

    def test_same_exit_matches_account_engine_without_portfolio_loss_actions(self):
        class OneSignal:
            def on_tick(self, observation):
                if observation.at_us == BASE:
                    return Signal(BASE,1,Side.LONG,100,20,5),"signal"
                return None,"wait"

        config = PolicyConfig()
        execution = ExecutionConfig()
        tape = [tick(0),tick(1),tick(2,100.4),tick(3,100.3)]
        account = ReplayEngine(config,execution)
        account.policy = OneSignal()
        account.run(tape)
        trade = account.trades[0]
        entry = paired.FrozenEntry(trade.security_id,Side(trade.side),trade.entry_us,
                                  trade.entry_price,trade.quantity)
        result = paired.replay_exit(entry,tape,ExitSpec(30,15,300),config,execution)
        self.assertEqual(result["exit_us"],trade.exit_us)
        self.assertEqual(result["exit_reason"],trade.exit_reason)
        self.assertAlmostEqual(result["gross_pnl"],trade.gross_pnl)
        self.assertAlmostEqual(result["fees"],trade.fees)
        self.assertAlmostEqual(result["net_pnl"],trade.net_pnl)


if __name__ == "__main__":
    unittest.main()
