import asyncio
import random
import time
import unittest
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Condition, Event, Lock
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock, patch

from pipeline.services.concurrent_work import bounded_results
from pipeline.services.feed_receiver import FeedReceiver
from pipeline.services.inflight_reads import InflightReads
from pipeline.services.dhan_service import DhanService
from pipeline.runtime.run_ai_trading_orchestrator import AITradingOrchestrator
from pipeline.services.nifty_depth_monitor import NiftyDepthMonitor
from pipeline.config import PipelineConfig
from pipeline.runtime.run_stock_agent import MultiStockAgentRunner
from pipeline.stages.intra_finder import IntraFinder
from pipeline.stages.live_state import LiveStockState


class RollingParityTests(unittest.TestCase):
    def test_incremental_prices_match_full_scan_through_replacements_and_expiration(self):
        state = LiveStockState("NSE_EQ", 1, "TEST", "ISIN")
        rng = random.Random(83)
        for index in range(2000):
            timestamp = 1800000000 + index * 0.5
            price = 100 + rng.random()
            state.latest_price = price
            state._sample(timestamp, price)
            state.refresh_derived(datetime.fromtimestamp(timestamp, tz=timezone.utc))
            five = [value for stamp, value in state.price_samples if stamp >= timestamp - 300]
            one = [value for stamp, value in state.price_samples if stamp >= timestamp - 60]
            path = sum(abs(b - a) for a, b in zip(one, one[1:]))
            self.assertAlmostEqual(state.realized_volatility_percent, (max(five) - min(five)) / price * 100)
            self.assertAlmostEqual(state.return_5m_percent, (five[-1] - five[0]) / five[0] * 100)
            self.assertAlmostEqual(state.trend_efficiency, abs(one[-1] - one[0]) / path if path else 0)

    def test_clock_reversal_does_not_hide_newer_retained_sample(self):
        state = LiveStockState("NSE_EQ", 1, "TEST", "ISIN")
        state.latest_price = 100
        state._sample(1000, 100)
        state._sample(500, 110)
        state._sample(1001, 120)
        state.refresh_derived(datetime.fromtimestamp(1001, tz=timezone.utc))
        self.assertEqual(state.return_5m_percent, 20)

    def test_same_second_volume_reset_can_restart_value_samples(self):
        state = LiveStockState("NSE_EQ", 1, "TEST", "ISIN")
        state._sample(1000, 100)
        state.value_samples.clear()
        state.cumulative_value = 10
        state._sample(1000.5, 101)
        self.assertEqual(list(state.value_samples), [(1000.5, 10)])

    def test_windows_match_reference_with_mature_sparse_and_boundary_samples(self):
        rng = random.Random(17)
        now = datetime.fromisoformat("2026-09-07T10:00:00+05:30")
        stamp = now.timestamp()
        for count in (0, 1, 3, 300, 900):
            state = LiveStockState("NSE_EQ", 1, "TEST", "ISIN")
            state.latest_price = 100
            prices = [(stamp - i, 100 + rng.random()) for i in reversed(range(count))]
            values = [(timestamp, float(index * 137)) for index, (timestamp, _) in enumerate(prices)]
            state.price_samples.extend(prices)
            state.value_samples.extend(values)
            for offset in (0, 0.5, 30, 60, 150, 300, 901):
                current = now + timedelta(seconds=offset)
                end = current.timestamp()
                five = [value for timestamp, value in prices if timestamp >= end - 300]
                one = [value for timestamp, value in prices if timestamp >= end - 60]
                path = sum(abs(b - a) for a, b in zip(one, one[1:]))

                def delta(start, stop):
                    window = [value for timestamp, value in values if start <= timestamp <= stop]
                    return max(0, window[-1] - window[0]) if window else 0

                recent, prior = delta(end - 30, end), delta(end - 150, end - 30)
                state.refresh_derived(current)
                self.assertAlmostEqual(state.realized_volatility_percent, max(five) - min(five) if five else 0)
                self.assertAlmostEqual(state.return_5m_percent, (five[-1] - five[0]) / five[0] * 100 if five else 0)
                self.assertAlmostEqual(state.trend_efficiency, abs(one[-1] - one[0]) / path if path else 0)
                self.assertEqual(state.traded_value_5m, delta(end - 300, end))
                self.assertEqual(state.volume_acceleration, min(8, recent / (prior / 4)) if recent > 0 and prior > 0 else None)

    def test_baseline_cache_tracks_mutation_and_interval(self):
        state = LiveStockState("NSE_EQ", 1, "TEST", "ISIN",
                               median_cumulative_volume={"09:15": 100, "09:20": 200, "bad": 3})
        now = datetime.fromisoformat("2026-09-07T09:20:00+05:30")
        self.assertEqual(state.expected_cumulative_volume(now), 100)
        state.median_cumulative_volume["09:15"] = 150
        self.assertEqual(state.expected_cumulative_volume(now), 150)
        state.baseline_interval_minutes = 10
        self.assertEqual(state.expected_cumulative_volume(now), 75)

    def test_checkpoint_retains_tail_and_detaches_setup_state(self):
        state = LiveStockState("NSE_EQ", 1, "TEST", "ISIN")
        state.price_samples = deque(((i, float(i)) for i in range(900)), maxlen=900)
        state.setup_state = {"signal": {"count": 1}}
        compact = state.checkpoint(compact=True)
        full = state.checkpoint()
        state.setup_state["signal"]["count"] = 2
        self.assertEqual(compact["price_samples"], list(state.price_samples)[-30:])
        self.assertEqual(full["price_samples"], list(state.price_samples)[-300:])
        self.assertEqual(compact["setup_state"]["signal"]["count"], 1)


class ConcurrentWorkTests(unittest.TestCase):
    def test_submission_is_bounded_and_results_keep_input_identity(self):
        consumed = []

        def items():
            for item in range(100):
                consumed.append(item)
                yield item

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = bounded_results(pool, lambda item: item * item, items(), limit=4)
            first = next(results)
            self.assertEqual(len(consumed), 4)
            rows = [first, *results]
        self.assertEqual(sorted(rows), [(i, i * i) for i in range(100)])

    def test_inflight_read_shares_success_and_does_not_cache_completed_result(self):
        reads = InflightReads()
        entered, release = Event(), Event()
        calls = []

        def fetch():
            calls.append(1)
            entered.set()
            self.assertTrue(release.wait(2))
            return {"value": 3}

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(reads.run, "same", fetch)
            self.assertTrue(entered.wait(1))
            second = pool.submit(reads.run, "same", fetch)
            time.sleep(0.02)
            release.set()
            self.assertEqual(first.result(), second.result())
        self.assertEqual(len(calls), 1)
        self.assertEqual(reads.run("same", lambda: 4), 4)

    def test_inflight_failure_can_retry(self):
        reads = InflightReads()
        with self.assertRaises(ValueError):
            reads.run("same", lambda: int("bad"))
        self.assertEqual(reads.run("same", lambda: 4), 4)


class ReceiverTests(unittest.TestCase):
    def test_stop_drains_packet_waiting_behind_full_queue(self):
        loop = asyncio.new_event_loop()
        count = 0

        async def receive():
            nonlocal count
            count += 1
            return {"sequence": count}

        receiver = FeedReceiver(SimpleNamespace(loop=loop, get_instrument_data=receive), datetime.now, capacity=1)
        try:
            receiver.start()
            deadline = time.monotonic() + 1
            while receiver.full_waits == 0 and time.monotonic() < deadline:
                time.sleep(0.001)
            receiver.stop()
            self.assertEqual([item.packet["sequence"] for item in receiver.drain()], [1, 2])
            self.assertEqual(list(receiver.drain()), [])
        finally:
            receiver.stop()
            loop.close()

    def test_bounded_receiver_preserves_order_and_runs_protocol_tasks(self):
        loop = asyncio.new_event_loop()
        protocol_ran = Event()
        count = 0

        async def receive():
            nonlocal count
            await asyncio.sleep(0)
            count += 1
            return {"sequence": count}

        receiver = FeedReceiver(SimpleNamespace(loop=loop, get_instrument_data=receive), datetime.now, capacity=2)
        try:
            receiver.start()
            loop.call_soon_threadsafe(lambda: loop.call_later(0.01, protocol_ran.set))
            self.assertTrue(protocol_ran.wait(1))
            self.assertEqual(receiver.queue.qsize(), 2)
            self.assertGreater(receiver.full_waits, 0)
            self.assertEqual([receiver.get(1).packet["sequence"] for _ in range(20)], list(range(1, 21)))
            self.assertLessEqual(receiver.high_water, 2)
        finally:
            receiver.stop()
            loop.close()

    def test_receiver_delivers_accepted_packet_before_failure(self):
        loop = asyncio.new_event_loop()
        count = 0

        async def receive():
            nonlocal count
            count += 1
            if count == 1:
                return {"sequence": 1}
            raise OSError("disconnected")

        receiver = FeedReceiver(SimpleNamespace(loop=loop, get_instrument_data=receive), datetime.now)
        try:
            receiver.start()
            self.assertEqual(receiver.get(1).packet, {"sequence": 1})
            with self.assertRaisesRegex(RuntimeError, "receiver failed"):
                receiver.get(1)
        finally:
            receiver.stop()
            loop.close()


class PersistenceTests(unittest.TestCase):
    def test_depth_snapshot_disk_write_does_not_hold_market_state_lock(self):
        with patch("pipeline.services.nifty_depth_monitor.MarketReferenceService"), \
             patch("pipeline.services.nifty_depth_monitor.NiftyDepthChartGenerator"):
            monitor = NiftyDepthMonitor(PipelineConfig())
        monitor._daily_dir = lambda: Path("unused")
        monitor._build_full_packet_snapshot = lambda: {}
        monitor._build_depth_snapshot = lambda: {}
        monitor._build_derived_snapshot = lambda: {}
        monitor._build_options_snapshot = lambda: {}
        monitor.market_time.is_market_hours = lambda: True

        def acquire_market_lock():
            acquired = monitor.lock.acquire(timeout=0.2)
            if acquired:
                monitor.lock.release()
            return acquired

        def save(*args):
            with ThreadPoolExecutor(max_workers=1) as executor:
                self.assertTrue(executor.submit(acquire_market_lock).result())

        with patch("pipeline.services.nifty_depth_monitor.StorageService.save_snapshot", side_effect=save):
            monitor._save_latest(force=True)
        self.assertGreater(monitor.last_saved_at, 0)

    def test_failed_future_remains_visible_and_blocks_new_writes(self):
        finder = object.__new__(IntraFinder)
        finder.io_futures = set()
        finder.io_pending_limit = 1
        finder.persistence_error = None
        with ThreadPoolExecutor(max_workers=1) as pool:
            finder.io_executor = pool
            finder._submit_io(lambda: int("bad"))
            with self.assertRaisesRegex(RuntimeError, "persistence failed"):
                finder._submit_io(lambda: None)
        self.assertEqual(len(finder.io_futures), 1)
        self.assertEqual(finder.persistence_error, "ValueError")


class AccountRoutingTests(unittest.TestCase):
    def test_shared_event_uses_separate_persisted_sessions_for_each_account(self):
        first = MultiStockAgentRunner._event_session_id("same-event", "first")
        second = MultiStockAgentRunner._event_session_id("same-event", "second")
        self.assertNotEqual(first, second)
        self.assertEqual(first, MultiStockAgentRunner._event_session_id("same-event", "first"))

    def test_slow_and_failed_account_does_not_block_other_account(self):
        orchestrator = object.__new__(AITradingOrchestrator)
        orchestrator.config = SimpleNamespace(ai_trading_state_path=Path("unused.json"))
        orchestrator.event_lock = Lock()
        orchestrator.event_state = {"events": {}}
        orchestrator.event_state_path = Path("unused.json")
        orchestrator.event_decision_archive_path = Path("unused.ndjson")
        orchestrator.storage = SimpleNamespace(save_snapshot=lambda *args: None)
        archive = []
        orchestrator._archive_event_decision = lambda event_id, payload: archive.append(payload)
        orchestrator._broadcast_event = Mock()
        second_started = Event()
        event = {"event_id": "test", "nested": {"value": 1}}

        def resolve(user):
            return {**user, "eligible": True, "trade_mode": "manual", "trade_amount": 100,
                    "amount_source": "user_amount", "max_concurrent_trades": 1}

        def run(routed, *, user_id, **kwargs):
            routed["nested"]["value"] = 9
            if user_id == "first":
                if not second_started.wait(2):
                    raise AssertionError("second account did not start concurrently")
                raise ValueError("account failed")
            second_started.set()
            return {"done": True}

        agent = SimpleNamespace(resolve_user_trade_config=resolve,
                                prepare_user_event=lambda event, user: {"eligible": True, "event": event},
                                run_event=run)
        orchestrator._get_stock_agent = lambda: agent
        with patch("pipeline.runtime.run_ai_trading_orchestrator.AITradingStateService.configured_users",
                   return_value=[{"user_id": "first"}, {"user_id": "second"}]), \
             patch.dict("os.environ", {"ACCOUNT_EVENT_WORKERS": "2"}):
            orchestrator._run_intra_finder_event(event)
        results = archive[0]["decision"]["user_results"]
        self.assertTrue(second_started.is_set())
        self.assertEqual(results[0]["status_code"], "account_run_failed")
        self.assertEqual(results[1]["result"], {"done": True})
        self.assertEqual(event["nested"]["value"], 1)


class OptionRateTests(unittest.TestCase):
    def test_redis_option_admission_reserves_data_and_option_budget_once(self):
        service = object.__new__(DhanService)
        service.gateway_url = None
        service.client_id = "test"
        service.config = SimpleNamespace(historical_rate_limit_per_sec=4)
        service.option_chain_request_gap = 3.1
        service.redis_limiter = SimpleNamespace(acquire=Mock())
        service.option_chain_api = SimpleNamespace(option_chain=Mock(return_value={"status": "success"}))
        service.fetch_option_chain(13, "IDX_I", "2026-09-10")
        service.redis_limiter.acquire.assert_called_once_with("test", {
            "data": [(1000, 4), (86400000, 100000)], "option-chain": [(3100, 1)],
        })

    def test_concurrent_option_calls_keep_gap(self):
        service = object.__new__(DhanService)
        service.config = SimpleNamespace(dhan_rate_limit_state_path=Path("unused.json"))
        service._acquire_shared_gap = lambda *args: None
        service.option_chain_condition = Condition()
        service.option_chain_request_gap = 0.03
        service.last_option_chain_request_ts = 0

        def acquire():
            service._enforce_option_chain_gap()
            return time.monotonic()

        with ThreadPoolExecutor(max_workers=4) as executor:
            stamps = sorted(executor.map(lambda _: acquire(), range(4)))
        for previous, current in zip(stamps, stamps[1:]):
            self.assertGreaterEqual(current - previous, 0.025)
