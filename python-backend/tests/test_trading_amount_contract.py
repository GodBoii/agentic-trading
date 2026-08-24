from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pipeline.runtime.run_stock_agent import MultiStockAgentRunner
from pipeline.services.ai_trading_state_service import AITradingStateService
from pipeline.services.convex_service import ConvexService
from pipeline.services.trading_amount_service import TradingAmountService


DEPTH = [
    {"ask_price": 500.0 + index * 0.01, "ask_quantity": 10, "bid_price": 499.99 - index * 0.01, "bid_quantity": 10}
    for index in range(5)
]


class TradingAmountContractTests(unittest.TestCase):
    def test_missing_amount_selects_auto_while_invalid_manual_and_stale_fail_closed(self):
        now = datetime.now(timezone.utc)
        automatic = TradingAmountService.status({}, max_age_seconds=60, now=now)
        self.assertTrue(automatic["eligible"])
        self.assertEqual(automatic["code"], "automatic_balance")
        for value in (0, -1, "bad", float("nan")):
            status = TradingAmountService.status(
                {"trade_mode": "manual", "trade_amount": value, "amount_updated_at_utc": now.isoformat()},
                max_age_seconds=60,
                now=now,
            )
            self.assertFalse(status["eligible"])
        stale = TradingAmountService.status(
            {"trade_mode": "manual", "trade_amount": 500, "amount_updated_at_utc": (now - timedelta(seconds=61)).isoformat()},
            max_age_seconds=60,
            now=now,
        )
        self.assertEqual(stale["code"], "amount_stale")

    def test_margin_allocation_uses_dhan_margin_and_leverage_cap(self):
        runner = object.__new__(MultiStockAgentRunner)
        runner.config = SimpleNamespace(
            intra_finder_max_slippage_percent=1.0,
            stock_agent_max_leverage=5.0,
        )
        runner._calculate_one_share_margin = lambda *_args: {
            "status": "success",
            "total_margin": 100.0,
        }
        base = {"price": 500.0, "direction": "LONG", "five_level_depth": DEPTH}
        rejected = runner.prepare_user_event(base, {"user_id": "small", "trade_mode": "manual", "amount_source": "user_amount", "trade_amount": 499.99})
        equal = runner.prepare_user_event(base, {"user_id": "equal", "trade_mode": "manual", "amount_source": "user_amount", "trade_amount": 500.0})
        below = runner.prepare_user_event(base, {"user_id": "larger", "trade_mode": "manual", "amount_source": "user_amount", "trade_amount": 1000.0})
        self.assertTrue(rejected["eligible"])
        self.assertEqual(rejected["requested_quantity"], 4)
        self.assertTrue(equal["eligible"])
        self.assertEqual(equal["requested_quantity"], 5)
        self.assertTrue(below["eligible"])
        self.assertEqual(below["requested_quantity"], 10)

    def test_multi_user_amounts_are_isolated(self):
        now = datetime.now(timezone.utc).isoformat()
        with (
            patch.object(ConvexService, "configured", return_value=False),
            patch.object(ConvexService, "required", return_value=False),
            tempfile.TemporaryDirectory() as directory,
        ):
            path = Path(directory) / "state.json"
            AITradingStateService.set_user_state(path, "small", True, {"trade_amount": 100, "amount_updated_at_utc": now})
            AITradingStateService.set_user_state(path, "large", True, {"trade_amount": 1000, "amount_updated_at_utc": now})
            AITradingStateService.set_user_state(path, "auto", True, {"trade_mode": "auto", "trade_amount": None, "amount_updated_at_utc": now})
            users = AITradingStateService.configured_users(path, max_age_seconds=60)
        self.assertEqual({row["user_id"]: row["trade_amount"] for row in users}, {"small": 100.0, "large": 1000.0, "auto": None})

    def test_auto_mode_resolves_current_available_balance(self):
        runner = object.__new__(MultiStockAgentRunner)
        runner.config = SimpleNamespace(stock_agent_max_concurrent_trades=3)
        runner._build_sizing_account_context = lambda: {"funds": {"data": {"availabelBalance": 1250.0}}}
        resolved = runner.resolve_user_trade_config({"user_id": "auto", "trade_mode": "auto"})
        self.assertTrue(resolved["eligible"])
        self.assertEqual(resolved["trade_amount"], 416.66)
        self.assertEqual(resolved["amount_source"], "available_balance")

    def test_auto_mode_fails_closed_when_balance_is_unavailable(self):
        runner = object.__new__(MultiStockAgentRunner)
        runner.config = SimpleNamespace(stock_agent_max_concurrent_trades=3)
        runner._build_sizing_account_context = lambda: {"funds": {"data": {}}}
        resolved = runner.resolve_user_trade_config({"user_id": "auto", "trade_mode": "auto"})
        self.assertFalse(resolved["eligible"])
        self.assertEqual(resolved["status_code"], "available_balance_unavailable")

    def test_fixed_mode_derives_dynamic_trade_limit_from_account_capacity(self):
        runner = object.__new__(MultiStockAgentRunner)
        runner.config = SimpleNamespace(stock_agent_max_concurrent_trades=3)
        runner._build_sizing_account_context = lambda: {
            "funds": {
                "data": {
                    "availabelBalance": 2000.0,
                    "utilizedAmount": 0.0,
                    "sodLimit": 2000.0,
                }
            }
        }

        expected = {500: 4, 1000: 2, 1500: 1}
        for amount, slots in expected.items():
            with self.subTest(amount=amount):
                resolved = runner.resolve_user_trade_config(
                    {"user_id": "fixed", "trade_mode": "manual", "trade_amount": amount}
                )
                self.assertTrue(resolved["eligible"])
                self.assertEqual(resolved["max_concurrent_trades"], slots)

        runner._build_sizing_account_context = lambda: {
            "funds": {
                "data": {
                    "availabelBalance": 10000.0,
                    "utilizedAmount": 0.0,
                    "sodLimit": 10000.0,
                }
            }
        }
        resolved = runner.resolve_user_trade_config(
            {"user_id": "fixed", "trade_mode": "manual", "trade_amount": 500}
        )
        self.assertEqual(resolved["max_concurrent_trades"], 20)

    def test_fixed_mode_capacity_includes_margin_already_utilized(self):
        runner = object.__new__(MultiStockAgentRunner)
        runner.config = SimpleNamespace(stock_agent_max_concurrent_trades=3)
        runner._build_sizing_account_context = lambda: {
            "funds": {
                "data": {
                    "availabelBalance": 8500.0,
                    "utilizedAmount": 1500.0,
                    "sodLimit": 10000.0,
                }
            }
        }

        resolved = runner.resolve_user_trade_config(
            {"user_id": "fixed", "trade_mode": "manual", "trade_amount": 500}
        )

        self.assertEqual(resolved["account_margin_capacity"], 10000.0)
        self.assertEqual(resolved["max_concurrent_trades"], 20)

    def test_quantity_is_cash_based_without_leverage(self):
        self.assertEqual(TradingAmountService.quantity(499.99, 500), 0)
        self.assertEqual(TradingAmountService.quantity(500, 500), 1)
        self.assertEqual(TradingAmountService.quantity(1099, 500), 2)

    def test_event_agent_session_carries_and_requires_user_id(self):
        runner = object.__new__(MultiStockAgentRunner)
        runner.config = SimpleNamespace(ai_trading_state_path=Path("unused-state.json"))
        runner.market_time = SimpleNamespace(market_date_str=lambda: "2026-08-12")
        runner._build_account_context = lambda: {}
        runner._build_candidate_packet = lambda **kwargs: {"security_id": 1}
        runner._strip_monitor_context = lambda packet: None
        runner._is_placed_result = lambda result: False
        runner._save_payload = lambda payload: None
        captured = {}

        def run_agents(packets, trade_config, event_callback, run_context):
            captured.update(run_context)
            return [{"decision": {"status": "no_trade"}}]

        runner._run_stock_agents = run_agents
        event = {
            "event_id": "event-123",
            "market_date": "2026-08-12",
            "exchange_segment": "NSE_EQ",
        }
        with patch.object(AITradingStateService, "is_any_user_enabled", return_value=True):
            runner.run_event(event, user_id="user-123", trade_config={"trade_amount": 500})
            self.assertEqual(captured["user_id"], "user-123")
            with self.assertRaisesRegex(RuntimeError, "user_id_required_for_agent_session"):
                runner.run_event(event, user_id=None, trade_config={"trade_amount": 500})


if __name__ == "__main__":
    unittest.main()
