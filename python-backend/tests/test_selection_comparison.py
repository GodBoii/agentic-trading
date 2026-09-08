from datetime import datetime

import pandas as pd
import pytest

from pipeline.research.selection_comparison import compare, label_minutes, read_minutes


def minutes():
    start = int(datetime.fromisoformat("2026-09-08T09:19:00+05:30").timestamp() // 60)
    return pd.DataFrame([
        {"minute": start + i, "timestamp": (start + i) * 60 + 59, "exchange_segment": "NSE_EQ",
         "security_id": 1, "last_price": 100 + i, "high": 101 + i, "low": 99 + i,
         "activity_rank": 1, "spread_percent": .02, "traded_value_5m": 1_000_000,
         "realized_volatility_percent": .5, "last_trade_age_seconds": 0,
         "best_bid": 100, "best_ask": 100.02}
        for i in range(7)
    ])


def test_future_label_excludes_entry_minute_and_uses_next_five():
    frame = minutes()
    frame.loc[0, "high"] = 999
    labelled = label_minutes(frame)
    assert labelled.iloc[0].range_pct == pytest.approx(6)
    assert labelled.iloc[0].return_pct == pytest.approx(5)
    assert labelled.iloc[0].label_available
    assert not labelled.iloc[-1].label_available


def test_missing_future_minute_does_not_become_a_complete_label():
    labelled = label_minutes(minutes().drop(index=2))
    assert not labelled.iloc[0].label_available


def test_future_changes_do_not_change_attention_selection():
    frame = minutes()
    baseline = compare(frame)
    frame.loc[frame.index > 0, ["high", "low", "last_price"]] *= 2
    changed = compare(frame)
    for name in baseline["policies"]:
        assert baseline["policies"][name]["selected"] == changed["policies"][name]["selected"]


def test_minute_aggregation_merges_files_by_time_and_keeps_venues_separate(tmp_path):
    directory = tmp_path / "hour=09"
    directory.mkdir()
    rows = minutes().iloc[:1].drop(columns=["minute", "timestamp", "high", "low"])
    rows["received_at"] = "2026-09-08T09:19:58+05:30"
    rows.to_parquet(directory / "b.parquet", index=False)
    later = rows.copy()
    later["received_at"] = "2026-09-08T09:19:59+05:30"
    later["last_price"] = 101
    other_venue = later.copy()
    other_venue["exchange_segment"] = "BSE_EQ"
    other_venue["last_price"] = 200
    pd.concat([later, other_venue]).to_parquet(directory / "a.parquet", index=False)
    result, manifest = read_minutes(tmp_path)
    assert len(manifest) == 2
    assert len(result) == 2
    nse = result[result.exchange_segment == "NSE_EQ"].iloc[0]
    assert nse.last_price == 101
    assert nse.high == 101
    assert nse.low == 100
