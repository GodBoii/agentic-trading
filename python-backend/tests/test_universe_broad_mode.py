from __future__ import annotations

import unittest
import sys
import types
from collections import Counter
from types import SimpleNamespace
from unittest.mock import Mock, patch
from datetime import datetime, timedelta, timezone

import pandas as pd

if "dhanhq" not in sys.modules:
    fake_dhan = types.ModuleType("dhanhq")
    fake_dhan.MarketFeed = type("MarketFeed", (), {})
    fake_dhan.DhanContext = type("DhanContext", (), {})
    fake_dhan.HistoricalData = type("HistoricalData", (), {})
    fake_dhan.OptionChain = type("OptionChain", (), {})
    fake_dhan.FullDepth = type("FullDepth", (), {})
    fake_dhan.dhanhq = type("dhanhq", (), {})
    sys.modules["dhanhq"] = fake_dhan

from pipeline.config import PipelineConfig
from pipeline.stages.universe_scanner import UniverseScanner
from pipeline.services.storage_service import StorageService


def venue_row() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "EXCH_ID": "NSE",
                "SECURITY_ID": 1,
                "SERIES": "EQ",
                "SYMBOL_NAME": "CHEAP",
                "DISPLAY_NAME": "Cheap Stock",
                "TICK_SIZE": 0.05,
                "SM_UPPER_LIMIT": 60.0,
                "SM_LOWER_LIMIT": 40.0,
                "BUY_SELL_INDICATOR": "A",
                "BRACKET_FLAG": "Y",
                "COVER_FLAG": "Y",
                "MTF_LEVERAGE": 1,
                "LOT_SIZE": 1,
                "SM_FREEZE_QTY": 10000,
                "ASM_GSM_FLAG": "N",
                "ASM_GSM_CATEGORY": "NA",
            }
        ]
    )


class BroadUniverseTests(unittest.TestCase):
    def scanner(self) -> UniverseScanner:
        scanner = UniverseScanner.__new__(UniverseScanner)
        scanner.config = PipelineConfig(stage1_apply_opportunity_filters=False)
        scanner.failure_counts = Counter()
        return scanner

    def test_low_price_low_adv_stock_remains_observable(self) -> None:
        scanner = self.scanner()
        start = datetime(2026, 7, 1, tzinfo=timezone.utc)
        frame = pd.DataFrame(
            {
                "timestamp": [start + timedelta(days=index) for index in range(21)],
                "open": [50.0] * 21,
                "high": [50.1] * 21,
                "low": [49.9] * 21,
                "close": [50.0] * 21,
                "volume": [1000] * 21,
            }
        )
        scanner._daily_frame = lambda _venue: (frame, None)

        record, _comparisons, exclusion = scanner._scan_isin("INE1", venue_row(), {})

        self.assertIsNone(exclusion)
        self.assertIsNotNone(record)
        self.assertLess(record.historical["adv_20_cr"], 10.0)
        self.assertLess(record.historical["previous_close"], 100.0)

    def test_history_failure_does_not_remove_tradable_identity(self) -> None:
        scanner = self.scanner()
        scanner._daily_frame = lambda _venue: (None, "historical_fetch_failed")

        record, _comparisons, exclusion = scanner._scan_isin("INE1", venue_row(), {})

        self.assertIsNone(exclusion)
        self.assertIsNotNone(record)
        self.assertEqual(record.historical["status"], "unavailable")
        self.assertEqual(record.selected_venue.exchange_segment, "NSE_EQ")

    def test_optional_profile_failures_do_not_invalidate_universe(self) -> None:
        payload = {
            "stage": "universe_scanner",
            "summary": {
                "status": "completed",
                "unique_isins_scanned": 3500,
                "historical_fetch_failed": 1000,
                "opportunity_filters_applied": False,
            },
        }

        self.assertTrue(StorageService.is_stage_snapshot_usable(payload, 0.10))

    def test_profile_builder_waits_out_shared_historical_cooldown(self) -> None:
        scanner = self.scanner()
        scanner.dhan = SimpleNamespace(
            historical_rate_limit_until=10.0,
            historical_circuit_open_until=0.0,
        )
        with (
            patch(
                "pipeline.stages.universe_scanner.time.monotonic",
                side_effect=[0.0, 11.0],
            ),
            patch("pipeline.stages.universe_scanner.time.sleep") as sleep,
        ):
            scanner._wait_for_historical_api()

        sleep.assert_called_once_with(10.05)

    def test_gateway_cooldown_is_retried_instead_of_becoming_missing_data(self) -> None:
        scanner = self.scanner()
        responses = iter(
            [
                {
                    "status": "failure",
                    "remarks": {
                        "error_code": "LOCAL-RATE-LIMIT-COOLDOWN",
                        "error_message": "retry available in 2 seconds",
                    },
                },
                {"status": "success", "close": [100.0]},
            ]
        )
        with patch("pipeline.stages.universe_scanner.time.sleep") as sleep:
            result = scanner._fetch_history_resilient(lambda: next(responses))

        self.assertEqual(result["status"], "success")
        sleep.assert_called_once_with(2.25)

    def test_non_retryable_history_failure_returns_immediately(self) -> None:
        scanner = self.scanner()
        response = {"status": "failure", "remarks": {"error_code": "BAD_REQUEST"}}
        request = Mock(return_value=response)

        result = scanner._fetch_history_resilient(request)

        self.assertIs(result, response)
        request.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
