from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd

from pipeline.services.signal_data_cache import SignalDataCacheService


class FakeMarketTime:
    def __init__(self) -> None:
        self.tz = ZoneInfo("Asia/Kolkata")
        self.current = datetime(2026, 8, 24, 10, 1, tzinfo=self.tz)

    def now(self) -> datetime:
        return self.current

    def market_date_str(self) -> str:
        return self.current.date().isoformat()


class FakeDhan:
    def __init__(self) -> None:
        self.fetch_calls = 0

    def fetch_intraday_history(self, *_args, **_kwargs):
        self.fetch_calls += 1
        return {
            "status": "success",
            "data": {
                "timestamp": [int(pd.Timestamp("2026-08-22T03:45:00Z").timestamp())],
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.0],
                "volume": [1000],
            },
        }

    def intraday_response_to_df(self, response):
        data = response["data"]
        return pd.DataFrame(
            {
                "timestamp": pd.to_datetime(data["timestamp"], unit="s", utc=True)
                .tz_localize(None),
                "open": data["open"],
                "high": data["high"],
                "low": data["low"],
                "close": data["close"],
                "volume": data["volume"],
            }
        )


class SignalDataCacheTests(unittest.TestCase):
    def test_prewarm_reuses_history_and_merges_causal_bars(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = SimpleNamespace(
                signal_data_cache_dir=Path(temp_dir),
                stock_agent_signal_cache_max_age_seconds=180,
            )
            market_time = FakeMarketTime()
            dhan = FakeDhan()
            cache = SignalDataCacheService(config, dhan, market_time)
            stock = {
                "security_id": 111,
                "exchange_segment": "NSE_EQ",
                "instrument": "EQUITY",
            }

            cache.prewarm(stock)
            cache.prewarm(stock)
            frame = cache.load_frame(
                market_date="2026-08-24",
                exchange_segment="NSE_EQ",
                security_id=111,
                recent_bars=[
                    {
                        "minute_start": "2026-08-24T10:00:00+05:30",
                        "open": 101,
                        "high": 102,
                        "low": 100.5,
                        "close": 101.5,
                        "volume": 200,
                    }
                ],
            )

            self.assertEqual(dhan.fetch_calls, 1)
            self.assertIsNotNone(frame)
            self.assertEqual(len(frame), 2)
            self.assertEqual(float(frame.iloc[-1]["close"]), 101.5)


if __name__ == "__main__":
    unittest.main()
