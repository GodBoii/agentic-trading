from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from pipeline.services.dhan_service import DhanService
from pipeline.services.latency_metrics import LatencyMetrics
from pipeline.services.storage_service import StorageService
from pipeline.stages.live_state import OHLCV


class LiveQualificationTests(unittest.TestCase):
    def test_compact_snapshot_preserves_payload_and_atomic_replacement(self):
        payload = {"states": {"NSE_EQ|1": {"bars": [None, 1.25], "symbol": "test"}}}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            StorageService.save_snapshot(path, payload)
            original_size = path.stat().st_size
            StorageService.save_snapshot(path, payload, compact=True)
            self.assertEqual(StorageService.load_snapshot(path), payload)
            self.assertLess(path.stat().st_size, original_size)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_candle_record_matches_checkpoint_contract(self):
        bar = OHLCV("2026-09-08T10:00:00+05:30", 100, 102, 99, 101, 2000, None)
        self.assertEqual(bar.to_record(), asdict(bar))

    def test_histogram_counts_all_observations_without_retaining_them(self):
        metrics = LatencyMetrics()
        for _ in range(99):
            metrics.observe("ingress", 0.2)
        metrics.observe("ingress", 15000)
        row = metrics.snapshot()["operations"]["ingress"]
        self.assertEqual(row["observations"], 100)
        self.assertEqual(row["p99_upper_ms"], 0.25)
        self.assertEqual(row["max_ms"], 15000)
        self.assertEqual(len(row["counts"]), 17)
        self.assertIsNotNone(row["max_at_epoch"])

    def test_historical_input_failure_retries_once_and_other_errors_do_not(self):
        for method in ("fetch_daily_history", "fetch_intraday_history"):
            for code, expected_calls in (("DH-905", 2), ("DH-907", 1)):
                with self.subTest(method=method, code=code):
                    service = object.__new__(DhanService)
                    service.gateway_url = None
                    service.config = SimpleNamespace(market_open_hour=9, market_open_minute=15)
                    service._market_now = lambda: datetime(2026, 9, 8, 10, tzinfo=timezone.utc)
                    service._historical_circuit_response_if_open = lambda: None
                    service._record_historical_response = lambda response: None
                    service.acquire_data_slot = Mock()
                    responses = [{"status": "failure", "remarks": {"error_code": code, "error_type": "Input_Exception"}},
                                 {"status": "success", "data": {"timestamp": [1]}}]
                    request = Mock(side_effect=responses)
                    service._historical_client = lambda: SimpleNamespace(historical_daily_data=request, intraday_minute_data=request)
                    with patch("pipeline.services.dhan_service.time.sleep"):
                        response = getattr(service, method)(1333, exchange_segment="NSE_EQ", retries=3)
                    self.assertEqual(request.call_count, expected_calls)
                    self.assertEqual(service.acquire_data_slot.call_count, expected_calls)
                    self.assertEqual(response["status"], "success" if code == "DH-905" else "failure")
