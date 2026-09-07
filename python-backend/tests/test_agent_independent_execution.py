from __future__ import annotations

import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pipeline.runtime.run_stock_agent import MultiStockAgentRunner
from pipeline.services.trade_capacity import account_capital, available_balance, effective_trade_slot_limit, trade_slot_limit
from pipeline.stock.stock_agent import StockAgent
from pipeline.stock.toolkits import StockExecutionCoordinator, StockExecutionToolkit, StockMarketDataToolkit


class Account:
    def __init__(self, capital=1900, active=0):
        self.capital = capital
        self.active = active
        self.orders = 0
        self.reject = False

    def fetch_positions(self):
        return {"status": "success", "data": [
            {"securityId": str(i + 100), "exchangeSegment": "NSE_EQ", "productType": "INTRADAY", "netQty": 1}
            for i in range(self.active)
        ]}

    def fetch_order_book(self):
        return {"status": "success", "data": []}

    fetch_super_orders = fetch_order_book

    def fetch_fund_limits(self):
        return {"status": "success", "data": {"availabelBalance": self.capital}}

    def fetch_quote_batch(self, *_args, **_kwargs):
        return {1: {"last_price": 100}, 2: {"last_price": 100}}

    def calculate_margin_requirement(self, **_kwargs):
        return {"status": "success", "data": {"totalMargin": 20}}

    def place_super_order(self, **_kwargs):
        self.orders += 1
        if self.reject:
            return {"status": "success", "data": {"orderId": str(self.orders), "orderStatus": "REJECTED"}}
        return {"status": "success", "data": {"orderId": str(self.orders), "orderStatus": "PENDING"}}


def execution(account, coordinator=None, security_id=1, **kwargs):
    tool = StockExecutionToolkit(
        account, security_id, 500, exchange_segment="NSE_EQ", amount_source="available_balance",
        coordinator=coordinator or StockExecutionCoordinator(account_scoped=True),
        balance_based_capacity=True, **kwargs,
    )
    tool._dhan_tools.allow_live_orders = True
    return tool


class IndependentExecutionTests(unittest.TestCase):
    def test_tier_boundaries_and_invalid_funds(self):
        for capital, expected in [(0, 0), (-1, 0), (float("nan"), 0), (float("inf"), 0), (1999.99, 3), (2000, 5), (5000, 5), (5000.01, 10)]:
            with self.subTest(capital=capital):
                self.assertEqual(trade_slot_limit(capital), expected)
        self.assertEqual(account_capital({"availabelBalance": 1000, "utilizedAmount": 2500}), 3500)
        self.assertEqual(available_balance({"availabelBalance": 0, "withdrawableBalance": 5000}), 0)
        self.assertEqual(effective_trade_slot_limit(10000, 100), 10)
        self.assertEqual(effective_trade_slot_limit(2000, 1000), 2)

    def test_repeated_price_rejections_return_current_evidence_and_allow_recovery(self):
        account = Account()
        state = {"status": "success", "as_of_ist": "2026-09-07T10:00:00+05:30", "candle_data_age_seconds": 1,
                 "quote": {"last_price": 102, "last_trade_age_seconds": 1}, "one_minute": {"latest_completed": {"close": 102}}}
        tool = execution(account, final_state_loader=lambda: state)
        for _ in range(6):
            result = tool.place_protected_intraday_order("BUY", 1, 100, 110, 99)
            self.assertIn("final_price_drift_exceeds_limit", result)
            self.assertIn("current_market_state", result)
            self.assertIn("last_price: 102", result)
            self.assertIn("one_minute", result)
            self.assertIn("order_submitted: false", result)
        self.assertEqual(account.orders, 0)
        self.assertIn("status: success", tool.estimate_intraday_quantity("BUY", 102, 100))
        self.assertIn("status: success", tool.place_protected_intraday_order("BUY", 1, 102, 110, 100))
        self.assertIn("entry_order_already_placed", tool.place_protected_intraday_order("BUY", 1, 102, 110, 100))
        self.assertEqual(account.orders, 1)

    def test_confirmed_broker_rejections_do_not_impose_attempt_limit(self):
        account = Account()
        account.reject = True
        tool = execution(account)
        for _ in range(5):
            self.assertIn("REJECTED", tool.place_protected_intraday_order("SELL", 1, 100, 95, 101))
        self.assertEqual(account.orders, 5)

    def test_ambiguous_submission_cannot_create_duplicate(self):
        account = Account()
        account.place_super_order = Mock(side_effect=TimeoutError("broker acknowledgement missing"))
        tool = execution(account)
        with self.assertRaises(TimeoutError):
            tool.place_protected_intraday_order("BUY", 1, 100, 105, 98)
        self.assertIn("broker_submission_unresolved", tool.place_protected_intraday_order("BUY", 1, 100, 105, 98))
        self.assertEqual(account.place_super_order.call_count, 1)

    def test_concurrent_admissions_reserve_only_available_capacity(self):
        account = Account(active=2)
        coordinator = StockExecutionCoordinator(account_scoped=True)
        first, second = execution(account, coordinator, 1), execution(account, coordinator, 2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda tool: tool.reserve_analysis_slot(), [first, second]))
        self.assertEqual(results.count(None), 1)
        self.assertEqual(len(coordinator.analysis_slots), 1)
        first.release_analysis_slot()
        second.release_analysis_slot()
        self.assertEqual(coordinator.analysis_slots, set())

    def test_accounts_and_pending_orders_are_isolated(self):
        one, two = Account(), Account()
        coordinator = StockExecutionCoordinator(account_scoped=True)
        tool = execution(one, coordinator)
        tool.place_protected_intraday_order("BUY", 1, 100, 105, 98)
        self.assertIn("assigned_stock_active_order_exists", execution(one, coordinator).reserve_analysis_slot())
        self.assertIsNone(execution(two).reserve_analysis_slot())

    def test_final_capacity_rechecks_changed_balance(self):
        account = Account(capital=6000, active=3)
        tool = execution(account)
        self.assertIsNone(tool.reserve_analysis_slot())
        self.assertEqual(tool.last_capacity["max_concurrent_trades"], 10)
        account.capital = 1900
        result = tool.place_protected_intraday_order("BUY", 1, 100, 105, 98)
        self.assertIn("maximum_concurrent_trade_slots_in_use", result)
        self.assertEqual(account.orders, 0)
        tool.release_analysis_slot()

    def test_full_account_never_starts_chart_or_model_work(self):
        runner = MultiStockAgentRunner.__new__(MultiStockAgentRunner)
        account = Account(active=3)
        runner.user_dhan = SimpleNamespace(service=lambda _user: account)
        runner._run_admitted_stock_agent = Mock()
        runner._resolve_margin_budget = lambda *_args: 500
        result = runner._run_single_stock_agent(0, {"security_id": 1, "exchange_segment": "NSE_EQ"}, {"user_id": "one", "amount_source": "available_balance"})
        self.assertEqual(result["decision"]["active_trade_count"], 3)
        self.assertEqual(result["decision"]["max_concurrent_trades"], 3)
        runner._run_admitted_stock_agent.assert_not_called()

    def test_failed_analysis_releases_reservation(self):
        runner = MultiStockAgentRunner.__new__(MultiStockAgentRunner)
        runner.user_dhan = SimpleNamespace(service=lambda _user: Account())
        runner._resolve_margin_budget = lambda *_args: 500
        runner._run_admitted_stock_agent = Mock(side_effect=RuntimeError("chart upload failed"))
        coordinator = StockExecutionCoordinator(account_scoped=True)
        with self.assertRaisesRegex(RuntimeError, "chart upload failed"):
            runner._run_single_stock_agent(0, {"security_id": 1, "exchange_segment": "NSE_EQ"}, {"amount_source": "available_balance"}, execution_coordinator=coordinator)
        self.assertEqual(coordinator.analysis_slots, set())

    def test_scanner_opinions_do_not_enter_agent_evidence(self):
        toolkit = StockMarketDataToolkit(Account(), SimpleNamespace(), 1, "TEST", "Test", exchange_segment="NSE_EQ", stock_context={
            "direction": "SHORT", "setup_type": "VWAP_REVERSION", "setup_score": 99,
            "explanation": "must be bearish", "indicator_snapshot": {"bias": "bearish"},
            "price": 100, "relative_volume": 3,
        })
        payload = json.dumps(toolkit.security_overview_payload())
        for opinion in ("SHORT", "VWAP_REVERSION", "setup_score", "bearish"):
            self.assertNotIn(opinion, payload)
        self.assertIn("relative_volume", payload)

    def test_admission_accepts_affordable_side_opposite_detector(self):
        runner = MultiStockAgentRunner.__new__(MultiStockAgentRunner)
        runner.user_dhan = SimpleNamespace(service=lambda _user: Account())
        runner.config = SimpleNamespace(stock_agent_max_leverage=5, intra_finder_max_slippage_percent=1)
        for direction, affordable_side in [("LONG", "SELL"), ("SHORT", "BUY")]:
            with self.subTest(direction=direction):
                runner._calculate_one_share_margin = lambda _event, side, *_args: {
                    "total_margin": 20 if side == affordable_side else 1000,
                }
                result = runner.prepare_user_event(
                    {"price": 100, "direction": direction, "five_level_depth": [
                        {"ask_price": 100, "ask_quantity": 100, "bid_price": 100, "bid_quantity": 100},
                    ]},
                    {"user_id": "test", "trade_amount": 500},
                )
                self.assertTrue(result["eligible"])

    def test_agent_framework_has_no_tool_call_limit(self):
        fake_agent = Mock()
        fake_agent.run.return_value = iter([SimpleNamespace(content="No trade", event="")])
        with patch("pipeline.stock.stock_agent.Agent", return_value=fake_agent) as factory, patch("pipeline.stock.stock_agent.create_multimodal_trading_model"), patch("pipeline.stock.stock_agent.CloudPersistenceService.agno_db"):
            StockAgent([]).analyze({}, [], {"agno_session_id": "test"})
        self.assertIsNone(factory.call_args.kwargs["tool_call_limit"])


if __name__ == "__main__":
    unittest.main()
