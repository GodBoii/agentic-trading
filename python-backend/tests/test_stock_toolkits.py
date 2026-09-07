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
from pipeline.stock.decision_context import StockDecisionContextBuilder
from pipeline.stock.stock_agent import StockAgent
from pipeline.stock.toolkits import (
    StockAccountToolkit,
    StockExecutionCoordinator,
    StockExecutionToolkit,
    StockMarketDataToolkit,
    StockTechnicalToolkit,
)
class FakeStockDhan:
    def __init__(self, margin_required=20.0, include_selected_position=True, order_status="TRANSIT", current_ltp=100.0, fund_balance=1000.0):
        self.margin_required = margin_required
        self.include_selected_position = include_selected_position
        self.order_status = order_status
        self.super_order_calls = 0
        self.last_super_order_kwargs = None
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
        self.last_super_order_kwargs = dict(kwargs)
        return {
            "status": "success",
            "data": {"orderId": "order-123"},
            "received": kwargs,
        }


class FakeOrderPlacementGate:
    def __init__(self):
        self.allowed = True
        self.placement_lock = threading.Lock()
        self.block_calls = 0
        self.reserved_security_ids = set()

    def block_from_order_response(self, _response):
        self.block_calls += 1
        self.allowed = False

    def reserve_trade_slot(self, security_id):
        self.reserved_security_ids.add(str(security_id))

    def active_trade_slots(self, broker_security_ids):
        return set(broker_security_ids) | self.reserved_security_ids


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
    def test_agent_can_choose_sell_independently(self):
        toolkit = StockExecutionToolkit(
            FakeStockDhan(include_selected_position=False),
            111,
            500,
        )

        toolkit._dhan_tools.allow_live_orders = True
        sizing = toolkit.estimate_intraday_quantity(
            side="SELL",
            reference_price=100,
            stop_loss_price=101,
        )
        placement = toolkit.place_protected_intraday_order(
            side="SELL",
            quantity=1,
            entry_price=100,
            target_price=99,
            stop_loss_price=101,
        )

        self.assertIn("- status: success", sizing)
        self.assertIn("- status: success", placement)

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
        self.assertEqual(bundle["chart_contract_version"], "stock-evidence-v6")
        self.assertEqual(
            list(bundle["charts"]),
            [
                "current_1m",
                "current_5m",
                "current_15m",
                "previous_15m",
                "volume_participation",
                "momentum_volatility",
                "price_structure_liquidity",
                "tpo_profile",
            ],
        )
        self.assertEqual(bundle["chart_count"], 8)
        self.assertNotIn("cvd_direction", bundle["technical_metadata"])

    def test_volume_chart_preserves_signal_timestamp_as_metadata_only(self):
        market_tz = ZoneInfo("Asia/Kolkata")
        rows = []
        for day in (20, 21, 22, 23):
            minutes = 375 if day < 23 else 120
            start = datetime(2026, 7, day, 9, 15, tzinfo=market_tz)
            for index in range(minutes):
                timestamp = start + timedelta(minutes=index)
                price = 100.0 + index * 0.001
                rows.append(
                    {
                        "timestamp": timestamp.astimezone(timezone.utc).replace(tzinfo=None),
                        "open": price,
                        "high": price + 0.05,
                        "low": price - 0.05,
                        "close": price + 0.01,
                        "volume": 1000 + (index % 10) * 50 + (day - 20) * 25,
                    }
                )
        service = CandlestickChartService("Asia/Kolkata")
        local = service._to_market_frame(pd.DataFrame(rows))
        today = service._day_frame(local, "2026-07-23")

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "volume.png"
            metadata = service._render_volume_participation_chart(
                local_frame=local,
                today_frame=today,
                display_name="Test Limited",
                market_date="2026-07-23",
                data_as_of=today.index[-1],
                output_path=output,
                signal_time_ist="2026-07-23T10:00:00+05:30",
            )

            self.assertTrue(output.exists())
        self.assertEqual(metadata["baseline_completed_sessions"], 3)
        self.assertIsNotNone(metadata["completed_5m_participation_impulse_3bar"])
        self.assertEqual(metadata["cumulative_volume_percentile_band"], "25th-75th")
        self.assertEqual(metadata["signal_time_ist"], "2026-07-23T10:00:00+05:30")

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

    def test_agent_prompt_contains_one_initial_decision_snapshot(self):
        execution = StockExecutionToolkit(FakeStockDhan(), 111, 500)
        agent = StockAgent([execution])
        prompt = agent._build_prompt(
            {
                "decision_context": {
                    "instrument": {
                        "security_id": 111,
                        "symbol": "TEST",
                        "display_name": "Test Limited",
                    },
                    "timestamps_and_session": {
                        "context_generated_at_ist": "2026-07-28T10:05:00+05:30",
                        "market_open_now": True,
                        "minutes_to_close": 325,
                    },
                },
            }
        )

        self.assertIn("Test Limited", prompt)
        self.assertEqual(prompt.count("## Initial decision snapshot"), 1)
        self.assertNotIn("rank", prompt.lower())
        self.assertNotIn("selected_stock", prompt)
        self.assertNotIn("timing_context", prompt)

    def test_execution_toolkit_exposes_only_sizing_and_protected_order(self):
        toolkit = StockExecutionToolkit(FakeStockDhan(), 111, 500)

        self.assertEqual(
            set(toolkit.functions),
            {"estimate_intraday_quantity", "place_protected_intraday_order"},
        )
        self.assertFalse(hasattr(toolkit, "place_intraday_order"))

    def test_quantity_uses_dhan_margin_and_configured_leverage(self):
        toolkit = StockExecutionToolkit(
            FakeStockDhan(margin_required=20.0, include_selected_position=False),
            111,
            500,
            max_leverage=5.0,
        )

        response = toolkit.estimate_intraday_quantity(
            side="BUY",
            reference_price=100.0,
            stop_loss_price=99.9,
        )

        self.assertIn("- broker_leverage: 5", response)
        self.assertIn("- max_qty_by_cash: 5", response)
        self.assertIn("- max_qty_by_margin: 25", response)
        self.assertIn("- recommended_quantity: 25", response)

    def test_stop_risk_can_reduce_leveraged_quantity(self):
        toolkit = StockExecutionToolkit(
            FakeStockDhan(margin_required=20.0, include_selected_position=False),
            111,
            500,
        )

        response = toolkit.estimate_intraday_quantity(
            side="BUY",
            reference_price=100.0,
            stop_loss_price=98.0,
            max_risk_rupees=10.0,
        )

        self.assertIn("- max_qty_by_risk: 5", response)
        self.assertIn("- recommended_quantity: 5", response)

    def test_decision_context_removes_duplicate_identity_price_vwap_and_budget(self):
        context = StockDecisionContextBuilder.build(
            selected_stock={
                "security_id": 111,
                "symbol": "TEST",
                "display_name": "Test Limited",
                "trade_amount": 500,
            },
            timing_context={
                "current_market_time_ist": "2026-07-28 10:05:00 IST",
                "market_session": {"is_open_now": True, "minutes_to_close": 325},
            },
            security_overview={
                "security_id": 111,
                "symbol": "TEST",
                "display_name": "Test Limited",
                "exchange_segment": "NSE_EQ",
                "market_evidence": {
                    "relative_volume": 1.4,
                    "volume_acceleration": 1.8,
                },
                "tradability": {"tick_size_rupees": 0.05, "upper_circuit": 120},
            },
            current_state={
                "status": "success",
                "source": "dhan_quote_and_intraday",
                "as_of_ist": "2026-07-28T10:05:01+05:30",
                "quote": {
                    "as_of_ist": "2026-07-28T10:05:01+05:30",
                    "last_price": 101,
                    "upper_circuit": 121,
                },
            },
            technical_data={
                "basis": "current 5-minute chart",
                "readings": {
                    "latest_price": 100,
                    "vwap": 99,
                    "price_vs_vwap": "above",
                },
            },
            account_overview={
                "status": "success",
                "assigned_security_id": 111,
                "intraday_margin_budget": 500,
                "available_balance": 1000,
            },
        )

        self.assertNotIn("scanner_signal", context)
        self.assertEqual(context["market_evidence"]["relative_volume"], 1.4)
        self.assertNotIn("score", json.dumps(context["market_evidence"]).lower())
        self.assertNotIn("latest_price", context["technical"]["readings"])
        self.assertAlmostEqual(
            context["technical"]["readings"]["price_vs_vwap_percent"],
            1.0101,
        )
        self.assertNotIn("upper_circuit", context["instrument"]["tradability"])
        self.assertEqual(context["live_market"]["quote"]["upper_circuit"], 121)
        self.assertNotIn("intraday_margin_budget", context["account"])
        self.assertNotIn("assigned_security_id", context["account"])

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
        result = StockAccountToolkit(FakeStockDhan(), 111, 500).get_account_overview()

        self.assertTrue(result.startswith("## Tool result\n"))
        self.assertIn("- has_open_intraday_position: true", result)
        self.assertIn("- open_intraday_position_count: 1", result)
        self.assertIn("- active_order_count: 1", result)
        self.assertNotIn("other-order-secret", result)
        self.assertNotIn("private-client-id", result)
        self.assertNotIn("999", result)

    def test_technical_tool_omits_indicators_without_enough_candles(self):
        result = StockTechnicalToolkit(
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

        self.assertIn("- latest_price: 100", result)
        self.assertNotIn("- rsi:", result)
        self.assertNotIn("- bb_upper:", result)

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

        result = toolkit.get_security_overview()
        self.assertIn("- tick_size_rupees: 0.05", result)
        self.assertIn("- relative_volume: 1.8", result)
        self.assertIn("- volume_acceleration: 1.4", result)
        self.assertNotIn("opening_range_breakout_percent", result)

    def test_model_market_evidence_excludes_detector_opinions(self):
        toolkit = StockMarketDataToolkit(
            FakeStockDhan(),
            SimpleNamespace(),
            security_id=111,
            symbol="TEST",
            display_name="Test Limited",
            stock_context={
                "price": 100,
                "created_at": "2026-08-24T10:00:00+05:30",
                "direction": "LONG",
                "setup_type": "INDICATOR_EVENT",
                "setup_score": 95,
                "selection_reason": "strong setup",
                "relative_volume": 1.7,
                "volume_acceleration": 2.2,
                "stage2": {"score": 99, "selection_score": 98},
            },
        )

        serialized = json.dumps(toolkit.security_overview_payload()).lower()

        self.assertIn("relative_volume", serialized)
        self.assertIn("volume_acceleration", serialized)
        for forbidden in (
            "direction",
            "setup_type",
            "setup_score",
            "selection_reason",
            "selection_score",
            '"score"',
        ):
            self.assertNotIn(forbidden, serialized)

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

        result = toolkit.get_current_stock_state()

        self.assertIn("- status: success", result)
        self.assertEqual(dhan.history_calls, 1)
        initial = toolkit.current_stock_state_payload(force_refresh=False)
        self.assertEqual(dhan.history_calls, 1)
        self.assertEqual(initial["quote"]["last_price"], 101.25)
        toolkit.current_stock_state_payload()
        self.assertEqual(dhan.history_calls, 2)
        self.assertIn("- last_price: 101.25", result)
        self.assertIn("12:59:00", result)
        self.assertIn("- close: 101.25", result)
        self.assertNotIn("recent_1m_candles", result)
        self.assertNotIn("recent_5m_candles", result)

    def test_execution_state_comes_from_tool_result_not_agent_prose(self):
        dhan = FakeStockDhan(margin_required=20.0, include_selected_position=False)
        toolkit = StockExecutionToolkit(dhan, 111, 500)
        toolkit._dhan_tools.allow_live_orders = True

        response = toolkit.place_protected_intraday_order(
                side="BUY",
                quantity=2,
                entry_price=100.0,
                target_price=105.0,
                stop_loss_price=98.0,
            )
        decision = toolkit.decision_snapshot("Test Limited")

        self.assertIn("- status: success", response)
        self.assertEqual(decision["action"], "pending")
        self.assertEqual(decision["execution_status"], "pending")
        self.assertEqual(decision["broker_order_status"], "TRANSIT")
        self.assertEqual(decision["filled_quantity"], 0)
        self.assertEqual(decision["order_id"], "order-123")
        self.assertEqual(dhan.super_order_calls, 1)

        self.assertNotIn("place_intraday_order", toolkit.functions)
        self.assertEqual(toolkit.decision_snapshot("Test Limited")["execution_status"], "pending")

    def test_nse_protected_order_preserves_selected_exchange_segment(self):
        dhan = FakeStockDhan(margin_required=20.0, include_selected_position=False)
        toolkit = StockExecutionToolkit(
            dhan,
            111,
            500,
            exchange_segment="NSE_EQ",
        )
        toolkit._dhan_tools.allow_live_orders = True

        response = toolkit.place_protected_intraday_order(
                side="BUY",
                quantity=2,
                entry_price=100.0,
                target_price=105.0,
                stop_loss_price=98.0,
            )

        self.assertIn("- status: success", response)
        self.assertNotIn("exchange_segment", response)
        self.assertEqual(dhan.last_super_order_kwargs["exchange_segment"], "NSE_EQ")

    def test_invalid_ip_broker_failure_is_never_reported_as_an_order(self):
        dhan = FakeStockDhan(margin_required=20.0, include_selected_position=False)
        dhan.place_super_order = lambda **_kwargs: {
            "status": "failure",
            "remarks": {
                "error_code": "DH-905",
                "error_type": "Input_Exception",
                "error_message": "Invalid IP",
            },
            "data": "",
        }
        gate = FakeOrderPlacementGate()
        coordinator = StockExecutionCoordinator(order_placement_gate=gate)
        toolkit = StockExecutionToolkit(
            dhan,
            111,
            500,
            exchange_segment="NSE_EQ",
            coordinator=coordinator,
        )
        toolkit._dhan_tools.allow_live_orders = True

        response = toolkit.place_protected_intraday_order(
                side="BUY",
                quantity=1,
                entry_price=100.0,
                target_price=105.0,
                stop_loss_price=98.0,
            )
        decision = toolkit.decision_snapshot("Test Limited")

        self.assertIn("- status: failure", response)
        self.assertIn("- error_code: DH-905", response)
        self.assertEqual(decision["action"], "avoid")
        self.assertEqual(decision["execution_status"], "failed")
        self.assertEqual(decision["order_id"], "NONE")
        self.assertEqual(toolkit.coordinator.successful_orders, [])
        self.assertFalse(gate.allowed)
        self.assertEqual(gate.block_calls, 1)

        sibling = StockExecutionToolkit(
            dhan,
            111,
            500,
            exchange_segment="NSE_EQ",
            coordinator=StockExecutionCoordinator(order_placement_gate=gate),
        )
        sibling._dhan_tools.allow_live_orders = True
        blocked = sibling.place_protected_intraday_order(
            side="BUY",
            quantity=1,
            entry_price=100.0,
            target_price=105.0,
            stop_loss_price=98.0,
        )
        self.assertIn("execution_halted_order_placement_blocked", blocked)
        self.assertEqual(dhan.super_order_calls, 0)

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

        response = toolkit.place_protected_intraday_order(
                side="BUY",
                quantity=1,
                entry_price=100.0,
                target_price=105.0,
                stop_loss_price=98.0,
            )
        decision = toolkit.decision_snapshot("Test Limited")

        self.assertIn("- status: blocked", response)
        self.assertEqual(decision["execution_status"], "blocked")
        self.assertEqual(dhan.super_order_calls, 0)

    def test_execution_blocks_when_three_trade_slots_are_already_in_use(self):
        dhan = FakeStockDhan(margin_required=20.0, include_selected_position=False)
        dhan.fetch_positions = lambda: {
            "status": "success",
            "data": [
                {"securityId": value, "productType": "INTRADAY", "netQty": 1}
                for value in ("901", "902", "903")
            ],
        }
        dhan.fetch_order_book = lambda: {"status": "success", "data": []}
        toolkit = StockExecutionToolkit(dhan, 111, 500, max_concurrent_trades=3)
        toolkit._dhan_tools.allow_live_orders = True

        response = toolkit.place_protected_intraday_order(
            side="BUY",
            quantity=1,
            entry_price=100.0,
            target_price=105.0,
            stop_loss_price=98.0,
        )

        self.assertIn("maximum_concurrent_trade_slots_in_use", response)
        self.assertEqual(dhan.super_order_calls, 0)

    def test_shared_gate_reserves_slot_before_broker_book_catches_up(self):
        dhan = FakeStockDhan(margin_required=20.0, include_selected_position=False)
        dhan.fetch_positions = lambda: {"status": "success", "data": []}
        dhan.fetch_order_book = lambda: {"status": "success", "data": []}
        dhan.fetch_super_orders = lambda: {"status": "success", "data": []}
        gate = FakeOrderPlacementGate()
        first = StockExecutionToolkit(
            dhan,
            111,
            500,
            coordinator=StockExecutionCoordinator(order_placement_gate=gate),
            max_concurrent_trades=1,
        )
        second = StockExecutionToolkit(
            dhan,
            222,
            500,
            coordinator=StockExecutionCoordinator(order_placement_gate=gate),
            max_concurrent_trades=1,
        )
        first._dhan_tools.allow_live_orders = True
        second._dhan_tools.allow_live_orders = True

        placed = first.place_protected_intraday_order(
            side="BUY", quantity=1, entry_price=100, target_price=105, stop_loss_price=98
        )
        blocked = second.place_protected_intraday_order(
            side="BUY", quantity=1, entry_price=100, target_price=105, stop_loss_price=98
        )

        self.assertIn("- status: success", placed)
        self.assertIn("maximum_concurrent_trade_slots_in_use", blocked)
        self.assertEqual(dhan.super_order_calls, 1)

    def test_execution_blocks_when_final_price_has_moved_too_far(self):
        dhan = FakeStockDhan(margin_required=20.0, include_selected_position=False)
        toolkit = StockExecutionToolkit(
            dhan,
            111,
            500,
            final_state_loader=lambda: {
                "status": "success",
                "candle_data_age_seconds": 10,
                "quote": {
                    "last_price": 101.5,
                    "last_trade_age_seconds": 1,
                },
            },
            max_entry_drift_risk_fraction=0.5,
        )
        toolkit._dhan_tools.allow_live_orders = True

        response = toolkit.place_protected_intraday_order(
            side="BUY",
            quantity=1,
            entry_price=100.0,
            target_price=105.0,
            stop_loss_price=98.0,
        )

        self.assertIn("final_price_drift_exceeds_limit", response)
        self.assertEqual(dhan.super_order_calls, 0)

    def test_execution_revalidates_current_ltp_against_leverage_cap(self):
        dhan = FakeStockDhan(margin_required=20.0, include_selected_position=False, current_ltp=501.0)
        toolkit = StockExecutionToolkit(dhan, 111, 500)
        toolkit._dhan_tools.allow_live_orders = True

        response = toolkit.place_protected_intraday_order(
            side="BUY", quantity=5, entry_price=490.0, target_price=510.0, stop_loss_price=480.0,
        )

        self.assertIn("- status: blocked", response)
        self.assertIn("- remarks: current_notional_exceeds_leverage_cap", response)
        self.assertIn("- current_ltp: 501", response)
        self.assertEqual(dhan.super_order_calls, 0)

    def test_execution_uses_current_available_balance_as_margin_cap(self):
        dhan = FakeStockDhan(margin_required=20.0, include_selected_position=False, current_ltp=100.0, fund_balance=90.0)
        toolkit = StockExecutionToolkit(dhan, 111, 500, amount_source="available_balance")
        toolkit._dhan_tools.allow_live_orders = True

        response = toolkit.place_protected_intraday_order(
            side="BUY", quantity=1, entry_price=100.0, target_price=105.0, stop_loss_price=98.0,
        )

        self.assertIn("- status: success", response)
        self.assertEqual(dhan.super_order_calls, 1)

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
