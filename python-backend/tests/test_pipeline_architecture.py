from __future__ import annotations

import os
import tempfile
import time
import unittest
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd

from pipeline.config import PipelineConfig
from pipeline.models import UniverseRecord, VenueIdentity
from pipeline.services.dhan_credentials import DhanCredentialStore, generate_totp
from pipeline.services.dhan_service import DhanService
from pipeline.runtime.run_dhan_auth_manager import DhanAuthManager
from pipeline.stages.intra_finder import IntraFinder, subscription_batches
from pipeline.stages.indicator_event_engine import IndicatorEventEngine
from pipeline.stages.universe_scanner import UniverseScanner


def temp_config(root: Path) -> PipelineConfig:
    results = root / "results"
    return PipelineConfig(
        root_dir=root,
        backend_dir=root,
        results_dir=results,
        runtime_dir=root / "runtime-data",
        runtime_secrets_dir=root / "runtime-data" / "secrets",
        dhan_credentials_path=root / "runtime-data" / "secrets" / "credentials.json",
        dhan_auth_health_path=results / "auth" / "health.json",
        stage1_results_dir=results / "stage1",
        stage2_results_dir=results / "stage2",
        stage1_latest_path=results / "stage1" / "latest.json",
        stage2_latest_path=results / "stage2" / "latest.json",
        regime_latest_path=results / "regime" / "latest.json",
        nifty_depth_latest_path=results / "nifty" / "latest.json",
    )


class CredentialStoreTests(unittest.TestCase):
    def test_encrypted_versioned_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = temp_config(Path(directory))
            with patch.dict(os.environ, {"DHAN_CREDENTIAL_ENCRYPTION_SECRET": "test-secret", "DHAN_CREDENTIAL_ENCRYPTION_SECRET_FILE": ""}, clear=False):
                store = DhanCredentialStore(config)
                first = store.publish(
                    client_id="123456",
                    access_token="token-one",
                    expires_at="2026-08-01T00:00:00+05:30",
                    source="test",
                )
                second = store.publish(
                    client_id="123456",
                    access_token="token-two",
                    expires_at="2026-08-02T00:00:00+05:30",
                    source="test",
                )
                loaded = store.load()
            self.assertEqual(first.version, 1)
            self.assertEqual(second.version, 2)
            self.assertEqual(loaded.access_token, "token-two")
            self.assertNotIn("token-two", config.dhan_credentials_path.read_text(encoding="utf-8"))

    def test_totp_matches_rfc_vector_truncated_to_six_digits(self) -> None:
        secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
        self.assertEqual(generate_totp(secret, at_time=59), "287082")

    def test_auth_manager_renews_and_publishes_new_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = temp_config(Path(directory))
            expiry = datetime.now(ZoneInfo("Asia/Kolkata")).replace(microsecond=0) + timedelta(hours=1)

            class FakeDhan:
                client_id = "123456"
                credential_version = 1

                def fetch_user_profile(self):
                    return {
                        "status": "success",
                        "data": {"tokenValidity": expiry.strftime("%d/%m/%Y %H:%M")},
                    }

                def renew_access_token(self):
                    return {"status": "success", "data": {"accessToken": "renewed-token"}}

            with patch.dict(os.environ, {"DHAN_CREDENTIAL_ENCRYPTION_SECRET": "test-secret", "DHAN_CREDENTIAL_ENCRYPTION_SECRET_FILE": ""}, clear=False):
                store = DhanCredentialStore(config)
                store.publish(
                    client_id="123456",
                    access_token="old-token",
                    expires_at=expiry.isoformat(),
                    source="test",
                )
                manager = DhanAuthManager(config)
                with patch(
                    "pipeline.runtime.run_dhan_auth_manager.DhanService",
                    return_value=FakeDhan(),
                ):
                    self.assertTrue(manager.run_once())
                loaded = store.load()
            self.assertEqual(loaded.access_token, "renewed-token")
            self.assertEqual(loaded.version, 2)
            self.assertEqual(manager.health["last_refresh_method"], "renew_token")

    def test_auth_manager_uses_totp_after_profile_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = temp_config(Path(directory))

            class FakeDhan:
                client_id = "123456"
                credential_version = 1
                generated = False

                def fetch_user_profile(self):
                    if self.generated:
                        return {
                            "status": "success",
                            "data": {"tokenValidity": "26/08/2026 08:30"},
                        }
                    return {"status": "failure", "remarks": "expired"}

                def generate_access_token(self, *, pin, totp):
                    self.generated = pin == "1234" and len(totp) == 6
                    return {"status": "success", "data": {"accessToken": "recovered-token"}}

            fake = FakeDhan()
            secrets = {
                "DHAN_CREDENTIAL_ENCRYPTION_SECRET": "test-secret",
                "DHAN_CREDENTIAL_ENCRYPTION_SECRET_FILE": "",
                "DHAN_SCANNER_PIN": "1234",
                "DHAN_SCANNER_PIN_FILE": "",
                "DHAN_SCANNER_TOTP_SECRET": "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ",
                "DHAN_SCANNER_TOTP_SECRET_FILE": "",
            }
            with patch.dict(os.environ, secrets, clear=False):
                store = DhanCredentialStore(config)
                store.publish(
                    client_id="123456",
                    access_token="expired-token",
                    expires_at=None,
                    source="test",
                )
                manager = DhanAuthManager(config)
                with patch(
                    "pipeline.runtime.run_dhan_auth_manager.DhanService",
                    return_value=fake,
                ):
                    self.assertTrue(manager.run_once())
                loaded = store.load()
            self.assertTrue(fake.generated)
            self.assertEqual(loaded.access_token, "recovered-token")
            self.assertEqual(manager.health["last_refresh_method"], "totp_recovery")

    def test_auth_manager_rotates_valid_token_after_twelve_hours(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = temp_config(Path(directory))
            now = datetime(2026, 8, 25, 3, 0, tzinfo=timezone.utc)
            expiry = now.astimezone(ZoneInfo("Asia/Kolkata")) + timedelta(hours=10)

            class FakeDhan:
                client_id = "123456"
                credential_version = 1
                renew_calls = 0

                def fetch_user_profile(self):
                    return {
                        "status": "success",
                        "data": {"tokenValidity": expiry.strftime("%d/%m/%Y %H:%M")},
                    }

                def renew_access_token(self):
                    self.renew_calls += 1
                    return {"status": "success", "data": {"accessToken": "rotated-token"}}

            fake = FakeDhan()
            env = {
                "DHAN_CREDENTIAL_ENCRYPTION_SECRET": "test-secret",
                "DHAN_CREDENTIAL_ENCRYPTION_SECRET_FILE": "",
                "DHAN_AUTO_RENEW_MAX_AGE_HOURS": "12",
            }
            with patch.dict(os.environ, env, clear=False):
                store = DhanCredentialStore(config)
                store.publish(
                    client_id="123456",
                    access_token="old-token",
                    expires_at=expiry.isoformat(),
                    source="test",
                )
                manager = DhanAuthManager(config, now=lambda: now)
                manager.store.bootstrap = lambda: SimpleNamespace(
                    issued_at=(now - timedelta(hours=12)).isoformat()
                )
                with patch(
                    "pipeline.runtime.run_dhan_auth_manager.DhanService",
                    return_value=fake,
                ):
                    self.assertTrue(manager.run_once())
                loaded = store.load()
            self.assertEqual(fake.renew_calls, 1)
            self.assertEqual(loaded.access_token, "rotated-token")
            self.assertEqual(manager.health["last_refresh_method"], "scheduled_12h_renewal")

    def test_auth_manager_wakes_at_0830_ist_and_records_live_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = temp_config(Path(directory))
            before_check = datetime(2026, 8, 25, 2, 59, tzinfo=timezone.utc)
            at_check = datetime(2026, 8, 25, 3, 0, tzinfo=timezone.utc)
            manager = DhanAuthManager(config, now=lambda: before_check)
            self.assertEqual(manager._seconds_until_daily_verification(), 60)

            manager = DhanAuthManager(config, now=lambda: at_check)
            manager._record_live_check(scheduled_0830=True)
            self.assertEqual(manager.health["last_0830_token_check_date"], "2026-08-25")
            self.assertEqual(manager.health["last_0830_token_check_status"], "healthy")

    def test_auth_manager_schedules_exact_twelve_hour_rotation_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = temp_config(Path(directory))
            now = datetime(2026, 8, 25, 3, 0, tzinfo=timezone.utc)
            env = {
                "DHAN_CREDENTIAL_ENCRYPTION_SECRET": "test-secret",
                "DHAN_CREDENTIAL_ENCRYPTION_SECRET_FILE": "",
                "DHAN_AUTO_RENEW_MAX_AGE_HOURS": "12",
            }
            with patch.dict(os.environ, env, clear=False):
                manager = DhanAuthManager(config, now=lambda: now)
                manager.store.load = lambda required=False: SimpleNamespace(
                    issued_at=(now - timedelta(hours=11, minutes=59)).isoformat()
                )
                self.assertEqual(manager._seconds_until_rotation(), 60)


class UniverseScannerTests(unittest.TestCase):
    def _scanner(self) -> UniverseScanner:
        scanner = UniverseScanner.__new__(UniverseScanner)
        scanner.config = PipelineConfig()
        scanner.exclusions = []
        scanner.failure_counts = Counter()
        return scanner

    def test_master_filter_excludes_surveillance_and_unsupported_series(self) -> None:
        scanner = self._scanner()
        frame = pd.DataFrame(
            [
                {
                    "EXCH_ID": "NSE",
                    "SEGMENT": "E",
                    "SECURITY_ID": 1,
                    "ISIN": "INE1",
                    "INSTRUMENT": "EQUITY",
                    "INSTRUMENT_TYPE": "ES",
                    "SERIES": "EQ",
                    "ASM_GSM_FLAG": "N",
                    "BUY_SELL_INDICATOR": "A",
                },
                {
                    "EXCH_ID": "BSE",
                    "SEGMENT": "E",
                    "SECURITY_ID": 2,
                    "ISIN": "INE2",
                    "INSTRUMENT": "EQUITY",
                    "INSTRUMENT_TYPE": "ES",
                    "SERIES": "A",
                    "ASM_GSM_FLAG": "Y",
                    "ASM_GSM_CATEGORY": "ASM",
                    "BUY_SELL_INDICATOR": "A",
                },
                {
                    "EXCH_ID": "NSE",
                    "SEGMENT": "E",
                    "SECURITY_ID": 3,
                    "ISIN": "INE3",
                    "INSTRUMENT": "EQUITY",
                    "INSTRUMENT_TYPE": "ES",
                    "SERIES": "BE",
                    "ASM_GSM_FLAG": "N",
                    "BUY_SELL_INDICATOR": "A",
                },
            ]
        )
        result = scanner._eligible_venue_rows(frame)
        self.assertEqual(result["ISIN"].tolist(), ["INE1"])
        self.assertEqual(scanner.failure_counts["asm_gsm"], 1)
        self.assertEqual(scanner.failure_counts["unsupported_series"], 1)

    def test_more_liquid_bse_venue_is_selected(self) -> None:
        scanner = self._scanner()
        scanner.config = PipelineConfig(
            stage1_min_price=1,
            stage1_max_price=10_000,
            stage1_min_adv_cr=0,
            stage1_min_atr_percent=0,
            stage1_min_active_session_ratio=0,
        )
        rows = pd.DataFrame(
            [
                {
                    "EXCH_ID": "NSE",
                    "SEGMENT": "E",
                    "SECURITY_ID": 10,
                    "ISIN": "INE1",
                    "SYMBOL_NAME": "ABC",
                    "DISPLAY_NAME": "ABC",
                    "SERIES": "EQ",
                    "ASM_GSM_FLAG": "N",
                    "BUY_SELL_INDICATOR": "A",
                },
                {
                    "EXCH_ID": "BSE",
                    "SEGMENT": "E",
                    "SECURITY_ID": 20,
                    "ISIN": "INE1",
                    "SYMBOL_NAME": "ABC",
                    "DISPLAY_NAME": "ABC",
                    "SERIES": "A",
                    "ASM_GSM_FLAG": "N",
                    "BUY_SELL_INDICATOR": "A",
                },
            ]
        )

        def history(venue):
            volume = 1_000 if venue["exchange"] == "NSE" else 10_000
            timestamps = pd.date_range("2026-06-01", periods=21, freq="B", tz="Asia/Kolkata")
            return (
                pd.DataFrame(
                    {
                        "timestamp": timestamps,
                        "open": 100,
                        "high": 103,
                        "low": 98,
                        "close": 101,
                        "volume": volume,
                    }
                ),
                None,
            )

        scanner._daily_frame = history
        record, _, exclusion = scanner._scan_isin("INE1", rows, {})
        self.assertIsNone(exclusion)
        self.assertEqual(record.selected_venue.exchange_segment, "BSE_EQ")

    def test_intraday_baseline_converts_utc_candles_to_ist(self) -> None:
        scanner = self._scanner()
        scanner.market_time = FakeMarketTime()
        scanner.captured_live_baselines = {}
        timestamps = pd.to_datetime(
            [
                "2026-07-30 03:45:00",
                "2026-07-30 03:50:00",
                "2026-07-30 03:55:00",
            ]
        )

        class FakeDhan:
            def fetch_intraday_history(self, *args, **kwargs):
                return {"status": "success"}

            def intraday_response_to_df(self, response):
                return pd.DataFrame(
                    {
                        "timestamp": timestamps,
                        "open": [100, 101, 102],
                        "high": [102, 103, 104],
                        "low": [99, 100, 101],
                        "close": [101, 102, 103],
                        "volume": [1000, 1200, 1400],
                    }
                )

        scanner.dhan = FakeDhan()
        record = UniverseRecord(
            isin="INE1",
            symbol="ABC",
            display_name="ABC",
            instrument="EQUITY",
            instrument_type="ES",
            selected_venue=VenueIdentity("NSE", "NSE_EQ", 10, "EQ", "ABC"),
            selected_venue_reason="test",
        )
        baseline = scanner._intraday_baseline(record)
        self.assertEqual(baseline["timezone"], "Asia/Kolkata")
        self.assertEqual(baseline["schema_version"], 2)
        self.assertEqual(
            sorted(baseline["median_cumulative_volume"]),
            ["09:15", "09:20", "09:25"],
        )


class FakeMarketTime:
    tz = ZoneInfo("Asia/Kolkata")

    def now(self):
        return datetime(2026, 7, 31, 10, 0, tzinfo=self.tz)

    def market_date_str(self):
        return "2026-07-31"


class IntraFinderTests(unittest.TestCase):
    def _finder(self, root: Path) -> IntraFinder:
        config = temp_config(root)
        finder = IntraFinder.__new__(IntraFinder)
        finder.config = config
        finder.market_time = FakeMarketTime()
        finder.market_calendar = None
        finder.universe_version = "2026-07-31-test"
        finder.event_state = {"events": {}, "active_setups": {}, "last_stock_event_at": {}}
        finder.raw_buffer = []
        finder.derived_buffer = []
        finder.last_flush = time.time()
        finder.last_status_save = time.time()
        finder.packet_count = 0
        finder.events_formed = 0
        finder.events_triggered = 0
        finder.events_suppressed = 0
        finder.reconnect_count = 0
        finder.universe_wait_count = 0
        finder.shadow_mode = True
        finder.detector_mode = "indicator_events"
        finder.indicator_engine = IndicatorEventEngine(event_cooldown_seconds=600)
        finder.indicator_aggregation_seconds = 1
        finder.stock_agent_cooldown_seconds = 1200
        finder.pending_indicator_deadlines = []
        finder.indicator_events_detected = 0
        finder.indicator_aggregates_formed = 0
        finder.readiness_evaluations = 0
        finder.readiness_passed = 0
        finder.readiness_rechecks = 0
        finder.readiness_threshold = 75.0
        finder.readiness_direction_margin = 10.0
        finder.readiness_min_completed_bars = 45
        finder.readiness_min_room_atr = 0.55
        finder.readiness_max_last_trade_age_seconds = 90
        finder.readiness_observation_seconds = 600
        finder.readiness_reevaluation_seconds = 60
        finder.readiness_min_confirmation_seconds = 300
        finder.readiness_max_entry_drift_atr = 0.80
        finder.candidates_seen = 0
        finder.gate_failure_counts = Counter()
        finder.agent_threads = set()
        finder.dispatch_lock = RLock()
        finder.agent_dispatch_successes = 0
        finder.agent_dispatch_failures = 0
        finder.received_security_ids = set()
        finder.full_packet_security_ids = set()
        finder.last_global_packet_at = None
        finder.connected_at = finder.market_time.now() - timedelta(minutes=1)
        finder.connection_state = "CONNECTED"
        finder.session_state = "LIVE"
        finder.state_lock = RLock()
        return finder

    @staticmethod
    def _stock() -> dict:
        return {
            "isin": "INE1",
            "security_id": 10,
            "exchange_segment": "NSE_EQ",
            "symbol": "ABC",
            "display_name": "ABC LTD",
            "instrument": "EQUITY",
            "intraday_baselines": {
                "status": "ready",
                "schema_version": 2,
                "timezone": "Asia/Kolkata",
                "median_cumulative_volume": {"10:00": 1000},
            },
        }

    @staticmethod
    def _packet(volume: int = 2000, price: float = 101.0, vwap: float = 99.0) -> dict:
        return {
            "security_id": 10,
            "LTP": str(price),
            "avg_price": str(vwap),
            "volume": volume,
            "depth": [
                {
                    "bid_price": price - 0.05 - index * 0.01,
                    "ask_price": price + 0.05 + index * 0.01,
                    "bid_quantity": 5000,
                    "ask_quantity": 4000,
                    "bid_orders": 10,
                    "ask_orders": 9,
                }
                for index in range(5)
            ],
        }

    def test_subscription_batching(self) -> None:
        instruments = list(range(250))
        self.assertEqual([len(batch) for batch in subscription_batches(instruments)], [100, 100, 50])

    def test_marketfeed_keeps_interval_and_disables_false_pong_timeout(self) -> None:
        websocket = SimpleNamespace(ping_interval=20, ping_timeout=20)
        DhanService.configure_marketfeed_websocket(SimpleNamespace(ws=websocket))
        self.assertEqual(websocket.ping_interval, 20)
        self.assertIsNone(websocket.ping_timeout)

    def test_completed_candle_orb_event_is_aggregated_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            finder = self._finder(Path(directory))
            stock = self._stock()
            finder.stocks_by_security_id = {10: stock}
            finder.states = {10: finder._new_state(stock)}
            finder.states[10].update(
                {
                    "opening_range_high": 100.0,
                    "opening_range_low": 95.0,
                    "opening_range_complete": True,
                    "state": "WATCHING",
                }
            )
            packet = self._packet(price=99.0)
            now = finder.market_time.now()
            self.assertIsNone(finder.process_packet(packet, received_at=now))
            packet = self._packet(volume=2050, price=101.0)
            self.assertIsNone(
                finder.process_packet(packet, received_at=now + timedelta(minutes=1))
            )
            packet["volume"] = 2100
            self.assertIsNone(
                finder.process_packet(packet, received_at=now + timedelta(minutes=2))
            )
            packet["volume"] = 2200
            with patch(
                "pipeline.stages.intra_finder.evaluate_trade_readiness",
                return_value={
                    "ready": True,
                    "direction": "LONG",
                    "score": 84.0,
                    "components": {},
                    "failures": [],
                },
            ):
                event = finder.process_packet(
                    packet, received_at=now + timedelta(minutes=2, seconds=2)
                )
            self.assertIsNotNone(event)
            self.assertEqual(event["setup_type"], "INDICATOR_EVENT")
            self.assertEqual(event["direction"], "LONG")
            self.assertIn(
                "ORB_BULLISH_CLOSE_BREAK",
                [item["event_type"] for item in event["indicator_events"]],
            )
            self.assertIsNone(
                finder.process_packet(packet, received_at=now + timedelta(minutes=3))
            )

    def test_packet_bursts_cannot_create_completed_candle_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            finder = self._finder(Path(directory))
            stock = self._stock()
            finder.stocks_by_security_id = {10: stock}
            finder.states = {10: finder._new_state(stock)}
            finder.states[10].update(
                {
                    "opening_range_high": 100.0,
                    "opening_range_low": 95.0,
                    "opening_range_complete": True,
                    "state": "WATCHING",
                }
            )
            now = finder.market_time.now()
            self.assertIsNone(
                finder.process_packet(self._packet(price=100.0), received_at=now)
            )
            packet = self._packet(price=101.0)
            for milliseconds in (0, 50, 100, 150, 200):
                self.assertIsNone(
                    finder.process_packet(
                        packet,
                        received_at=now + timedelta(seconds=1, milliseconds=milliseconds),
                    )
                )
            self.assertEqual(finder.events_formed, 0)
            self.assertEqual(len(finder.states[10]["minute_bars"]), 0)

    def test_late_start_above_opening_range_is_not_a_new_breakout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            finder = self._finder(Path(directory))
            stock = self._stock()
            finder.stocks_by_security_id = {10: stock}
            finder.states = {10: finder._new_state(stock)}
            finder.states[10].update(
                {
                    "opening_range_high": 100.0,
                    "opening_range_low": 95.0,
                    "opening_range_complete": True,
                    "state": "WATCHING",
                }
            )
            now = finder.market_time.now()
            for seconds in (0, 5, 10, 15, 20):
                self.assertIsNone(
                    finder.process_packet(
                        self._packet(volume=2000 + seconds * 10, price=101.0),
                        received_at=now + timedelta(seconds=seconds),
                    )
                )
            self.assertEqual(finder.events_formed, 0)

    def test_indicator_observation_waits_for_readiness_when_history_is_too_short(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            finder = self._finder(Path(directory))
            stock = self._stock()
            stock["intraday_baselines"] = {"status": "unavailable"}
            finder.stocks_by_security_id = {10: stock}
            finder.states = {10: finder._new_state(stock)}
            finder.states[10].update(
                {
                    "opening_range_high": 100.0,
                    "opening_range_low": 95.0,
                    "opening_range_complete": True,
                    "state": "WATCHING",
                }
            )
            now = finder.market_time.now()
            self.assertIsNone(
                finder.process_packet(self._packet(price=100.0), received_at=now)
            )
            packet = self._packet(price=101.0)
            finder.process_packet(packet, received_at=now + timedelta(minutes=1))
            finder.process_packet(packet, received_at=now + timedelta(minutes=2))
            event = finder.process_packet(
                packet, received_at=now + timedelta(minutes=2, seconds=2)
            )
            self.assertIsNone(event)
            self.assertGreater(finder.readiness_rechecks, 0)
            self.assertIn("INSUFFICIENT_COMPLETED_BARS", finder.gate_failure_counts)

    def test_vwap_cross_is_detected_only_on_completed_candles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            finder = self._finder(Path(directory))
            stock = self._stock()
            finder.stocks_by_security_id = {10: stock}
            finder.states = {10: finder._new_state(stock)}
            now = finder.market_time.now()
            finder.process_packet(self._packet(price=99.0, vwap=100.0), received_at=now)
            finder.process_packet(
                self._packet(volume=2100, price=101.0, vwap=100.0),
                received_at=now + timedelta(minutes=1),
            )
            finder.process_packet(
                self._packet(volume=2200, price=101.0, vwap=100.0),
                received_at=now + timedelta(minutes=2),
            )
            with patch(
                "pipeline.stages.intra_finder.evaluate_trade_readiness",
                return_value={
                    "ready": True,
                    "direction": "LONG",
                    "score": 82.0,
                    "components": {},
                    "failures": [],
                },
            ):
                event = finder.process_packet(
                    self._packet(volume=2300, price=101.0, vwap=100.0),
                    received_at=now + timedelta(minutes=2, seconds=2),
                )
            self.assertIsNotNone(event)
            self.assertEqual(event["setup_type"], "INDICATOR_EVENT")
            self.assertEqual(event["direction"], "LONG")
            self.assertIn(
                "VWAP_BULLISH_CROSS",
                [item["event_type"] for item in event["indicator_events"]],
            )


if __name__ == "__main__":
    unittest.main()
