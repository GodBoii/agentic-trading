from __future__ import annotations

import unittest
import sys
import types
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from threading import Event, RLock
from types import SimpleNamespace

if "dhanhq" not in sys.modules:
    fake_dhan = types.ModuleType("dhanhq")
    fake_dhan.MarketFeed = type("MarketFeed", (), {"NSE": "NSE", "BSE": "BSE", "Full": "Full"})
    fake_dhan.DhanContext = type("DhanContext", (), {})
    fake_dhan.HistoricalData = type("HistoricalData", (), {})
    fake_dhan.OptionChain = type("OptionChain", (), {})
    fake_dhan.FullDepth = type("FullDepth", (), {})
    fake_dhan.dhanhq = type("dhanhq", (), {})
    sys.modules["dhanhq"] = fake_dhan

from pipeline.config import PipelineConfig
from pipeline.stages.activity_ranker import ActivityRanker
from pipeline.stages.activity_ranker import RankingResult
from pipeline.stages.intra_finder import IntraFinder
from pipeline.stages.live_state import LiveStockState
from pipeline.stages.setups import SetupEngine
from pipeline.stages.setups.base import SetupSignal
from pipeline.services.storage_service import StorageService


IST = datetime.fromisoformat("2026-08-28T09:15:30+05:30").tzinfo


def state(security_id: int, *, volume: float, volatility: float, value: float) -> LiveStockState:
    now = datetime.fromisoformat("2026-08-28T10:00:00+05:30")
    item = LiveStockState("NSE_EQ", security_id, f"S{security_id}", f"INE{security_id}")
    item.latest_price = 100.0
    item.last_packet_at = now.isoformat()
    item.last_trade_at = now.isoformat()
    item.depth = [{} for _ in range(5)]
    item.spread_percent = 0.03
    item.volume_pace = volume
    item.realized_volatility_percent = volatility
    item.traded_value_5m = value
    item.refresh_derived = lambda _now: None
    return item


class ActivityRankerTests(unittest.TestCase):
    def test_rank_requires_both_volume_and_movement(self) -> None:
        now = datetime.fromisoformat("2026-08-28T10:00:00+05:30")
        balanced = state(1, volume=2.0, volatility=2.0, value=20_000_000)
        volume_only = state(2, volume=5.0, volatility=0.2, value=30_000_000)
        movement_only = state(3, volume=0.2, volatility=5.0, value=10_000_000)
        ranker = ActivityRanker(hot_size=1, reserve_size=1)

        result = ranker.rank({item.key: item for item in (balanced, volume_only, movement_only)}, now)

        self.assertEqual(result.ranked[0].security_id, 1)
        self.assertTrue(balanced.is_hot)
        self.assertFalse(volume_only.is_hot)
        self.assertFalse(movement_only.is_hot)

    def test_missing_personal_baseline_uses_turnover_pace(self) -> None:
        now = datetime.fromisoformat("2026-08-28T10:00:00+05:30")
        item = LiveStockState("NSE_EQ", 1, "TEST", "INE1", adv_20_cr=20.0)
        item.latest_price = 100.0
        item.cumulative_value = 10_000_000.0

        item.refresh_derived(now)

        self.assertIsNotNone(item.volume_pace)
        self.assertGreater(item.volume_pace, 0.0)


class SetupEngineTests(unittest.TestCase):
    def test_market_open_discards_preopen_bar_builder(self) -> None:
        preopen = datetime.fromisoformat("2026-08-31T09:10:00+05:30")
        market_open = datetime.fromisoformat("2026-08-31T09:15:00+05:30")
        item = LiveStockState("NSE_EQ", 1, "TEST", "INE1")
        depth = [{} for _ in range(5)]
        features = {"spread_percent": 0.03}
        item.apply_packet(
            received_at=preopen,
            price=100.0,
            cumulative_volume=0.0,
            vwap=100.0,
            last_trade_at=preopen,
            last_trade_quantity=1.0,
            depth=depth,
            depth_features=features,
        )
        item.apply_packet(
            received_at=market_open,
            price=101.0,
            cumulative_volume=100.0,
            vwap=101.0,
            last_trade_at=market_open,
            last_trade_quantity=10.0,
            depth=depth,
            depth_features=features,
        )

        self.assertEqual(list(item.minute_bars), [])
        self.assertEqual(item.minute_builder.minute_start, market_open)
        self.assertEqual(item.minute_builder.open, 101.0)

    def test_opening_setup_can_trigger_without_completed_minute_bars(self) -> None:
        start = datetime.fromisoformat("2026-08-28T09:15:00+05:30")
        item = LiveStockState("NSE_EQ", 1, "TEST", "INE1", historical_atr_percent=2.0)
        item.is_hot = True
        item.first_packet_at = start.isoformat()
        item.session_open = 100.0
        item.session_high = 100.6
        item.session_low = 100.0
        item.latest_price = 100.6
        item.volume_percentile = 90.0
        item.volatility_percentile = 90.0
        item.relative_strength_percentile = 90.0
        item.trend_efficiency = 0.9
        for second, price in ((0, 100.0), (10, 100.2), (20, 100.4), (30, 100.6)):
            item.price_samples.append(((start + timedelta(seconds=second)).timestamp(), price))
        engine = SetupEngine()

        self.assertEqual(engine.evaluate(item, start + timedelta(seconds=30)), [])
        signals = engine.evaluate(item, start + timedelta(seconds=39))

        self.assertEqual(len(item.minute_bars), 0)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].family, "OPENING_DRIVE")
        self.assertEqual(signals[0].direction, "LONG")

        item.volume_percentile = 0.0
        self.assertEqual(engine.evaluate(item, start + timedelta(seconds=40)), [])
        item.volume_percentile = 90.0
        self.assertEqual(engine.evaluate(item, start + timedelta(seconds=50)), [])


class IntraFinderFlowTests(unittest.TestCase):
    def test_stale_prior_session_market_context_is_not_attached(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nifty.json"
            StorageService.save_snapshot(
                path,
                {
                    "stage": "nifty",
                    "generated_at_utc": "2026-08-23T10:00:00+00:00",
                    "summary": {"market_date": "2026-08-24"},
                },
            )
            now = datetime.fromisoformat("2026-08-31T10:00:00+05:30")
            finder = IntraFinder.__new__(IntraFinder)
            finder.config = PipelineConfig()
            finder.market_time = SimpleNamespace(
                now=lambda: now,
                market_date_str=lambda: "2026-08-31",
            )

            self.assertIsNone(finder._load_context(path))

    def test_recent_completed_universe_is_accepted_as_opening_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = PipelineConfig(
                stage1_latest_path=root / "latest.json",
                stage2_results_dir=root / "stage2",
                stage1_universe_fallback_max_age_days=4,
            )
            StorageService.save_snapshot(
                config.stage1_latest_path,
                {
                    "stage": "universe_scanner",
                    "summary": {
                        "status": "completed",
                        "market_date": "2026-08-28",
                        "universe_version": "v1",
                    },
                    "stocks": [
                        {
                            "isin": "INE1",
                            "exchange_segment": "NSE_EQ",
                            "security_id": 1,
                            "symbol": "TEST",
                        }
                    ],
                },
            )
            finder = IntraFinder.__new__(IntraFinder)
            finder.config = config
            finder.market_time = SimpleNamespace(market_date_str=lambda: "2026-08-30")
            finder.universe_version = ""
            finder.universe_source_date = ""
            finder.universe_payload = {}
            finder.stocks = {}
            finder.states = {}
            finder._restore_runtime_state = lambda _date: None
            finder._load_event_state = lambda _date: None

            stocks = finder.load_universe()

            self.assertEqual(len(stocks), 1)
            self.assertEqual(finder.universe_source_date, "2026-08-28")

    def test_packet_identity_includes_exchange_segment(self) -> None:
        finder = IntraFinder.__new__(IntraFinder)
        finder.stocks = {
            ("NSE_EQ", 10): {"security_id": 10},
            ("BSE_EQ", 10): {"security_id": 10},
        }
        finder.security_index = {10: [("NSE_EQ", 10), ("BSE_EQ", 10)]}

        self.assertEqual(finder._packet_key({"exchange_segment": 1, "security_id": 10}), ("NSE_EQ", 10))
        self.assertEqual(finder._packet_key({"exchange_segment": 4, "security_id": 10}), ("BSE_EQ", 10))
        self.assertIsNone(finder._packet_key({"security_id": 10}))

    def test_dispatch_is_bounded_to_three_live_threads(self) -> None:
        finder = IntraFinder.__new__(IntraFinder)
        finder.config = PipelineConfig(intra_finder_max_dispatch_concurrency=3)
        finder.dispatch_lock = RLock()
        finder.agent_threads = set()
        finder.events_triggered = 0
        finder.events_suppressed = 0
        finder.agent_dispatch_failures = 0
        finder.gate_failure_counts = __import__("collections").Counter()
        release = Event()
        started = Event()
        calls: list[str] = []

        def post(event):
            calls.append(event["event_id"])
            if len(calls) == 3:
                started.set()
            release.wait(2)

        finder._post_agent_event = post
        for index in range(3):
            self.assertTrue(finder._dispatch_event({"event_id": str(index)}))
        self.assertTrue(started.wait(2))
        self.assertFalse(finder._dispatch_event({"event_id": "fourth"}))
        self.assertEqual(finder.events_triggered, 3)
        release.set()
        for thread in list(finder.agent_threads):
            thread.join(timeout=2)

    def test_one_share_depth_probe_uses_percent_units(self) -> None:
        depth = [
            {
                "bid_price": 99.9,
                "ask_price": 100.1,
                "bid_quantity": 100,
                "ask_quantity": 100,
            }
        ]
        slippage = IntraFinder._estimated_slippage(
            depth,
            direction="LONG",
            reference_price=100.0,
            trade_amount=100.0,
        )
        self.assertAlmostEqual(slippage, 0.1)

    def test_trigger_packet_preserves_agent_event_contract(self) -> None:
        now = datetime.fromisoformat("2026-08-28T10:00:00+05:30")
        stock = {
            "isin": "INE1",
            "exchange_segment": "NSE_EQ",
            "security_id": 1,
            "symbol": "TEST",
            "display_name": "Test Limited",
            "instrument": "EQUITY",
        }
        live = LiveStockState.from_stock(stock)
        finder = IntraFinder.__new__(IntraFinder)
        finder.config = PipelineConfig()
        finder.market_time = SimpleNamespace(
            now=lambda: now,
            market_date_str=lambda: "2026-08-28",
        )
        finder.stocks = {live.key: stock}
        finder.states = {live.key: live}
        finder.security_index = {1: [live.key]}
        finder.universe_version = "v2"
        finder.universe_source_date = "2026-08-28"
        finder.detector_mode = "cross_sectional_setups_v2"
        finder.event_state = {"events": {}}
        finder.packet_count = 0
        finder.last_global_packet_at = None
        finder.received_keys = set()
        finder.full_packet_keys = set()
        finder.coverage_milestones_logged = set()
        finder.raw_buffer = []
        finder.derived_buffer = []
        finder.record_all_raw = False
        finder.record_hot_raw = False
        finder.last_rank_at = 0.0
        finder.last_rank_duration_ms = 0.0
        finder.candidates_seen = 0
        finder.events_formed = 0
        finder.events_suppressed = 0
        finder.events_triggered = 0
        finder.shadow_mode = True
        finder.connected_at = now - timedelta(minutes=1)
        finder.gate_failure_counts = __import__("collections").Counter()
        finder._log = lambda _message: None
        finder._flush_if_due = lambda: None
        finder._save_status_if_due = lambda: None
        finder._submit_io = lambda *_args: None
        finder._load_context = lambda _path: None

        class Ranker:
            @staticmethod
            def rank(states, _now):
                item = next(iter(states.values()))
                item.is_hot = True
                item.activity_rank = 1
                item.hotness = 95.0
                item.volume_percentile = 95.0
                item.volatility_percentile = 95.0
                return RankingResult([item], [item], 1)

        finder.ranker = Ranker()
        signal = SetupSignal(
            family="VOLATILITY_IGNITION",
            direction="LONG",
            armed_at=now - timedelta(seconds=5),
            triggered_at=now,
            expires_at=now + timedelta(seconds=30),
            trigger_level=100.0,
            trigger_price=100.0,
            invalidation_price=99.5,
            reason="test trigger",
            diagnostics={"price": 100.0},
        )
        finder.setup_engine = SimpleNamespace(evaluate=lambda _state, _now: [signal])
        packet = {
            "exchange_segment": 1,
            "security_id": 1,
            "LTP": 100.0,
            "LTT": "10:00:00",
            "volume": 10_000,
            "avg_price": 99.8,
            "close": 99.0,
            "open": 99.5,
            "high": 100.0,
            "low": 99.5,
            "depth": [
                {
                    "bid_price": 99.99,
                    "ask_price": 100.01,
                    "bid_quantity": 1000,
                    "ask_quantity": 1000,
                    "bid_orders": 10,
                    "ask_orders": 10,
                }
                for _ in range(5)
            ],
        }

        event = finder.process_packet(packet, received_at=now)

        self.assertEqual(event["setup_type"], "VOLATILITY_IGNITION")
        self.assertEqual(event["setup_state"], "TRIGGERED")
        self.assertEqual(event["expires_at"], signal.expires_at.isoformat())
        self.assertEqual(event["activity"]["rank"], 1)
        self.assertEqual(event["exchange_segment"], "NSE_EQ")


if __name__ == "__main__":
    unittest.main()
