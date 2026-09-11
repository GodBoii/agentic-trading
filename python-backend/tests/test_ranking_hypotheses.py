"""Causal and identity checks for the offline minute-tape comparison."""

import base64

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from pipeline.research.ranking_hypotheses import evaluate, features
from pipeline.research.ranking_tape_export import COLUMNS, reduce_day


DAY = "2026-09-09"
START = pd.Timestamp(f"{DAY}T09:15:59+05:30")
CAUSAL = ["exchange_segment", "security_id", "decision", "renewal", "recent_range",
          "freshness", "efficiency5", "expansion", "value5", "entry_fresh"]


def tape(stocks=12, minutes=30):
    rows = []
    for number in range(stocks):
        for minute in range(minutes):
            price = 100 + number + minute * (number + 1) * .01
            row = dict.fromkeys(COLUMNS, 1.0)
            row.update(received_at=(START + pd.Timedelta(minutes=minute)).isoformat(),
                       exchange_segment="NSE_EQ" if number % 2 == 0 else "BSE_EQ",
                       security_id=number // 2 + 1, activity_rank=number + 1,
                       last_price=price, open=price - .03, high=price + .1, low=price - .1,
                       day_volume=1000 + minute * (number + 1) * 100,
                       spread_percent=.02, last_trade_age_seconds=0,
                       best_bid=price - .01, best_ask=price + .01)
            rows.append(row)
    return pd.DataFrame(rows)


def test_future_prices_volumes_and_ranks_cannot_change_prior_features_or_selection():
    original = tape()
    cutoff = pd.Timestamp(f"{DAY}T09:35:00+05:30").timestamp()
    changed = original.copy()
    future = pd.to_datetime(changed.received_at, utc=True).array.as_unit("ns").asi8 / 1e9 >= cutoff
    changed.loc[future, ["last_price", "high", "low", "day_volume"]] *= 7
    changed.loc[future, "activity_rank"] = 100 - changed.loc[future, "activity_rank"]
    changed.loc[future, "spread_percent"] = 1
    before, after = features(original), features(changed)
    pd.testing.assert_frame_equal(before.loc[before.decision <= cutoff, CAUSAL].reset_index(drop=True),
                                  after.loc[after.decision <= cutoff, CAUSAL].reset_index(drop=True))
    _, selected_before = evaluate(original, DAY)
    _, selected_after = evaluate(changed, DAY)
    selection_columns = ["policy", "decision", "exchange_segment", "security_id", "activity_rank",
                         "renewal", "recent_range", "freshness", "efficiency5", "expansion", "value5"]
    pd.testing.assert_frame_equal(
        selected_before.loc[selected_before.decision <= cutoff, selection_columns].reset_index(drop=True),
        selected_after.loc[selected_after.decision <= cutoff, selection_columns].reset_index(drop=True),
    )
    assert not before.loc[before.decision == cutoff, "forward_abs"].equals(
        after.loc[after.decision == cutoff, "forward_abs"]
    )


def test_missing_minute_does_not_bridge_forward_labels_or_create_candidate():
    frame = tape(stocks=1)
    missing_stamp = (START + pd.Timedelta(minutes=12)).isoformat()
    frame = frame[frame.received_at != missing_stamp]
    result = features(frame)
    missing_minute = int(pd.Timestamp(missing_stamp).timestamp() // 60)
    missing = result[result.m == missing_minute].iloc[0]
    assert not missing.entry_fresh
    assert not missing.label_available
    preceding = result[result.m.between(missing_minute - 5, missing_minute - 1)]
    assert not preceding.label_available.any()
    after_gap = result[result.m == missing_minute + 1].iloc[0]
    assert pd.isna(after_gap.value5)
    assert pd.isna(after_gap.renewal)


def test_same_security_id_on_two_exchanges_keeps_separate_series():
    frame = tape(stocks=2)
    frame.loc[frame.exchange_segment == "BSE_EQ", ["last_price", "high", "low"]] *= 10
    result = features(frame)
    assert set(result.security_id) == {1}
    assert len(result) == 60
    assert result[result.exchange_segment == "BSE_EQ"].last_price.min() > 1000
    assert result[result.exchange_segment == "NSE_EQ"].last_price.max() < 110


def test_cumulative_reset_invalidates_volume_windows_instead_of_inventing_quiet_volume():
    frame = tape(stocks=1)
    frame.loc[frame.index >= 8, "day_volume"] -= 1500
    result = features(frame)
    assert result.iloc[8:14].renewal.isna().all()
    assert result.iloc[8:13].value5.isna().all()
    assert pd.notna(result.iloc[14].renewal)


def write_shard(root, name, frame):
    directory = root / DAY / "one-second" / "hour=09"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    pq.write_table(pa.Table.from_pandas(frame[COLUMNS], preserve_index=False), path)
    return path


def test_export_manifest_and_venue_identity(tmp_path):
    frame = tape(stocks=2, minutes=2)
    path = write_shard(tmp_path, "part.parquet", frame)
    payload = reduce_day(tmp_path, DAY)
    result = pq.read_table(pa.BufferReader(base64.b64decode(payload["parquet"]))).to_pandas()
    assert payload["rows"] == 4
    assert set(result.exchange_segment) == {"NSE_EQ", "BSE_EQ"}
    assert payload["manifest"] == [{"name": str(path), "bytes": path.stat().st_size,
                                     "mtime_ns": path.stat().st_mtime_ns}]


def test_export_open_and_first_at_come_from_earliest_observation(tmp_path):
    frame = tape(stocks=1, minutes=1)
    earliest = frame.copy()
    earliest["received_at"] = f"{DAY}T09:15:01+05:30"
    earliest["last_price"] = 90
    middle = frame.copy()
    middle["received_at"] = f"{DAY}T09:15:30+05:30"
    middle["last_price"] = 95
    write_shard(tmp_path, "long.parquet", pd.concat([earliest, frame]))
    write_shard(tmp_path, "middle.parquet", middle)
    payload = reduce_day(tmp_path, DAY)
    result = pq.read_table(pa.BufferReader(base64.b64decode(payload["parquet"]))).to_pandas().iloc[0]
    assert result.open == 90
    assert result.first_at == earliest.received_at.iloc[0]
    assert result.high == 100
    assert result.low == 90
