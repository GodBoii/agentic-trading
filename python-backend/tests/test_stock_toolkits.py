import asyncio
import json
from pathlib import Path
import threading
import time
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd

from pipeline.services.charting_service import CandlestickChartService
from pipeline.services.nifty_depth_charting import NiftyDepthChartGenerator
from pipeline.services.nifty_depth_monitor import NiftyDepthMonitor
from pipeline.stock.stock_agent import StockAgent
from pipeline.stock.toolkits import (
    StockAccountToolkit,
    StockExecutionCoordinator,
    StockExecutionToolkit,
    StockMarketDataToolkit,
    StockTechnicalToolkit,
)
try:
    from pipeline.stock.toolkits.research_toolkit import StockResearchToolkit
    from agno.tools.websearch import WebSearchTools
except ImportError:
    StockResearchToolkit = None
    WebSearchTools = None


class FakeStockDhan:
    def __init__(self, margin_required=20.0, include_selected_position=True, order_status="TRANSIT", current_ltp=100.0, fund_balance=1000.0):
        self.margin_required = margin_required
        self.include_selected_position = include_selected_position
        self.order_status = order_status
        self.super_order_calls = 0
        self.current_ltp = current_ltp
        self.fund_balance = fund_balance

    def fetch_quote_batch(self, security_ids, **_kwargs):
        return {int(security_id): {"last_price": self.current_ltp} for security_id in security_ids}

    def calculate_margin_requirement(self, **_kwargs):
        return {"status": "success", "data": {"totalMargin": self.margin_required}}

    def fetch_positions(self):
        selected = (
            [
                {
                    "securityId": "111",
                    "productType": "INTRADAY",
                    "netQty": 2,
                    "positionType": "LONG",
                }
            ]
            if self.include_selected_position
            else []
        )
        return {
            "status": "success",
            "data": [
                *selected,
                {
                    "securityId": "999",
                    "productType": "INTRADAY",
                    "netQty": -3,
                    "positionType": "SHORT",
                },
            ],
        }

    def fetch_order_book(self):
        return {
            "status": "success",
            "data": [
                {
                    "securityId": "999",
                    "orderId": "other-order-secret",
                    "orderStatus": "PENDING",
                }
            ],
        }

    def fetch_super_orders(self):
        if self.super_order_calls <= 0:
            return {"status": "success", "data": []}
        return {
            "status": "success",
            "data": [
                {
                    "securityId": "111",
                    "orderId": "order-123",
                    "orderStatus": self.order_status,
                    "quantity": 2,
                    "filledQty": 2 if self.order_status == "TRADED" else 0,
                }
            ],
        }

    def fetch_fund_limits(self):
        return {
            "status": "success",
            "data": {
                "dhanClientId": "private-client-id",
                "availabelBalance": self.fund_balance,
                "utilizedAmount": 100.0,
            },
        }

    def place_super_order(self, **kwargs):
        self.super_order_calls += 1
        return {
            "status": "success",
            "data": {"orderId": "order-123"},
            "received": kwargs,
        }


class ConcurrentFakeStockDhan(FakeStockDhan):
    def __init__(self):
        super().__init__(margin_required=20.0, include_selected_position=False)
        self.activity_lock = threading.Lock()
        self.active_calls = 0
        self.max_active_calls = 0

    def _enter(self):
        with self.activity_lock:
            self.active_calls += 1
            self.max_active_calls = max(self.max_active_calls, self.active_calls)
        time.sleep(0.01)

    def _exit(self):
        with self.activity_lock:
            self.active_calls -= 1

    def calculate_margin_requirement(self, **kwargs):
        self._enter()
        try:
            return super().calculate_margin_requirement(**kwargs)
        finally:
            self._exit()

    def place_super_order(self, **kwargs):
        self._enter()
        try:
            return super().place_super_order(**kwargs)
        finally:
            self._exit()


class FreshStateDhan(FakeStockDhan):
    def __init__(self, frame):
        super().__init__(include_selected_position=False)
        self.frame = frame
        self.history_calls = 0

    def fetch_quote_batch(self, *_args, **_kwargs):
        return {
            111: {
                "last_price": 101.25,
                "last_trade_time": "28/07/2026 12:59:58",
                "volume": 5000,
                "depth": {
                    "buy": [{"price": 101.2, "quantity": 50, "orders": 2}],
                    "sell": [{"price": 101.25, "quantity": 40, "orders": 2}],
                },
                "ohlc": {"open": 100.0, "high": 102.0, "low": 99.5, "close": 100.5},
            }
        }

    def fetch_ohlc_batch(self, *_args, **_kwargs):
        return {}

    def fetch_intraday_history(self, *_args, **_kwargs):
        self.history_calls += 1
        return {"status": "success", "data": "fresh"}

    def intraday_response_to_df(self, _response):
        return self.frame.copy()


class StockToolkitTests(unittest.TestCase):
    def test_depth_monitor_awaits_async_disconnect_fallback(self):
        class AsyncDisconnectFeed:
            def __init__(self):
                self.loop = asyncio.new_event_loop()
                self.disconnected = False

            def close_connection(self):
                raise RuntimeError("primary close failed")

            async def disconnect(self):
                self.disconnected = True

        feed = AsyncDisconnectFeed()
        try:
            monitor = object.__new__(NiftyDepthMonitor)
            monitor._close_feed(feed)
            self.assertTrue(feed.disconnected)
        finally:
            feed.loop.close()

    def test_depth_monitor_disables_sdk_pong_timeout(self):
        websocket = SimpleNamespace(ping_timeout=20)
        NiftyDepthMonitor._configure_depth_websocket(SimpleNamespace(ws=websocket))
        self.assertIsNone(websocket.ping_timeout)

    def test_chart_indicators_remain_unavailable_until_enough_candles_exist(self):
        frame = pd.DataFrame(
            {
                "open": [100.0] * 10,
                "high": [101.0] * 10,
                "low": [99.0] * 10,
                "close": [100.0] * 10,
            }
        )

        enriched = CandlestickChartService("Asia/Calcutta")._compute_full_indicators(frame)

        self.assertTrue(enriched["rsi"].isna().all())
        self.assertTrue(enriched["bb_upper"].isna().all())
        self.assertTrue(enriched["bb_lower"].isna().all())

    def test_chart_bundle_labels_exact_data_timestamp(self):
        market_tz = ZoneInfo("Asia/Kolkata")
        timestamps = []
        for day in (27, 28):
            start = datetime(2026, 7, day, 9, 15, tzinfo=market_tz).astimezone(timezone.utc)
            timestamps.extend(start + timedelta(minutes=index) for index in range(30))
        frame = pd.DataFrame(
            {
                "timestamp": [value.replace(tzinfo=None) for value in timestamps],
                "open": [100.0] * 60,
                "high": [101.0] * 60,
                "low": [99.0] * 60,
                "close": [100.5] * 60,
                "volume": [100] * 60,
            }
        )
        service = CandlestickChartService("Asia/Calcutta")
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(service, "_render_chart"), \
                 patch.object(service, "_render_volume_participation_chart", return_value={}), \
                 patch.object(service, "_render_momentum_volatility_chart", return_value={}), \
                 patch.object(service, "_render_price_structure_liquidity_chart", return_value={}), \
                 patch.object(service, "_render_tpo_profile_chart", return_value={}):
                bundle = service.build_intraday_chart_set(
                    frame,
                    "Test Limited",
                    "2026-07-28",
                    Path(temp_dir),
                )

        self.assertIn("2026-07-28T09:44:00+05:30", bundle["data_as_of_ist"])
        self.assertEqual(
            bundle["charts"]["current_5m"]["data_as_of_ist"],
            bundle["data_as_of_ist"],
        )
        self.assertEqual(
            bundle["technical_metadata"]["data_as_of_ist"],
            bundle["data_as_of_ist"],
        )
        self.assertEqual(bundle["chart_contract_version"], "stock-evidence-v4")
        self.assertEqual(
            list(bundle["charts"]),
            [
                "current_1m",
                "current_5m",
                "current_15m",
                "previous_5m",
                "previous_15m",
                "volume_participation",
                "momentum_volatility",
                "price_structure_liquidity",
                "tpo_profile",
            ],
        )
        self.assertEqual(bundle["chart_count"], 9)
        self.assertNotIn("cvd_direction", bundle["technical_metadata"])

    def test_nifty_trade_tick_zero_delta_is_not_recounted_from_ltq(self):
        monitor = object.__new__(NiftyDepthMonitor)
        monitor.last_trade_fingerprint = None
        tick = {
            "latest_price": 24000.0,
            "last_traded_quantity": 65,
            "last_trade_time": "14:30:01",
            "volume": 123456,
            "volume_delta": 0,
        }

        self.assertEqual(monitor._tick_quantity(tick), 0.0)
        self.assertFalse(monitor._should_write_trade_tick(tick))
        self.assertFalse(monitor._should_write_trade_tick(tick))

    def test_nifty_chart_window_uses_only_common_depth_trade_coverage(self):
        generator = object.__new__(NiftyDepthChartGenerator)
        generator.chart_window_minutes = 15
        market_tz = ZoneInfo("Asia/Kolkata")
        base = pd.Timestamp(datetime(2026, 7, 28, 14, 40, tzinfo=market_tz))
        depth = pd.DataFrame(
            {
                "timestamp": [base + pd.Timedelta(minutes=value) for value in (8, 12, 17)],
                "price": [24000.0, 24001.0, 24002.0],
            }
        )
        quotes = pd.DataFrame(
            {"best_bid": [23999.0, 24000.0, 24001.0]},
            index=depth["timestamp"],
        )
        trades = pd.DataFrame(
            {
                "timestamp": [base + pd.Timedelta(minutes=value) for value in (0, 10, 17)],
                "price": [23995.0, 23998.0, 24002.0],
            }
        )

        synced_depth, synced_quotes, synced_trades = generator._synchronize_chart_window(
            depth,
            quotes,
            trades,
        )

        common_start = base + pd.Timedelta(minutes=8)
        self.assertGreaterEqual(synced_depth["timestamp"].min(), common_start)
        self.assertGreaterEqual(synced_trades["timestamp"].min(), common_start)
        self.assertGreaterEqual(synced_quotes.index.min(), common_start)

    def test_agent_prompt_is_small_and_does_not_expose_pipeline_sections(self):
        execution = StockExecutionToolkit(FakeStockDhan(), 111, 500)
        agent = StockAgent([execution])
        prompt = agent._build_prompt(
            {
                "selected_stock": {
                    "security_id": 111,
                    "symbol": "TEST",
                    "display_name": "Test Limited",
                },
                "timing_context": {
                    "current_market_time_ist": "2026-07-28T10:05:00+05:30",
                    "market_session": {
                        "regular_session": "09:15-15:30 IST",
                        "is_open_now": True,
                        "minutes_to_close": 325,
                    },
                },
            }
        )

        self.assertIn("Test Limited", prompt)
        self.assertNotIn("Stage 2", prompt)
        self.assertNotIn("rank", prompt.lower())
        self.assertNotIn("Technical Metadata", prompt)
        self.assertNotIn("Output Requirements", prompt)
        self.assertNotIn("execution", prompt.lower())
        self.assertNotIn("setup", prompt.lower())

    def test_stream_tool_events_capture_result_size_status_and_summary(self):
        agent = StockAgent([])
        tool = SimpleNamespace(
            tool_call_id="call-1",
            tool_name="get_current_stock_state",
            tool_args={},
            tool_call_error=False,
            result=json.dumps({"status": "partial", "missing_fields": ["quote"]}),
            metrics=SimpleNamespace(duration=0.25),
        )
        event = SimpleNamespace(
            event="ToolCallCompleted",
            run_id="run-1",
            created_at=1,
            tool=tool,
            error=None,
        )

        normalized = agent._normalize_stream_event(event)
        summary = agent._build_tool_summary([normalized])

        self.assertEqual(normalized["type"], "stock_agent_tool_call_completed")
        self.assertTrue(normalized["result_partial"])
        self.assertEqual(normalized["duration_seconds"], 0.25)
        self.assertGreater(normalized["result_length"], 0)
        self.assertEqual(summary["tool_calls"], 1)
        self.assertEqual(summary["partial"], 1)
        self.assertEqual(summary["succeeded"], 0)

    def test_tpo_initial_balance_uses_first_clock_hour_not_first_sixty_rows(self):
        market_tz = ZoneInfo("Asia/Kolkata")
        timestamps = [
            datetime(2026, 7, 28, 9, 15, tzinfo=market_tz) + timedelta(minutes=index * 2)
            for index in range(70)
        ]
        frame = pd.DataFrame(
            {
                "open": [100.0] * 70,
                "high": [101.0] * 30 + [120.0] * 40,
                "low": [99.0] * 70,
                "close": [100.0] * 70,
                "volume": [10] * 70,
            },
            index=pd.DatetimeIndex(timestamps),
        )

        profile = CandlestickChartService("Asia/Calcutta")._build_tpo_profile(frame)

        self.assertEqual(profile["initial_balance_high"], 101.0)

    def test_account_overview_hides_other_trade_details_and_client_id(self):
        payload = json.loads(StockAccountToolkit(FakeStockDhan(), 111, 500).get_account_overview())

        self.assertTrue(payload["assigned_stock_overlap"]["has_open_intraday_position"])
        self.assertEqual(payload["other_live_activity"]["open_intraday_position_count"], 1)
        self.assertEqual(payload["other_live_activity"]["active_order_count"], 1)
        serialized = json.dumps(payload)
        self.assertNotIn("other-order-secret", serialized)
        self.assertNotIn("private-client-id", serialized)
        self.assertNotIn('"999"', serialized)

    def test_technical_tool_omits_indicators_without_enough_candles(self):
        payload = json.loads(
            StockTechnicalToolkit(
                {
                    "market_date": "2026-07-28",
                    "charts": {"current_5m": {"candles": 10}},
                    "technical_metadata": {
                        "latest_price": 100.0,
                        "rsi": 50.0,
                        "bb_upper": None,
                        "bb_lower": None,
                    },
                }
            ).get_technical_data()
        )

        self.assertEqual(payload["readings"]["latest_price"], 100.0)
        self.assertNotIn("rsi", payload["readings"])
        self.assertNotIn("bb_upper", payload["readings"])

    def test_security_overview_normalizes_bse_tick_size_from_paise(self):
        market_time = SimpleNamespace()
        toolkit = StockMarketDataToolkit(
            FakeStockDhan(),
            market_time,
            security_id=111,
            symbol="TEST",
            display_name="Test Limited",
            stock_context={
                "stock": {
                    "price": 100.0,
                    "static_tradability": {"tick_size": 5, "lot_size": 1},
                },
                "stage2": {
                    "time_of_day_rvol": 1.8,
                    "opening_range_breakout_percent": 0.7,
                    "volume_acceleration_ratio": 1.4,
                },
            },
        )

        payload = json.loads(toolkit.get_security_overview())
        self.assertEqual(payload["tradability"]["tick_size_rupees"], 0.05)
        self.assertEqual(payload["stage2_momentum_snapshot"]["time_of_day_rvol"], 1.8)
        self.assertEqual(
            payload["stage2_momentum_snapshot"]["opening_range_breakout_percent"],
            0.7,
        )

    def test_duplicative_live_and_ohlc_tools_are_not_exposed(self):
        market_tz = ZoneInfo("Asia/Kolkata")
        now = datetime(2026, 7, 28, 12, 55, tzinfo=market_tz)
        previous_start = datetime(2026, 7, 27, 9, 15, tzinfo=market_tz).astimezone(timezone.utc)
        current_start = datetime(2026, 7, 28, 9, 15, tzinfo=market_tz).astimezone(timezone.utc)
        timestamps = [
            *(previous_start + timedelta(minutes=index) for index in range(5)),
            *(current_start + timedelta(minutes=index) for index in range(70)),
        ]
        frame = pd.DataFrame(
            {
                "timestamp": [value.replace(tzinfo=None) for value in timestamps],
                "open": [100.0] * 75,
                "high": [101.0] * 75,
                "low": [99.0] * 75,
                "close": [100.5] * 75,
                "volume": [10] * 75,
            }
        )
        market_time = SimpleNamespace(
            tz=market_tz,
            now=lambda: now,
            config=SimpleNamespace(
                market_open_hour=9,
                market_open_minute=15,
                market_close_hour=15,
                market_close_minute=30,
            ),
        )
        toolkit = StockMarketDataToolkit(
            FakeStockDhan(),
            market_time,
            security_id=111,
            symbol="TEST",
            display_name="Test Limited",
            intraday_frame=frame,
        )

        self.assertFalse(hasattr(toolkit, "get_ohlc_snapshot"))
        self.assertFalse(hasattr(toolkit, "get_live_market_snapshot"))

    def test_final_stock_state_forces_new_quote_and_history(self):
        market_tz = ZoneInfo("Asia/Kolkata")
        now = datetime(2026, 7, 28, 13, 0, tzinfo=market_tz)
        timestamps = [
            datetime(2026, 7, 28, 12, 57, tzinfo=market_tz).astimezone(timezone.utc),
            datetime(2026, 7, 28, 12, 58, tzinfo=market_tz).astimezone(timezone.utc),
            datetime(2026, 7, 28, 12, 59, tzinfo=market_tz).astimezone(timezone.utc),
        ]
        fresh_frame = pd.DataFrame(
            {
                "timestamp": [value.replace(tzinfo=None) for value in timestamps],
                "open": [100.0, 100.5, 101.0],
                "high": [100.75, 101.25, 101.5],
                "low": [99.75, 100.25, 100.75],
                "close": [100.5, 101.0, 101.25],
                "volume": [100, 200, 300],
            }
        )
        dhan = FreshStateDhan(fresh_frame)
        market_time = SimpleNamespace(
            tz=market_tz,
            now=lambda: now,
            config=SimpleNamespace(
                market_open_hour=9,
                market_open_minute=15,
                market_close_hour=15,
                market_close_minute=30,
            ),
        )
        stale_frame = fresh_frame.iloc[:1].copy()
        toolkit = StockMarketDataToolkit(
            dhan,
            market_time,
            security_id=111,
            symbol="TEST",
            display_name="Test Limited",
            intraday_frame=stale_frame,
        )

        payload = json.loads(toolkit.get_current_stock_state())

        self.assertEqual(payload["status"], "success")
        self.assertEqual(dhan.history_calls, 1)
        self.assertEqual(payload["quote"]["last_price"], 101.25)
        self.assertIn("12:59:00", payload["candle_data_as_of_ist"])
        self.assertEqual(payload["one_minute"]["latest_completed"]["close"], 101.25)
        self.assertNotIn("recent_1m_candles", payload)
        self.assertNotIn("recent_5m_candles", payload)

    @unittest.skipIf(StockResearchToolkit is None, "optional ddgs dependency is not installed")
    def test_news_tool_removes_future_dated_results(self):
        market_time = SimpleNamespace(
            now=lambda: datetime(
                2026,
                7,
                28,
                13,
                0,
                tzinfo=ZoneInfo("Asia/Kolkata"),
            )
        )
        toolkit = StockResearchToolkit("Test Limited", "TEST", market_time=market_time)
        source = json.dumps(
            [
                {"date": "2026-07-28T05:00:00+00:00", "title": "Current"},
                {"date": "2026-10-03T00:00:00+00:00", "title": "Future"},
            ]
        )

        with patch.object(WebSearchTools, "search_news", return_value=source):
            results = json.loads(toolkit.search_news("latest"))

        self.assertEqual([item["title"] for item in results], ["Current"])

    def test_execution_state_comes_from_tool_result_not_agent_prose(self):
        dhan = FakeStockDhan(margin_required=20.0, include_selected_position=False)
        toolkit = StockExecutionToolkit(dhan, 111, 500)
        toolkit._dhan_tools.allow_live_orders = True

        response = json.loads(
            toolkit.place_protected_intraday_order(
                side="BUY",
                quantity=2,
                entry_price=100.0,
                target_price=105.0,
                stop_loss_price=98.0,
            )
        )
        decision = toolkit.decision_snapshot("Test Limited")

        self.assertEqual(response["status"], "success")
        self.assertEqual(decision["action"], "pending")
        self.assertEqual(decision["execution_status"], "pending")
        self.assertEqual(decision["broker_order_status"], "TRANSIT")
        self.assertEqual(decision["filled_quantity"], 0)
        self.assertEqual(decision["order_id"], "order-123")
        self.assertEqual(dhan.super_order_calls, 1)

        second_response = json.loads(
            toolkit.place_intraday_order(
                side="BUY",
                quantity=1,
                reference_price=100.0,
            )
        )
        self.assertEqual(second_response["remarks"], "entry_order_already_placed")
        self.assertEqual(toolkit.decision_snapshot("Test Limited")["execution_status"], "pending")

    def test_only_traded_order_is_reported_as_executed(self):
        dhan = FakeStockDhan(
            margin_required=20.0,
            include_selected_position=False,
            order_status="TRADED",
        )
        toolkit = StockExecutionToolkit(dhan, 111, 500)
        toolkit._dhan_tools.allow_live_orders = True

        toolkit.place_protected_intraday_order(
            side="BUY",
            quantity=2,
            entry_price=100.0,
            target_price=105.0,
            stop_loss_price=98.0,
        )
        decision = toolkit.decision_snapshot("Test Limited")

        self.assertEqual(decision["action"], "trade")
        self.assertEqual(decision["execution_status"], "traded")
        self.assertEqual(decision["broker_order_status"], "TRADED")
        self.assertEqual(decision["filled_quantity"], 2)

    def test_execution_blocks_quantity_over_bound_margin_budget(self):
        dhan = FakeStockDhan(margin_required=600.0, include_selected_position=False)
        toolkit = StockExecutionToolkit(dhan, 111, 500)
        toolkit._dhan_tools.allow_live_orders = True

        response = json.loads(
            toolkit.place_protected_intraday_order(
                side="BUY",
                quantity=1,
                entry_price=100.0,
                target_price=105.0,
                stop_loss_price=98.0,
            )
        )
        decision = toolkit.decision_snapshot("Test Limited")

        self.assertEqual(response["status"], "blocked")
        self.assertEqual(decision["execution_status"], "blocked")
        self.assertEqual(dhan.super_order_calls, 0)

    def test_execution_revalidates_current_ltp_against_cash_amount(self):
        dhan = FakeStockDhan(margin_required=20.0, include_selected_position=False, current_ltp=501.0)
        toolkit = StockExecutionToolkit(dhan, 111, 500)
        toolkit._dhan_tools.allow_live_orders = True

        response = json.loads(toolkit.place_protected_intraday_order(
            side="BUY", quantity=1, entry_price=490.0, target_price=510.0, stop_loss_price=480.0,
        ))

        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["remarks"], "current_price_exceeds_trading_amount")
        self.assertEqual(response["current_ltp"], 501.0)
        self.assertEqual(dhan.super_order_calls, 0)

    def test_auto_execution_revalidates_current_available_balance(self):
        dhan = FakeStockDhan(margin_required=20.0, include_selected_position=False, current_ltp=100.0, fund_balance=90.0)
        toolkit = StockExecutionToolkit(dhan, 111, 500, amount_source="available_balance")
        toolkit._dhan_tools.allow_live_orders = True

        response = json.loads(toolkit.place_protected_intraday_order(
            side="BUY", quantity=1, entry_price=100.0, target_price=105.0, stop_loss_price=98.0,
        ))

        self.assertEqual(response["status"], "blocked")
        self.assertEqual(response["effective_current_cap"], 90.0)
        self.assertEqual(response["amount_source"], "available_balance")
        self.assertEqual(dhan.super_order_calls, 0)

    def test_shared_execution_coordinator_serializes_final_checks_and_placements(self):
        dhan = ConcurrentFakeStockDhan()
        coordinator = StockExecutionCoordinator()
        first = StockExecutionToolkit(dhan, 111, 500, coordinator=coordinator)
        second = StockExecutionToolkit(dhan, 222, 500, coordinator=coordinator)
        first._dhan_tools.allow_live_orders = True
        second._dhan_tools.allow_live_orders = True

        def place(toolkit, entry):
            toolkit.place_protected_intraday_order(
                side="BUY",
                quantity=1,
                entry_price=entry,
                target_price=entry + 2,
                stop_loss_price=entry - 1,
            )

        threads = [
            threading.Thread(target=place, args=(first, 100.0)),
            threading.Thread(target=place, args=(second, 200.0)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(dhan.max_active_calls, 1)
        self.assertEqual(len(coordinator.successful_orders), 2)


if __name__ == "__main__":
    unittest.main()
