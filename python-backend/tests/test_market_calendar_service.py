from __future__ import annotations

import unittest
from datetime import date

from pipeline.services.market_calendar_service import MarketCalendarService


class MarketCalendarServiceTests(unittest.TestCase):
    def service(self) -> MarketCalendarService:
        service = MarketCalendarService.__new__(MarketCalendarService)
        service.fail_closed = True
        service._forced_status = lambda: None
        service._manual_holidays = lambda: set()
        return service

    def test_weekend_is_closed_without_external_lookup(self) -> None:
        service = self.service()
        service._load_or_refresh_nse_cache = lambda: self.fail("weekend queried NSE")

        result = service.is_trading_day(date(2026, 8, 30))

        self.assertFalse(result["is_trading_day"])
        self.assertEqual(result["reason"], "weekend")

    def test_only_cash_market_holidays_are_extracted(self) -> None:
        service = self.service()
        payload = {
            "CM": [{"tradingDate": "26-Aug-2026"}],
            "COM": [{"tradingDate": "01-Jan-2026"}],
            "CD": [{"tradingDate": "02-Jan-2026"}],
        }

        dates = service._extract_dates(payload)

        self.assertEqual(dates, {"2026-08-26"})

    def test_cash_market_holiday_is_closed(self) -> None:
        service = self.service()
        service._load_or_refresh_nse_cache = lambda: {
            "status": "success",
            "holiday_dates": ["2026-08-26"],
            "calendar_segment": "CM",
        }

        result = service.is_trading_day(date(2026, 8, 26))

        self.assertFalse(result["is_trading_day"])
        self.assertEqual(result["reason"], "nse_trading_holiday")

    def test_uncovered_calendar_year_fails_closed(self) -> None:
        service = self.service()
        service._load_or_refresh_nse_cache = lambda: {
            "status": "stale_or_unavailable",
            "holiday_dates": ["2025-12-25"],
            "calendar_segment": "CM",
        }

        result = service.is_trading_day(date(2026, 8, 31))

        self.assertFalse(result["is_trading_day"])
        self.assertEqual(result["reason"], "market_calendar_year_unavailable")

    def test_covered_normal_weekday_is_open(self) -> None:
        service = self.service()
        service._load_or_refresh_nse_cache = lambda: {
            "status": "success",
            "holiday_dates": ["2026-08-26"],
            "calendar_segment": "CM",
        }

        result = service.is_trading_day(date(2026, 8, 31))

        self.assertTrue(result["is_trading_day"])
        self.assertEqual(result["source"], "nse_holiday_cache")


if __name__ == "__main__":
    unittest.main()
