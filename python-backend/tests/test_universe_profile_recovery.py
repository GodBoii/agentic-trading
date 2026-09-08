from collections import Counter
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd

from pipeline.config import PipelineConfig
from pipeline.stages.universe_scanner import UniverseScanner
from tests.test_universe_broad_mode import venue_row


NOW = datetime.fromisoformat("2026-09-08T07:00:00+05:30")


def history(last_day=NOW - timedelta(days=1)):
    return pd.DataFrame({"timestamp": [last_day - timedelta(days=i) for i in reversed(range(25))],
                         "open": [100.] * 25, "high": [102.] * 25, "low": [99.] * 25,
                         "close": [101.] * 25, "volume": [1000.] * 25})


def scanner(tmp_path):
    item = UniverseScanner.__new__(UniverseScanner)
    item.config = PipelineConfig(results_dir=tmp_path)
    item.market_time = SimpleNamespace(now=lambda: NOW, tz=NOW.tzinfo)
    item.failure_counts = Counter()
    item._wait_for_historical_api = Mock()
    item._fetch_history_resilient = lambda call: call()
    item._log = Mock()
    item.dhan = Mock()
    item.dhan.fetch_daily_history.return_value = {"status": "failure"}
    return item


def cache(tmp_path, frame):
    path = tmp_path / "reference/historical-daily/NSE_EQ/1.parquet"
    path.parent.mkdir(parents=True)
    frame.to_parquet(path)
    return path


def test_failed_refresh_preserves_dated_valid_history(tmp_path):
    item = scanner(tmp_path)
    path = cache(tmp_path, history())
    before = path.read_bytes()
    frame, error = item._daily_frame({"exchange_segment": "NSE_EQ", "security_id": 1})
    assert error == "cached_profile_after_refresh_failure"
    assert frame.attrs["profile_status"] == "stale"
    assert frame.attrs["profile_age_days"] == 1
    assert path.read_bytes() == before


def test_old_or_future_only_cache_is_not_a_fallback(tmp_path):
    item = scanner(tmp_path)
    path = cache(tmp_path, history(NOW - timedelta(days=8)))
    assert item._daily_frame({"exchange_segment": "NSE_EQ", "security_id": 1})[0] is None
    frame = history()
    frame["timestamp"] = NOW + timedelta(days=1)
    frame.to_parquet(path)
    assert item._daily_frame({"exchange_segment": "NSE_EQ", "security_id": 1})[0] is None


def test_corrupt_cache_does_not_prevent_fresh_request(tmp_path):
    item = scanner(tmp_path)
    path = cache(tmp_path, history())
    path.write_bytes(b"not parquet")
    item.dhan.fetch_daily_history.return_value = {"status": "success"}
    item.dhan.daily_response_to_df.return_value = history()
    frame, error = item._daily_frame({"exchange_segment": "NSE_EQ", "security_id": 1})
    assert len(frame) == 25
    assert error is None
    assert len(pd.read_parquet(path)) == 25
    item.dhan.fetch_daily_history.reset_mock()
    cached, error = item._daily_frame({"exchange_segment": "NSE_EQ", "security_id": 1})
    item.dhan.fetch_daily_history.assert_not_called()
    assert error is None
    assert cached.attrs["fetched_for_market_date"] == NOW.date().isoformat()


def test_incomplete_comparison_keeps_previous_venue(tmp_path):
    item = scanner(tmp_path)
    rows = pd.concat([venue_row(), venue_row()], ignore_index=True)
    rows.loc[1, "EXCH_ID"] = "BSE"
    rows.loc[1, "SECURITY_ID"] = 2
    item._daily_frame = lambda venue: (None, "failure") if venue["exchange_segment"] == "NSE_EQ" else (history(), None)
    record, _, _ = item._scan_isin("INE1", rows, {"INE1": "NSE_EQ"})
    assert record.selected_venue.exchange_segment == "NSE_EQ"
    assert record.historical["status"] == "unavailable"


def test_valid_comparisons_still_allow_more_liquid_venue(tmp_path):
    item = scanner(tmp_path)
    rows = pd.concat([venue_row(), venue_row()], ignore_index=True)
    rows.loc[1, "EXCH_ID"] = "BSE"
    rows.loc[1, "SECURITY_ID"] = 2

    def daily(venue):
        frame = history()
        if venue["exchange_segment"] == "BSE_EQ":
            frame["volume"] *= 3
        return frame, None

    item._daily_frame = daily
    record, _, _ = item._scan_isin("INE1", rows, {"INE1": "NSE_EQ"})
    assert record.selected_venue.exchange_segment == "BSE_EQ"
